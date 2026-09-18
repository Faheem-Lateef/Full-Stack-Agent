Ã¯Â»Â¿# AgentHarbor | Full-Stack-Agent

AgentHarbor is your workspace for AI conversations and everyday work. This repository includes the runnable app and the generator it was built from.

This repository contains a **project generator**. It creates a separate application
with a Python/FastAPI backend, an optional Next.js frontend, and the integrations
you choose. You own and can edit the generated code.

The generator is published as `fastapi-fullstack`. It is not itself the chat app.

## What problem does it solve?

An AI product needs more than a model API call. It usually needs accounts, a user
interface, saved conversations, database migrations, deployment configuration,
and a way to investigate errors. This template supplies that foundation so you can
focus on your product's features.

Example applications include a customer-support assistant, an internal document
search tool, or a subscription-based AI service.

## Start here: your existing app

**AgentHarbor** is the application in **`my_ai_app/`**. The website uses the AgentHarbor name; the folder and database retain their original technical names.
**Do not run the generator again with that name.** Open that folder to work on the
application. Use the repository root when working on the generator itself.

Your app includes:

- FastAPI backend and Next.js frontend.
- User authentication and an admin panel.
- PostgreSQL storage and database migrations.
- PydanticAI with OpenAI integration and streaming chat.

RAG/document search, billing, teams, Redis, Google login, and external monitoring
were not enabled in this local configuration. They are available template options,
not features automatically included in every generated app.

| Location | Purpose |
| --- | --- |
| `my_ai_app/backend/` | Application APIs, database models, and AI logic |
| `my_ai_app/frontend/` | Website and chat interface |
| `my_ai_app/backend/.env` | Database credentials, AI key, and internal secrets |
| `my_ai_app/frontend/.env.local` | Frontend connection settings |
| `fastapi_gen/` | Generator implementation |
| `template/` | Source templates used to create new applications |
| `tests/` | Tests for the generator and its templates |

See [the local setup guide](my_ai_app/LOCAL_SETUP.md) for additional Windows notes.
The `my_ai_app/` folder is specific to this checkout; a fresh upstream download
starts with the generator only.

## Configure your environment

The existing app's environment files have been created. Internal application
secrets have been generated; add your own database credentials and AI key locally.
Do not put provider keys in frontend variables or commit `.env` files.

### Backend: `my_ai_app/backend/.env`

For a local PostgreSQL database, the initial development settings are:

```dotenv
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=my_ai_app
POSTGRES_SSL_MODE=prefer
```

These values do not create a database. A matching PostgreSQL server must be
running, or you must replace them with a hosted database's connection details.

Also configure:

```dotenv
OPENAI_API_KEY=your-api-key
AI_MODEL=your-accessible-model-name
```

Replace the example values rather than copying them literally. Keep the generated
`SECRET_KEY` and `API_KEY`; these are application secrets, not your AI-provider key.

### Can I use a database managed through a browser?

Yes. Use a **hosted PostgreSQL database** and copy its connection settings from
its dashboard:

```dotenv
POSTGRES_HOST=your-database-host
POSTGRES_PORT=5432
POSTGRES_USER=your-database-user
POSTGRES_PASSWORD="your-database-password"
POSTGRES_DB=your-database-name
POSTGRES_SSL_MODE=require
```

Use the database hostname, not the dashboard URL. Follow the provider's port and
TLS/certificate requirements. Prefer a direct or session-pooler connection;
transaction pooling may need additional driver configuration.

The SSL setting and safe credential encoding were added to **this local
`my_ai_app` backend**. They have not been added to the generator's source template.

For hosted PostgreSQL, run the backend directly using the commands below. The
supplied Docker Compose configuration starts a local database and overrides the
backend database hostname to `db`.

### Frontend: `my_ai_app/frontend/.env.local`

```dotenv
BACKEND_URL=http://localhost:8000
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=ws://localhost:8000
```

The initial URLs are already configured. Restart the affected server after changing
its environment file. Production changes to `NEXT_PUBLIC_*` variables require a
new frontend build.

## Run the existing app on Windows

Dependencies were installed during local setup. If the servers are already
running, use their URLs instead of starting another copy on the same ports.

### 1. Start the backend

Open PowerShell in this repository's root:

```powershell
cd my_ai_app/backend
$env:DEBUG = 'true'

# Run after configuring a reachable development database.
.\.venv\Scripts\python.exe -m alembic upgrade head

.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

The explicit `DEBUG` setting avoids a conflicting `DEBUG=release` environment
variable found on this machine. Run migrations against a dedicated development
database. If they fail, fix the connection before expecting login to work.

### 2. Start the frontend

Open a second PowerShell terminal in the repository root:

```powershell
cd my_ai_app/frontend
npm.cmd run dev -- --hostname localhost
```

| Page | Address |
| --- | --- |
| Website | http://localhost:3000 |
| Login | http://localhost:3000/login |
| API documentation | http://localhost:8000/docs |
| API liveness | http://localhost:8000/api/v1/health |

Register an account after migrations succeed. Database-backed features require a
working database; AI responses also require a valid provider key and model access.
A healthy liveness endpoint confirms the server is running, not that every
integration is ready.

### If dependencies need reinstalling

From the generated app's backend directory:

```powershell
python -m uv sync
```

From its frontend directory:

```powershell
npm.cmd install
```

## Generate a different application

For a fresh setup, you need Python and `uv`. The generator supports Python 3.11+;
the generated backend's `pyproject.toml` defines its own minimum (3.12 by default).
For the frontend, use a supported Node.js LTS version compatible with its Next.js
version. Docker Desktop is needed only for a container-based setup.

From the repository root:

```powershell
python -m pip install uv
python -m uv sync

