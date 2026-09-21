#!/usr/bin/env bash
# Run the backend test-suite against in-memory SQLite (no Docker required).
set -euo pipefail

cd "$(dirname "$0")/.."

export DATABASE_URL="sqlite://"
exec python -m pytest backend/app/tests -v --cov=backend/app --cov-report=term-missing "$@"
