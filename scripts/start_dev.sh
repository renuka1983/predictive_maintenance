#!/usr/bin/env bash
# Bring up the full local stack.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> Starting PostgreSQL, backend and frontend"
docker compose up -d --build

echo "==> Waiting for the API to become healthy"
for _ in $(seq 1 60); do
  if curl -fsS http://localhost:8000/health >/dev/null 2>&1; then
    echo "    API is up"
    break
  fi
  sleep 2
done

cat <<'MSG'

Ready:
  API docs     http://localhost:8000/docs
  Frontend     http://localhost:3000
  PgAdmin      docker compose --profile tools up -d pgadmin  ->  http://localhost:5050

Next, load the pilot tenants (Levels 1, 2 and 3):
  ./scripts/load_pilot_data.sh
MSG
