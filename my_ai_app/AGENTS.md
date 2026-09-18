# AGENTS.md

This file provides guidance for AI coding agents (Codex, Copilot, Cursor, Zed, OpenCode).

## Project Overview

**my_ai_app** - FastAPI application generated with [Full-Stack AI Agent Template](https://github.com/vstorm-co/full-stack-ai-agent-template).

**Stack:** FastAPI + Pydantic v2, PostgreSQL
, JWT + API Key auth
, pydantic_ai (openai), Next.js 15 (i18n)

## Commands

```bash
# Run server
cd backend && uv run uvicorn app.main:app --reload

# Tests & lint
pytest
ruff check . --fix && ruff format .

# Migrations
uv run alembic upgrade head
uv run alembic revision --autogenerate -m "Description"
```

## Project Structure

```
backend/app/
├── api/routes/v1/    # Endpoints
├── services/         # Business logic
├── repositories/     # Data access
├── schemas/          # Pydantic models
├── db/models/        # DB models
├── agents/           # AI agents
└── commands/         # CLI commands
```

## Key Conventions

- `db.flush()` in repositories, not `commit()`
- Services raise `NotFoundError`, `AlreadyExistsError`
- Separate `Create`, `Update`, `Response` schemas
- Commands auto-discovered from `app/commands/`

## More Info

- `docs/architecture.md` - Architecture details
- `docs/adding_features.md` - How to add features
- `docs/testing.md` - Testing guide
- `docs/patterns.md` - Code patterns

## Required workflow for this checkout

The product is **AgentHarbor**, located in `my_ai_app/` from the repository root. Keep display branding separate from database and package identifiers.

- Read the applicable architecture documentation before changing module boundaries: `../docs/architecture.md`.
- Read `../docs/quality.md` before implementation and run the relevant checks before completion. Every behavior change needs normal-path and failure/authorization regression coverage where relevant.
- Consult `../docs/decisions/` for architecture choices and `../docs/runbooks/` for startup, recovery or deployment work. Update these documents when behavior changes.
- Keep database operations in repositories, business rules in services, and HTTP concerns in routes. Never trust a client-supplied role for public registration.
- Never print or commit `.env` files, credentials, provider keys, database dumps, user uploads or browser authentication state.
- Fix failures caused by your changes; do not disable checks. Report checks run, outcomes and any unverified integrations. A missing API key must be reported, not replaced by fake success.
- Use migrations for schema changes. Do not reset databases or remove user data as automatic repair.
- These instructions guide agent work; they do not provide continuous monitoring.
