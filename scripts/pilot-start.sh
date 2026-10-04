#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

fail() {
  printf 'Tender Compliance Engine pilot start failed: %s\n' "$1" >&2
  exit 1
}

command -v docker >/dev/null 2>&1 || fail "Docker is not installed or not on PATH."
docker compose version >/dev/null 2>&1 || fail "Docker Compose v2 is required."
command -v curl >/dev/null 2>&1 || fail "curl is required for the readiness check."

if ! docker info >/dev/null 2>&1; then
  fail "Docker is installed but the Docker daemon is not reachable."
fi

if ! docker compose config >/dev/null 2>/tmp/tce-compose-config.err; then
  if grep -q "OPENAI_API_KEY" /tmp/tce-compose-config.err; then
    cat >&2 <<'EOF'
OPENAI_API_KEY is the only external secret required for the bundled pilot.

Start with either:

  OPENAI_API_KEY=sk-... make pilot-start

or put OPENAI_API_KEY in a local .env file and run:

  make pilot-start
EOF
  else
    cat /tmp/tce-compose-config.err >&2
  fi
  exit 1
fi

printf 'Starting Tender Compliance Engine...\n'
docker compose up -d --build

ready_file="$(mktemp)"
trap 'rm -f "$ready_file" /tmp/tce-compose-config.err' EXIT

for attempt in $(seq 1 72); do
  if curl --fail --silent --show-error \
    http://localhost:3000/api/backend/ready \
    -o "$ready_file" 2>/dev/null; then
    if python3 - "$ready_file" <<'PY' 2>/dev/null
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text())
assert payload["status"] == "ready", payload
PY
    then
      printf '\nTender Compliance Engine is ready.\n'
      printf 'Open: http://localhost:3000\n'
      printf 'Readiness: http://localhost:3000/api/backend/ready\n'
      exit 0
    fi
  fi

  if (( attempt % 12 == 0 )); then
    printf 'Still starting (%s/72)...\n' "$attempt"
  fi
  sleep 5
done

printf '\nThe stack started but did not become ready in time.\n' >&2
docker compose ps >&2 || true
docker compose logs --no-color --tail=200 >&2 || true
exit 1
