#!/bin/bash
set -e
install_opencode() {
  local BIN="$1"
  if [ -x "$BIN" ]; then return 0; fi
  echo "downloading opencode..."
  curl -fsSL -o /tmp/oc.tar.gz https://github.com/anomalyco/opencode/releases/latest/download/opencode-linux-x64.tar.gz
  mkdir -p "$(dirname "$BIN")" /tmp/oc
  tar -xzf /tmp/oc.tar.gz -C /tmp/oc
  local SRC
  SRC=$(find /tmp/oc -type f -name opencode | head -n1)
  cp "$SRC" "$BIN" && chmod +x "$BIN"
  rm -rf /tmp/oc /tmp/oc.tar.gz
  echo "opencode installed at $BIN"
}
for D in /usr/local/bin "$HOME/bin" "$(cd "$(dirname "$0")" && pwd)/bin"; do
  if install_opencode "$D/opencode" 2>/dev/null; then
    export PATH="$D:$PATH"
    break
  fi
done
command -v opencode >/dev/null 2>&1 || { echo "opencode not found"; exit 1; }
PORT="${PORT:-5000}"
export PORT
exec python3 server.py
