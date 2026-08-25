// Cloudflare Worker: CORS-прокси к OpenCode Zen + (опционально) лог посетителей для админки.
// Деплой без обязательных настроек. KV/VISITS и ADMIN_CODE — опциональны (для админки позже).

const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
  'Access-Control-Allow-Headers': 'content-type, authorization',
};

async function logVisit(req, env) {
  if (!env.VISITS) return;
  try {
    const ip = req.headers.get('cf-connecting-ip') || '';
    const country = req.headers.get('cf-ipcountry') || '';
    const asn = req.headers.get('cf-asn') || '';
    const ua = req.headers.get('user-agent') || '';
    const ref = req.headers.get('referer') || '';
    const now = new Date().toISOString();
    const logs = await env.VISITS.get('logs', { type: 'json' }) || [];
    logs.push({ time: now, ip, country, asn, ua, ref });
    // оставляем последние 500
    if (logs.length > 500) logs.splice(0, logs.length - 500);
    await env.VISITS.put('logs', JSON.stringify(logs));
  } catch (e) { /* best-effort */ }
}

export default {
  async fetch(req, env, ctx) {
    const url = new URL(req.url);

    if (req.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: CORS });
    }

    // Админка: список посетителей по коду
    if (url.pathname === '/admin' && req.method === 'GET') {
      const code = url.searchParams.get('code');
      if (!env.ADMIN_CODE || code !== env.ADMIN_CODE) {
        return new Response('Forbidden', { status: 403, headers: CORS });
      }
      const logs = env.VISITS ? (await env.VISITS.get('logs', { type: 'json' }) || []) : [];
      return new Response(JSON.stringify(logs), {
        headers: { ...CORS, 'Content-Type': 'application/json' },
      });
    }

    // Прокси к OpenCode Zen
    if (req.method === 'POST' && url.pathname.startsWith('/zen/') && env.VISITS) {
      ctx.waitUntil(logVisit(req, env));
    }

    const target = 'https://opencode.ai' + url.pathname + url.search;
    const upstream = await fetch(target, {
      method: req.method,
      headers: req.headers,
      body: req.body,
      redirect: 'follow',
    });
    const resp = new Response(upstream.body, upstream);
    resp.headers.set('Access-Control-Allow-Origin', '*');
    return resp;
  },
};
