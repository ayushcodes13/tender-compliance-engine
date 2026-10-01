#!/usr/bin/env bash
# =============================================================================
# Run database migrations (CP47 deployment helper)
# =============================================================================
# This script is intended for use in a migration job / init-container during
# deployment.  It runs alembic upgrade head against the configured DATABASE_URL.
#
# Usage:
#   ./scripts/migrate.sh
#
# Environment:
#   DATABASE_URL — PostgreSQL connection string (required)
# =============================================================================
set -euo pipefail

cd "$(dirname "$0")/.."

if [ -z "${DATABASE_URL:-}" ]; then
    echo "ERROR: DATABASE_URL environment variable is required." >&2
    exit 1
fi

echo "Running migrations against ${DATABASE_URL}..."
cd apps/api

alembic upgrade head

echo "Migrations complete. Current version:"
alembic current
