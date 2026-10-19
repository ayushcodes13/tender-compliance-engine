#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="${TCE_DATA_DIR:-$ROOT_DIR/.local/mvp}"
ENV_FILE="${TCE_ENV_FILE:-$ROOT_DIR/.env}"
PID_FILE="$DATA_DIR/mvp.pid"
API_PID=""
WEB_PID=""

fail() {
  printf 'MVP startup failed: %s\n' "$1" >&2
  exit 1
}

stop_services() {
  local exit_code=$?
  trap - EXIT INT TERM
  for pid in "$WEB_PID" "$API_PID"; do
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      kill -TERM "$pid" 2>/dev/null || true
    fi
  done
  for pid in "$WEB_PID" "$API_PID"; do
    if [[ -n "$pid" ]]; then
      wait "$pid" 2>/dev/null || true
    fi
  done
  if [[ -f "$PID_FILE" ]] && [[ "$(<"$PID_FILE")" == "$$" ]]; then
    unlink "$PID_FILE" 2>/dev/null || true
  fi
  exit "$exit_code"
}

trap stop_services EXIT
trap 'exit 0' INT TERM

command -v uv >/dev/null 2>&1 || fail "Install uv, then run make start again."
command -v node >/dev/null 2>&1 || fail "Install Node.js, then run make start again."
command -v npm >/dev/null 2>&1 || fail "Install npm, then run make start again."
command -v curl >/dev/null 2>&1 || fail "curl is required for local readiness checks."

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

mkdir -p "$DATA_DIR/files"
if [[ -f "$PID_FILE" ]]; then
  previous_pid="$(<"$PID_FILE")"
  previous_command="$(ps -p "$previous_pid" -o command= 2>/dev/null || true)"
  if [[ "$previous_command" == *"$ROOT_DIR/scripts/mvp-start.sh"* ]]; then
    fail "The local MVP is already running with PID $previous_pid."
  fi
fi
printf '%s\n' "$$" > "$PID_FILE"
export APP_ENV=development
export AUTH_MODE=single_workspace
export LOCAL_MVP_MODE=true
export API_HOST=127.0.0.1
export API_PORT=8000
export DATABASE_URL="sqlite+aiosqlite:///$DATA_DIR/tender.sqlite3"
export REDIS_URL=""
export OBJECT_STORAGE_ENDPOINT=""
export OBJECT_STORAGE_LOCAL_PATH="$DATA_DIR/files"
export MALWARE_SCANNER_MODE=fake
export CORS_ALLOWED_ORIGINS="http://127.0.0.1:3307,http://localhost:3307"
export BACKEND_INTERNAL_URL=http://127.0.0.1:8000
export NEXT_TELEMETRY_DISABLED=1

if [[ ! -d "$ROOT_DIR/apps/web/node_modules" ]]; then
  printf 'Installing web dependencies from the lockfile...\n'
  (cd "$ROOT_DIR/apps/web" && npm ci)
fi

printf 'Preparing the local SQLite database...\n'
(cd "$ROOT_DIR/apps/api" && uv run --extra local --python 3.12 alembic upgrade head)

printf 'Starting API and embedded processing worker...\n'
(
  cd "$ROOT_DIR/apps/api"
  exec uv run --extra local --python 3.12 uvicorn tender_compliance_api.main:app \
    --host 127.0.0.1 --port 8000
) &
API_PID=$!

api_ready=false
for _ in $(seq 1 90); do
  if curl -fsS http://127.0.0.1:8000/ready >/dev/null 2>&1; then
    api_ready=true
    break
  fi
  if ! kill -0 "$API_PID" 2>/dev/null; then
    fail "The API stopped during startup. Check the API output above."
  fi
  sleep 1
done
[[ "$api_ready" == true ]] || fail "The API did not become ready within 90 seconds."

printf 'Starting the web app...\n'
(
  cd "$ROOT_DIR/apps/web"
  exec ./node_modules/.bin/next dev --hostname 127.0.0.1 --port 3307
) &
WEB_PID=$!

web_ready=false
for _ in $(seq 1 90); do
  if curl -fsS http://127.0.0.1:3307/ >/dev/null 2>&1; then
    web_ready=true
    break
  fi
  if ! kill -0 "$WEB_PID" 2>/dev/null; then
    fail "The web app stopped during startup. Check the web output above."
  fi
  sleep 1
done
[[ "$web_ready" == true ]] || fail "The web app did not become ready within 90 seconds."

printf '\nTender Compliance Engine is ready at http://127.0.0.1:3307\n'
printf 'API readiness: http://127.0.0.1:8000/ready\n'
printf 'Local data: %s\n' "$DATA_DIR"
printf 'Press Ctrl+C here to stop both services.\n\n'

wait "$WEB_PID"
