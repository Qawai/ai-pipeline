#!/bin/bash
set -e
if ! command -v opencode >/dev/null 2>&1 && [ ! -x "$HOME/bin/opencode" ]; then
  echo "Downloading opencode..."
  curl -fsSL -o /tmp/oc.tar.gz https://github.com/anomalyco/opencode/releases/latest/download/opencode-linux-x64.tar.gz
  mkdir -p /tmp/oc && tar -xzf /tmp/oc.tar.gz -C /tmp/oc
  BIN=$(find /tmp/oc -name opencode -type f | head -n1)
  mkdir -p "$HOME/bin"
  cp "$BIN" "$HOME/bin/opencode"
  chmod +x "$HOME/bin/opencode"
  rm -rf /tmp/oc /tmp/oc.tar.gz
  echo "opencode installed"
fi
export PATH="$HOME/bin:$PATH"
export PORT="${PORT:-5000}"
exec python server.py
