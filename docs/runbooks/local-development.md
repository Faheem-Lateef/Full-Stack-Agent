# Local startup and recovery

## Configuration

The application is in `my_ai_app/`. Backend configuration lives in `my_ai_app/backend/.env`; frontend configuration lives in `my_ai_app/frontend/.env.local`. Copy the corresponding example on a new checkout, then fill in real values locally. Never commit these files.

Local PostgreSQL uses `localhost:5432`, user `postgres`, database `my_ai_app`. The database has already been created on the current machine. For another machine, create a dedicated database with pgAdmin or `createdb -U postgres my_ai_app`; enter the password when prompted. Hosted PostgreSQL also works; use its connection hostname and TLS settings, not the browser dashboard URL.

## Start

In a backend terminal:

```powershell
cd my_ai_app/backend
$env:DEBUG='true'
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In a separate terminal from the repository root:

```powershell
cd my_ai_app/frontend
npm.cmd run dev -- --hostname localhost
```

Install dependencies first on a fresh checkout; see the root README. The `DEBUG` override is necessary on machines with an inherited non-boolean value such as `release`.

## Verify

Open http://localhost:3000 and http://localhost:8000/docs. Check http://localhost:8000/api/v1/health/ready and inspect each dependency status; HTTP 200 does not guarantee an AI key is present. Register your own account before exposing this app publicly: the first registered account becomes administrator. Later public registrations must remain ordinary users.

Run `npm.cmd run test:smoke` from the frontend after both servers start. This checks branding, login, dashboard and browser errors against a uniquely named temporary account. It uses an API login and removes its own account afterward. It does not call a paid model.

## Database failures

Check that the PostgreSQL Windows service is running and port 5432 is available. Check host, database, username and password in the backend environment file without printing it. Run migrations and `python -m alembic current` using the backend virtual environment. Restart the backend after environment changes. Do not delete data or use `alembic stamp` to hide failed migrations.

## AI failures

Add `OPENAI_API_KEY` and select an `AI_MODEL` available to that account in backend `.env`, then restart the backend. Provider secrets must never use a `NEXT_PUBLIC_` prefix. Authentication, quota and model-access failures need provider configuration; fake responses are not a fix.

## Port conflicts or frontend build failures

Inspect the process owning the port before stopping it. Stop only this application's process. Do not run `next dev` and `next build` against the same `.next` directory at once. Review `server-error.log` and `dev-server-error.log` when using background servers. Logs may contain user data and stay ignored by Git.

## Recovery and rollback

For code regressions, revert the offending Git commit and run the quality checks before restarting. Before production migrations, take a PostgreSQL backup and verify restoration in a separate database. Review migration downgrade code before using it; a downgrade can discard data. Restore into a separate database and validate it before changing connection settings. Never overwrite the original database as an automatic repair.
