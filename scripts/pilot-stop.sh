#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
pid_file=".local/web.pid"
if [[ -f "$pid_file" ]]; then
  pid="$(cat "$pid_file")"
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid" || true
    echo "Stopped Tender Review (PID $pid)."
  fi
  rm -f "$pid_file"
fi
echo "No local tender data is stored by the app."
