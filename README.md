# Charla

A Spanish conversation companion for intermediate (B1→B2) learners.

- **Conversation practice that knows you:** role-play scenarios with inline corrections; recurring mistakes feed future conversations.
- **Learn from real content:** paste an article or subtitles, get idioms and slang explained in context, and turn them into spaced-repetition cards.

## Quick start

Prerequisites: Node 24, Python 3.12+ with [uv](https://docs.astral.sh/uv/), Docker.

```sh
docker compose up -d db                 # Postgres on localhost:5442
cd api
cp .env.example .env                    # add ANTHROPIC_API_KEY
uv sync
uv run alembic upgrade head
uv run fastapi dev app/main.py          # http://localhost:8000/docs

cd ../web
npm install
npm run dev                             # http://localhost:5173
```

See `CLAUDE.md` for commands and conventions.

## Roadmap

1. Typed conversation
2. Inline corrections and end-of-conversation summary
3. Level adaptation
4. Text content and quizzing
5. Voice in and out
6. Audio and video content
7. Learner memory

Details, scope and open questions: [docs/roadmap.md](docs/roadmap.md).
