# Charla

Spanish conversation companion for B1→B2 learners: AI role-play that remembers your recurring mistakes, plus "explain it like a tutor" for real content (idioms, slang). Portfolio project, built by and for one learner first.

## Layout

- `web/` — Vite + React + TypeScript SPA. In dev, `/api/*` is proxied to the API (see `web/vite.config.ts`).
- `api/` — FastAPI (Python 3.12, managed with `uv`), SQLAlchemy 2 async + asyncpg, Alembic migrations, Anthropic SDK.
- `docker-compose.yml` — local Postgres 17 on host port **5442** (5432 is commonly taken by other local Postgres instances).

## Commands

API (run from `api/`):
- `uv sync` — install deps
- `uv run fastapi dev app/main.py` — dev server on :8000
- `uv run pytest` — tests
- `uv run ruff check .` — lint; `uv run mypy app` — types (strict)
- `uv run alembic revision --autogenerate -m "<msg>"` then `uv run alembic upgrade head` — migrations (needs `docker compose up -d db`)

Web (run from `web/`):
- `npm run dev` — dev server on :5173
- `npm test` — Vitest; `npm run lint` — oxlint; `npm run build` — type-check + build

CI (`.github/workflows/ci.yml`) runs lint, types and tests for both halves on every push/PR to `main`.

## Conventions

- **Logging**: use `structlog` (`structlog.get_logger()`), never `print`. Bind ids as keyword args (`log.info("conversation_created", conversation_id=...)`). Never log full user-authored message text; log lengths or ids.
- **LLM output is structured**: ask the model for JSON that validates against a Pydantic model in `api/app/schemas/`. `CorrectionReport` is the central contract — the UI, eval set and learner memory all depend on it.
- **Config** comes from `app/config.py` (`pydantic-settings`, `.env` in `api/`). Never read `os.environ` directly. Copy `api/.env.example` to `api/.env`.
- **Tests** live in `api/tests/` and next to components in `web/src/` as `<name>.test.tsx`. Mock the Anthropic SDK in unit tests; real-model checks belong in the eval harness, not the test suite.
- **Mobile-friendly UI**: design for a narrow viewport first.

## Product notes

- Learner is B1; replies should target B1+1 (comprehensible input). Dialect is a user setting (not yet decided).
- Correction quality is the hard part: catch real errors, don't nitpick, don't invent errors.
