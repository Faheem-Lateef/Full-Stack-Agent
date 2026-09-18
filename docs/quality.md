# Quality requirements

## Scope

This repository contains the generator and the AgentHarbor application in `my_ai_app/`. Test the component changed. Template changes also require generator regression tests; changes inside `my_ai_app/` do not automatically change future generated apps.

## Completion requirements

For every behavior change, add or update tests covering the normal path, invalid input, and relevant authorization or failure cases. Fix failing checks caused by the change. Never remove assertions or disable checks just to obtain a pass. Documentation-only changes need link and command verification, not artificial tests.

From `my_ai_app/backend` in PowerShell:

```powershell
$env:DEBUG='true'
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check app tests alembic
```

From `my_ai_app/frontend`:

```powershell
npm.cmd run lint
npm.cmd run type-check
npm.cmd run test:run
npm.cmd run build
```

Stop the frontend dev server before a production build: both write `.next`. Restart it after the build. Use the Chromium browser smoke test documented in the runbook for UI changes. Existing E2E scenarios that require a seeded account are not a substitute for an actual authenticated test.

For generator changes, from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check fastapi_gen tests
```

## Database and integration checks

Apply migrations to a dedicated development or disposable test database, then check `alembic current`. Never reset a user's database for testing. Confirm `/api/v1/health/ready` reports a healthy database. Use unique test accounts and remove only records created by a test. Verify registration, login, profile access, and authorization. AI provider integration requires a configured key; report it as unverified when the key is absent.

## Performance and release expectations

Initial local targets: readiness under 1 second and ordinary API reads under 500 ms after warm-up on the development machine. These are targets, not measured production guarantees. Record build failures, browser console errors, slow endpoints, and remaining lint warnings. Provider generation latency is measured separately from application overhead.

Do not call a release production-ready solely because unit tests pass. Before deployment, verify environment-specific configuration, backups and restore, TLS, access controls, provider quotas, migrations and rollback. Keep credentials, uploaded user content and test session tokens out of Git.

## Evidence

At completion, report changed behavior, commands run and outcomes, and checks that could not run. Automated checks enforce only what they cover; these documents do not create a background monitoring service.

GitHub runs the AgentHarbor backend and frontend checks through `.github/workflows/agentharbor.yml` on app changes. Local browser smoke checks require running servers and a development database; this workflow does not run provider calls or that local smoke test.
