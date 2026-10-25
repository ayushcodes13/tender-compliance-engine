#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
mkdir -p .local/logs .local/npm-cache

if [[ -f .env.local ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env.local
  set +a
fi

command -v node >/dev/null || { echo "Install Node.js 22.13+ first." >&2; exit 1; }
command -v npm >/dev/null || { echo "Install npm first." >&2; exit 1; }
if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  echo "Add OPENAI_API_KEY to .env.local before starting the extraction demo." >&2
  exit 1
fi

if [[ ! -f apps/web/node_modules/next/package.json ]]; then
  npm_config_cache="$ROOT_DIR/.local/npm-cache" npm ci --prefix apps/web --no-audit --no-fund --prefer-offline
fi

if [[ -f .local/web.pid ]] && kill -0 "$(cat .local/web.pid)" 2>/dev/null; then
  echo "Tender Review is already running: http://127.0.0.1:3307"
  exit 0
fi

node apps/web/node_modules/next/dist/bin/next dev apps/web --hostname 127.0.0.1 --port 3307 >.local/logs/web.log 2>&1 &
echo "$!" > .local/web.pid

for attempt in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:3307/ >/dev/null 2>&1; then
    echo "Tender Review is ready: http://127.0.0.1:3307"
    exit 0
  fi
  sleep 1
done

echo "The app did not become ready. Recent log:" >&2
tail -n 100 .local/logs/web.log >&2 || true
exit 1
