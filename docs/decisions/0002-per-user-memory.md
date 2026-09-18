# 0002: Persistent per-user memory

- Status: accepted
- Date: 2026-09-18
- Upstream: https://github.com/vstorm-co/full-stack-ai-agent-template/pull/133
- Reviewed PR head: `6c965ebcc6d7b1e09eb91b8be0d34a4261dcfcb7` (open when reviewed)

## Context and value

Conversation history belongs to a single chat. AgentHarbor also benefits from durable preferences and notes that can be recalled in later conversations. The installed PydanticAI and PostgreSQL stack matches this PR's requirements.

## Decision

Adapt the memory backend, settings editor, tool cards and PydanticAI v2 tool-result fix into the existing `my_ai_app` application. Do not merge the upstream branch wholesale or modify the generator. Its CLI flags, alternate-framework fixes and deep-research buffering changes are outside this app's enabled configuration.

Use `pydantic-ai-harness==0.12.0` as the memory data adapter. Services own validation and error mapping; the harness store owns database operations instead of a duplicate repository. A dedicated asyncpg pool uses the existing PostgreSQL credentials and TLS mode. Alembic migration 0028 explicitly creates the three tables and version sequence; the library also performs idempotent schema checks on first use. These tables are library-owned and must not be removed by future ORM autogeneration.

Memory is isolated by authenticated user UUID, never by a model-supplied namespace. Anonymous or invalid identities receive no memory capability. `MEMORY.md` is the main notebook; flat markdown files can hold additional notes. The settings API exposes only the current user's namespace. Updates and deletes require a matching version; stale writes return HTTP 409.

## Local configuration

`ENABLE_MEMORY` defaults to false in code and the example env file; it is enabled in the local backend `.env`. Disabling it prevents agent use and API access but retains stored data. The Settings page explains when it is disabled. A database outage is shown as retryable unavailability, not as an empty or disabled notebook.

## Differences from the reviewed PR

- Bound connection attempts and recheck retry cooldown under the lock, timestamping completion.
- Preserve unsaved drafts on all save failures, including version conflicts.
- Distinguish disabled memory from a temporarily unavailable database.
- Validate user UUIDs before building a capability and scope frontend query caches to the signed-in user.
- Create storage with an explicit migration and keep the harness version pinned because its filename/path helpers are private APIs.
- Fix misleading deletion copy: deleting the main notebook does not delete other memory files.

## Consequences and limitations

Stored memory is additional persistent user data. Users can view, edit and delete files in Settings > Memory. Deleting a conversation does not remove these notes. Deleting a memory file does not erase copies already present in chat history or backups. Storage is plaintext in PostgreSQL; database access and backups must be protected. A valid AI provider key is still required for agent-driven recall and writes. CRUD tests do not prove model behavior.

The adapter's startup schema checks require DDL privileges; do not deploy with a restricted database role without reviewing this behavior. The Alembic environment excludes the library-owned memory tables from ORM autogeneration through `app/db/migration_filters.py`. Account deletion currently does not purge the isolated namespace; implement a tested lifecycle policy before exposing public self-service account deletion.

## Verification

Run the backend suite, frontend tests, type checks, lint and production build. Run `npm run test:smoke` with both servers and memory enabled to check real PostgreSQL CRUD, isolation, conflicting writes and the settings editor. Tests use temporary users and clean up their notes. No paid provider calls are required.
