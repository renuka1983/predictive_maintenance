#!/usr/bin/env bash
# Generate and load the three pilot tenants (Levels 1, 2 and 3).
set -euo pipefail

cd "$(dirname "$0")/.."

: "${DATABASE_URL:=postgresql+psycopg2://postgres:postgres@localhost:5432/manufacturing_ai}"
export DATABASE_URL

echo "==> Loading into ${DATABASE_URL%%:*}..."
exec python -m ml.data_generation.load_to_db --tenant "${1:-all}" --reset
