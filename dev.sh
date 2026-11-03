#!/usr/bin/env bash
# Start Postgres (docker), the API (:8000) and the web app (:5173). Ctrl+C stops the API and web;
# Postgres is left running (stop it with `docker compose down`).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

command -v docker >/dev/null || { echo "docker not found" >&2; exit 1; }
command -v uv >/dev/null || { echo "uv not found" >&2; exit 1; }
command -v npm >/dev/null || { echo "npm not found" >&2; exit 1; }

if [ ! -f api/.env ]; then
  cp api/.env.example api/.env
  echo "Created api/.env from .env.example (set ANTHROPIC_API_KEY there)."
fi

echo "==> Postgres"
docker compose up -d --wait db

echo "==> Dependencies"
(cd api && uv sync --quiet)
[ -d web/node_modules ] || (cd web && npm install)

pids=()
cleanup() {
  trap - INT TERM EXIT
  echo; echo "Stopping API and web..."
  for pid in "${pids[@]:-}"; do
    [ -n "$pid" ] && kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
}
trap cleanup INT TERM EXIT

echo "==> API    http://localhost:8000  (docs: /docs)"
(cd api && exec uv run fastapi dev app/main.py) &
pids+=($!)

echo "==> Web    http://localhost:5173"
(cd web && exec npm run dev) &
pids+=($!)

# Exit as soon as either process dies.
while kill -0 "${pids[0]}" 2>/dev/null && kill -0 "${pids[1]}" 2>/dev/null; do
  sleep 1
done
