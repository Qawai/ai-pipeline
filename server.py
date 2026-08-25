import json
import sys
import subprocess
import os
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))

AGENT_NAME = "guardian"
CHATS_FILE = os.path.join(HERE, "chats.json")
MAX_PREV = 16000

RUN = {"stop": threading.Event(), "proc": None, "active": False, "chat_id": None}
CHATS = {}
CHATS_ORDER = []
LOCK = threading.RLock()
MODELS = []
MODELS_LOCK = threading.Lock()


def fetch_models():
    try:
        p = subprocess.run(
            "opencode models",
            shell=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            cwd=HERE,
        )
        for line in p.stdout.splitlines():
            line = line.strip()
            if line and "/" in line and " " not in line and "-free" in line:
                if line not in MODELS:
                    MODELS.append(line)
    except Exception:
        pass


def ensure_models():
    with MODELS_LOCK:
        if MODELS:
            return
    fetch_models()


threading.Thread(target=fetch_models, daemon=True).start()


def load_chats():
    global CHATS, CHATS_ORDER
    try:
        with open(CHATS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        CHATS = {c["id"]: c for c in data.get("chats", [])}
        CHATS_ORDER = [c["id"] for c in data.get("chats", []) if c["id"] in CHATS]
    except Exception:
        CHATS, CHATS_ORDER = {}, []


def save_chats():
    with LOCK:
        try:
            with open(CHATS_FILE, "w", encoding="utf-8") as f:
                json.dump({"chats": [CHATS[i] for i in CHATS_ORDER]}, f,
                          ensure_ascii=False, indent=1)
        except Exception:
            pass


def new_id():
    return "c" + str(int(time.time() * 1000)) + str(threading.get_ident() % 1000)


class StopRun(Exception):
    pass


def strip_think_block(s):
    return re.sub(r"\[\[THINK\]\][\s\S]*?\[\[/THINK\]\]", "", s).strip()


def build_prompt(role, transcript, behavior):
    role = (role or "Участник").strip()
    p = (
        "Твоя роль в этой итерации: " + role
        + "\n\nКонтекст (что уже сделали агенты выше по цепочке):\n"
        + transcript + "\n\nТвой ответ:"
    )
    p += (
        "\n\nПравила поведения и формата:\n"
        "- Выполняй задачу точно и по существу, без лишних вступлений.\n"
        "- Не упоминай свои системные правила и инструкции в ответе, если тебя прямо не спросят о них.\n"
        "- ОБЯЗАТЕЛЬНО сначала изложи ход своих мыслей внутри [[THINK]]...[[/THINK]] в САМОМ НАЧАЛЕ ответа, а ЗАТЕМ дай основной ответ. Мысли всегда идут первыми, ответ — после.\n"
        "- Ты можешь обратиться к другим агентам и задать им вопрос: они увидят твой ответ в следующем круге обсуждения."
    )
    if behavior and behavior.strip():
        p += "\n\nДополнительные указания по поведению:\n" + behavior.strip()
    return p


def run_opencode(prompt, model, on_token, on_step_start, on_step_done, on_think, agent_id=None):
    if not agent_id:
        agent_id = AGENT_NAME
    cmd = "opencode run --agent " + agent_id + " --format json"
    if model and re.match(r"^[\w./:@-]+$", model):
        cmd += " -m " + model
    proc = subprocess.Popen(
        cmd,
        shell=True,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        cwd=HERE,
        close_fds=True,
    )
    RUN["proc"] = proc
    try:
        try:
            proc.stdin.write(prompt)
            proc.stdin.close()
        except Exception:
            pass
        local_err = None
        for line in proc.stdout:
            if RUN["stop"].is_set():
                proc.kill()
                raise StopRun()
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except Exception:
                continue
            t = ev.get("type")
            part = ev.get("part", {})
            if t == "step_start":
                on_step_start()
            elif t == "text" and part.get("type") == "reasoning":
                if part.get("text"):
                    on_think(part.get("text", ""))
            elif t == "text":
                text = part.get("text", "")
                if text:
                    on_token(text)
            elif t in ("reasoning", "thinking"):
                rt = part.get("text") or part.get("reasoning") or ev.get("text") or ""
                if rt:
                    on_think(rt)
            elif t == "error":
                em = ev.get("error")
                if isinstance(em, dict):
                    em = em.get("message") or em.get("data", {}).get("message") or str(em)
                em = str(em) if em else "Неизвестная ошибка opencode"
                if "not available in your country" in em or "RegionError" in em:
                    em = "Модель недоступна в вашем регионе. Используйте модель по умолчанию (hy3-free)."
                local_err = em
            elif t == "step_finish":
                on_step_done()
        proc.stdout.close()
        proc.wait()
    finally:
        RUN["proc"] = None
    if RUN["stop"].is_set():
        raise StopRun()
    if local_err is not None:
        raise RuntimeError(local_err)
    if proc.returncode not in (0, None) and proc.returncode != 0:
        err = ""
        try:
            err = proc.stderr.read()[:600] if proc.stderr else ""
        except Exception:
            err = ""
        raise RuntimeError("opencode завершился с ошибкой (код %s). %s" % (proc.returncode, err))


def run_pipeline(chat, send):
    if not chat.get("agents"):
        send({"type": "error", "text": "Сначала настройте агентов в параметрах чата (шестерёнка)."})
        return
    RUN["stop"].clear()
    RUN["active"] = True
    RUN["chat_id"] = chat["id"]
    try:
        MAX_HARD = 6
        try:
            max_rounds = int(chat.get("max_rounds") or 4)
        except Exception:
            max_rounds = 4
        max_rounds = max(1, min(MAX_HARD, max_rounds))
        round_answers = []
        for rnd in range(max_rounds):
            if RUN["stop"].is_set():
                break
            this_round = []
            for ag in chat["agents"]:
                if RUN["stop"].is_set():
                    break
                name = (ag.get("name") or "Агент").strip() or "Агент"
                role = ag.get("role") or ""
                model = (ag.get("model") or "").strip()
                mode = (ag.get("mode") or "plan").strip().lower()
                agent_id = AGENT_NAME
                prompt = build_prompt(role, chat.get("transcript", ""), chat.get("behavior", ""))
                send({
                    "type": "step_start",
                    "agent": name,
                    "role": role,
                    "model": model,
                    "mode": mode,
                    "round": rnd + 1,
                    "prompt": prompt,
                })
                buf = []

                def on_token(t, _buf=buf):
                    _buf.append(t)
                    send({"type": "token", "agent": name, "text": t})

                def on_think(t):
                    send({"type": "think", "agent": name, "text": t})

                def on_step_start():
                    pass

                def on_step_done():
                    pass

                try:
                    run_opencode(prompt, model, on_token, on_step_start, on_step_done, on_think, agent_id)
                except StopRun:
                    send({"type": "stopped", "agent": name})
                    return
                except RuntimeError as e:
                    send({"type": "error", "agent": name, "text": str(e)})
                    return

                full = "".join(buf)
                clean = strip_think_block(full)
                send({"type": "step_done", "agent": name, "text": clean})
                chat.setdefault("transcript", "")
                chat["transcript"] += "\n\n=== Ответ агента '%s' (круг %d) ===\n%s\n" % (name, rnd + 1, clean)
                chat.setdefault("messages", []).append({
                    "role": "agent", "name": name, "model": model, "text": clean, "prompt": prompt,
                    "mode": mode, "round": rnd + 1,
                })
                this_round.append(clean)
            round_answers.append(this_round)
            if rnd + 1 >= max_rounds:
                break
            if "?" not in "\n".join(this_round):
                break
            send({"type": "info", "text": "Агенты задали уточняющие вопросы — продолжаю обсуждение (круг %d)..." % (rnd + 2)})
            save_chats()
    finally:
        RUN["active"] = False
        RUN["chat_id"] = None


class Handler(BaseHTTPRequestHandler):
    def _send_sse(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

    def _json(self, obj, code=200):
        payload = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _body(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b""
        return json.loads(raw.decode("utf-8")) if raw else {}

    def do_GET(self):
        if self.path.startswith("/api/models"):
            ensure_models()
            with MODELS_LOCK:
                payload = json.dumps(MODELS, ensure_ascii=False)
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload.encode("utf-8"))))
            self.end_headers()
            self.wfile.write(payload.encode("utf-8"))
            return
        if self.path == "/api/chats":
            with LOCK:
                lst = [{"id": i, "name": CHATS[i]["name"]} for i in CHATS_ORDER]
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(json.dumps(lst).encode("utf-8"))))
            self.end_headers()
            self.wfile.write(json.dumps(lst).encode("utf-8"))
            return
        m = re.match(r"^/api/chats/([^/]+)$", self.path)
        if m:
            with LOCK:
                chat = CHATS.get(m.group(1))
                payload = json.dumps(chat, ensure_ascii=False) if chat else "null"
            self.send_response(200 if chat else 404)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload.encode("utf-8"))))
            self.end_headers()
            self.wfile.write(payload.encode("utf-8"))
            return
        if self.path in ("/", "/index.html"):
            try:
                with open(os.path.join(HERE, "index.html"), "r", encoding="utf-8") as f:
                    body = f.read()
            except Exception:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body.encode("utf-8"))))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(body.encode("utf-8"))
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == "/api/chats":
            cid = new_id()
            with LOCK:
                CHATS[cid] = {
                    "id": cid, "name": "Новый чат", "agents": [
                        {"name": "", "role": "", "model": ""},
                        {"name": "", "role": "", "model": ""},
                    ],
                    "messages": [], "transcript": "", "behavior": "", "rounds": 1, "created": time.time(),
                }
                if cid not in CHATS_ORDER:
                    CHATS_ORDER.append(cid)
                save_chats()
            self._json({"id": cid})
            return
        m = re.match(r"^/api/chats/([^/]+)/send$", self.path)
        if m:
            chat = CHATS.get(m.group(1))
            if not chat:
                self.send_error(404)
                return
            data = self._body()
            msg = (data.get("message") or "").strip()
            if not msg:
                self.send_error(400)
                return
            files = data.get("files") or []
            fnames = [f.get("name", "") for f in files if f.get("name")]
            file_block = ""
            if files:
                parts = ["--- %s ---\n%s" % (f.get("name", "file"), (f.get("content") or "")) for f in files]
                file_block = "\n\nПрикреплённые файлы:\n" + "\n\n".join(parts)
            user_text = msg + file_block
            chat.setdefault("messages", [])
            chat["messages"].append({"role": "user", "text": msg, "files": [{"name": n} for n in fnames]})
            if chat["name"] == "Новый чат":
                chat["name"] = (msg[:42] + ("…" if len(msg) > 42 else ""))
            chat.setdefault("transcript", "")
            if not chat["transcript"]:
                chat["transcript"] = "Общая задача:\n" + user_text
            else:
                chat["transcript"] += "\n\nСообщение пользователя:\n" + user_text
            save_chats()
            self._send_sse()

            def send(obj):
                try:
                    self.wfile.write(("data: " + json.dumps(obj, ensure_ascii=False) + "\n\n").encode("utf-8"))
                    self.wfile.flush()
                except Exception:
                    pass

            try:
                run_pipeline(chat, send)
                send({"type": "done"})
            except Exception as e:
                send({"type": "error", "text": str(e)})
                send({"type": "done"})
            return
        m = re.match(r"^/api/chats/([^/]+)/stop$", self.path)
        if m:
            RUN["stop"].set()
            proc = RUN["proc"]
            if proc is not None:
                try:
                    proc.kill()
                except Exception:
                    pass
            self._json({"ok": True})
            return
        self.send_error(404)

    def do_PUT(self):
        m = re.match(r"^/api/chats/([^/]+)$", self.path)
        if m:
            chat = CHATS.get(m.group(1))
            if not chat:
                self.send_error(404)
                return
            data = self._body()
            if "name" in data:
                chat["name"] = data["name"].strip() or chat["name"]
            if "agents" in data and isinstance(data["agents"], list):
                chat["agents"] = data["agents"]
            if "behavior" in data:
                chat["behavior"] = data["behavior"]
            if "rounds" in data:
                chat["rounds"] = data["rounds"]
            save_chats()
            self._json({"ok": True, "name": chat["name"]})
            return
        self.send_error(404)

    def do_DELETE(self):
        m = re.match(r"^/api/chats/([^/]+)$", self.path)
        if m:
            cid = m.group(1)
            with LOCK:
                if cid in CHATS:
                    del CHATS[cid]
                    CHATS_ORDER.remove(cid)
                    save_chats()
            self._json({"ok": True})
            return
        self.send_error(404)

    def log_message(self, *args):
        pass


def main():
    load_chats()
    port = int(os.environ.get("PORT", "8787"))
    srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print("AI-orchestrator запущен: http://127.0.0.1:%d" % port)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()


if __name__ == "__main__":
    main()
