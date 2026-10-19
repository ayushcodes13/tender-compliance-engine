#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="${TCE_DATA_DIR:-$ROOT_DIR/.local/mvp}"
PID_FILE="$DATA_DIR/mvp.pid"

if [[ ! -f "$PID_FILE" ]]; then
  printf 'The local MVP is not running.\n'
  exit 0
fi

pid="$(<"$PID_FILE")"
if [[ ! "$pid" =~ ^[0-9]+$ ]]; then
  printf 'Ignoring invalid local MVP pid file: %s\n' "$PID_FILE" >&2
  exit 1
fi

process_command="$(ps -p "$pid" -o command= 2>/dev/null || true)"
if [[ "$process_command" != *"$ROOT_DIR/scripts/mvp-start.sh"* ]]; then
  unlink "$PID_FILE" 2>/dev/null || true
  printf 'The local MVP is not running.\n'
  exit 0
fi

kill -TERM "$pid"
for _ in $(seq 1 20); do
  if ! kill -0 "$pid" 2>/dev/null; then
    printf 'Local MVP stopped.\n'
    exit 0
  fi
  sleep 0.25
done

printf 'The local MVP did not stop within 5 seconds. Press Ctrl+C in its terminal.\n' >&2
exit 1
