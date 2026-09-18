# AgentHarbor: local setup on Windows

This generated app has a FastAPI backend, Next.js frontend, login, admin and
OpenAI chat. RAG, billing, Redis and OAuth were not enabled.

## Environment files

- `backend/.env`: database settings, application secrets and `OPENAI_API_KEY`.
- `frontend/.env.local`: local backend and WebSocket URLs; no provider secrets.

Application secrets have already been generated. Add your AI key locally and
set `AI_MODEL` to a model your provider account can access.

## Hosted PostgreSQL

A hosted PostgreSQL database works without Docker or a local PostgreSQL install.
Copy its database connection values, not its website/dashboard URL, into
`backend/.env`:

```dotenv
POSTGRES_HOST=your-database-host
POSTGRES_PORT=5432
POSTGRES_USER=your-database-user
POSTGRES_PASSWORD="your-database-password"
POSTGRES_DB=your-database-name
POSTGRES_SSL_MODE=require
```

Follow your provider's TLS/certificate requirements; `verify-full` is also
supported. Prefer the direct database or session-pooler endpoint for this setup;
transaction-pooler endpoints may require additional driver configuration.
Use a dedicated development database. The code safely URL-encodes credentials.

The default Docker Compose files override POSTGRES_HOST to `db` and start a local
database. For hosted PostgreSQL, run the backend directly as shown below.

## Run

From `my_ai_app`, in PowerShell:

```powershell
cd backend
# This machine has DEBUG=release in its environment; override it for this shell.
$env:DEBUG='true'
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Run migrations only after filling database credentials. Then in another terminal:

```powershell
cd frontend
npm.cmd run dev -- --hostname localhost
```

- Frontend: http://localhost:3000
- API docs: http://localhost:8000/docs

Register an account once database migrations succeed. Login and saved
conversations require a reachable database; AI responses also require a valid
provider key. A running server alone does not establish that these features work.

On this machine Docker reported that Virtual Machine Platform is not enabled.
That must be resolved before using the local Docker database option.

Local PostgreSQL is configured on port 5432 with database `my_ai_app`. The display name is AgentHarbor. See [the runbook](../docs/runbooks/local-development.md) and [quality policy](../docs/quality.md) for verification and recovery.