# Interactive feature selection:
python -m uv run fastapi-fullstack

# Or create a basic app explicitly, using an unused folder name:
python -m uv run fastapi-fullstack create another_ai_app --frontend nextjs --no-logfire --websockets --admin-panel
```

Then follow the README inside the generated folder. Inspect available options with:

```powershell
python -m uv run fastapi-fullstack create --help
python -m uv run fastapi-fullstack templates
```

## Optional capabilities

Choose only what your application needs. Framework/provider combinations and
feature dependencies are validated by the generator.

| Capability | Available options or examples |
| --- | --- |
| AI framework | PydanticAI, PydanticDeep, LangChain, LangGraph, DeepAgents |
| Model provider | OpenAI, Anthropic, Google, OpenRouter |
| Document search (RAG) | Parse documents, retrieve relevant content, and pass it to an agent |
| Vector storage | Milvus, Qdrant, ChromaDB, pgvector |
| Document sources | Local files, uploads, Google Drive, S3 |
| Accounts and SaaS | Google login, teams, Stripe billing, usage credits |
| Background processing | Queues and scheduled work; availability depends on configuration |
| Observability | Logfire, LangSmith, Sentry, Prometheus |
| Deployment | Docker Compose and optional Kubernetes configuration |

Credentials for optional services are needed only when those services are enabled.
The generated code remains editable; new features still need implementation,
configuration, and testing for your application.

## Testing and AI-assisted development

`AGENTS.md` provides instructions for coding assistants. The generated app also
contains testing and architecture guides. These files guide development; they do
not automatically monitor production or repair every problem.

Run generator checks from the repository root:

```powershell
python -m uv run pytest
python -m uv run ruff check .
python -m uv run ty check
```

Run application checks from `my_ai_app/backend`:

```powershell
$env:DEBUG = 'true'
.\.venv\Scripts\python.exe -m pytest
```

From `my_ai_app/frontend`:

```powershell
npm.cmd run type-check
npm.cmd run test:run
npm.cmd run build
```

Stop the frontend development server before a production build, since both use
`.next`. Some tests need services or fixtures; see the application's testing guide.

## Troubleshooting

| Problem | What to check |
| --- | --- |
| Docker reports no virtualization | Enable Windows Virtual Machine Platform and complete Docker/WSL setup, or use hosted PostgreSQL with the backend running directly. |
| Login or registration fails | Verify database settings and apply migrations. |
| AI replies fail | Check the backend provider key, model access, and provider error logs. |
| `DEBUG` is not a valid boolean | Set `$env:DEBUG='true'` in the backend terminal. |
| Frontend redirects repeatedly | Use `localhost:3000` consistently and start Next.js with `--hostname localhost`. |
| Connection refused | Confirm the relevant server is running and its port matches the environment file. |
| Download or DNS errors | Check network connectivity and retry dependency installation. |
| Address already in use | Check for an existing server before launching another copy. |

## Before production

This is a starting point with deployment tooling, not a guarantee of production
readiness. Validate authentication, authorization, migrations, backups, secrets,
HTTPS, monitoring, and your actual user journeys before deploying.

Replace development credentials and disable debug mode. Template-provided demo
accounts must not remain accessible in a public deployment.

## Further reading

- [Local app setup](my_ai_app/LOCAL_SETUP.md)
- [Generator architecture](docs/architecture.md)
- [Configuration guide](docs/guides/configuration.md)
- [Deployment guide](docs/deployment.md)
- [Development guide](docs/development.md)
- [Template upgrades](docs/guides/version-upgrade.md)
- [Contributing](CONTRIBUTING.md)
- [Security policy](SECURITY.md)

Created by **Vstorm**. Distributed under the [MIT License](LICENSE).

## Project guidance

- [Agent instructions](AGENTS.md)
- [Architecture](docs/architecture.md)
- [Architecture decisions](docs/decisions/README.md)
- [Quality checks](docs/quality.md)
- [Startup and recovery](docs/runbooks/local-development.md)

## Persistent memory

AgentHarbor now supports private notes that survive across conversations. Visit **Settings > Memory** to view, create, edit or delete them. This local instance has `ENABLE_MEMORY=true`; other installations opt in through backend `.env` after running migrations. The agent can read, search, write and delete its authenticated user's notes, with visible tool cards in chat. An AI key is required for agent-driven memory, but the settings editor works without one.

See [the memory decision record](docs/decisions/0002-per-user-memory.md) for the upstream PR, scope, limitations and operational details.

## Optional OrcaRouter provider

AgentHarbor can use OrcaRouter for model access through a single gateway. Configure `LLM_PROVIDER=orcarouter`, `ORCAROUTER_API_KEY` and `AI_MODEL` in backend `.env`, then restart the backend. OpenAI remains the local default. See [provider setup and verification](docs/decisions/0003-orcarouter-provider.md).
