#!/bin/bash
set -e
BIN=/usr/local/bin/opencode
if [ ! -x "$BIN" ]; then
  echo "downloading opencode..."
  curl -fsSL -o /tmp/oc.tar.gz https://github.com/anomalyco/opencode/releases/latest/download/opencode-linux-x64.tar.gz
  mkdir -p /tmp/oc && tar -xzf /tmp/oc.tar.gz -C /tmp/oc
  SRC=$(find /tmp/oc -type f -name opencode | head -n1)
  cp "$SRC" "$BIN" && chmod +x "$BIN"
  rm -rf /tmp/oc /tmp/oc.tar.gz
fi
opencode --version || true
