# Support pilot: start, use and recover

## Start locally

Run migration and API from `my_ai_app/backend`:

```powershell
$env:DEBUG='true'
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Run the worker from the same directory in a separate terminal:

```powershell
$env:DEBUG='true'
.\.venv\Scripts\python.exe -m app.worker.support
```

Backend `.env` settings:

```ini
SUPPORT_ENABLED=true
LLM_PROVIDER=openai
OPENAI_API_KEY=your-local-secret
SUPPORT_EMBEDDINGS_ENABLED=false
SUPPORT_EMBEDDING_MODEL=text-embedding-3-small
```

Do not put real keys in tracked files or frontend configuration. Restart both API and worker after changes. The local installation enables support and keyword search. On 2026-09-20 the operator authorized live testing and supplied a key, which was stored only in the ignored backend `.env`. OpenAI returned `429 credit_balance_exhausted` (`insufficient_quota`); successful generation and semantic verification remain blocked by account credits. See the [functional review](../reports/product-review-2026-09-20.md).

To enable semantic search later, configure a valid OpenAI key, set `SUPPORT_EMBEDDINGS_ENABLED=true`, restart, and replace/reprocess the existing documents. Existing keyword-only documents are not silently embedded. Index and query vectors must use the same model. Changing the model requires reindexing; keep semantic mode disabled until that migration is complete. Indexing and searching in semantic mode can incur embedding charges.

The worker needs the backend dependencies, including `pypdf`, installed using the project lockfile. On this machine `.venv/Scripts/uv.exe sync` is available; standard installations can use `uv sync`.

Run frontend from `my_ai_app/frontend` using `npm.cmd run dev -- --hostname localhost` when editing. For production-mode local verification, stop the frontend, run `npm.cmd run build`, then `npm.cmd run start -- --hostname localhost`. Do not build into `.next` while the development server is running. The existing standalone configuration emits a `next start` warning; actual standalone deployment must package `public` and `.next/static` with the standalone server.

## Use the product

1. Sign in at http://localhost:3000 and open **Support**.
2. Create a workspace. Its creator becomes workspace owner independently of application admin status.
3. Open **Company knowledge**, upload a trusted text PDF/TXT/Markdown file, and wait for `ready`.
4. Test a question in the knowledge search. Keyword mode is explicitly displayed.
5. Open **Team** to invite an email address. Share the one-time token privately; it is not sent automatically. The teammate signs in with that address and uses **Join workspace**. Tokens expire after three days and can be revoked.
6. Create a support case. Once an operator key is configured, choose **Draft reply**. Review the outcome and sources, edit/save revisions, approve, then copy into your helpdesk. Copying does not send a customer message.
7. Open **Usage** for request allowance, stored bytes and queued work. Workspace settings include owner-confirmed deletion.

Pilot limits: 10 MB/file, 200 PDF pages, 500 chunks/document, 100 stored documents, 50 MB original bytes and 5,000 active chunks/workspace. At most five active jobs/workspace and four processing jobs globally. Generation allowance defaults to 100 requests per calendar month; failed/cancelled requests count because upstream charges may already have occurred. These are request safeguards, not subscription billing or measured provider costs. Document uploads currently have storage limits but not the generation queue's five-job limit.

## Verification

Backend:

```powershell
$env:DEBUG='true'
$env:RUN_SUPPORT_DB_TESTS='1'
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check app tests alembic
```

Support DB tests use the configured local database and roll back their unique test records. They do not reset it. Without `RUN_SUPPORT_DB_TESTS=1`, database integration cases are skipped explicitly.

Frontend:

```powershell
npm.cmd run lint
npm.cmd run type-check
npm.cmd run test:run
node scripts/support-smoke.mjs
npm.cmd run test:smoke
```

Support smoke requires the running API, worker and frontend with support enabled. It creates two uniquely named users and a workspace, tests real ingestion and search, invitations and permissions, seeds a clearly identified draft fixture to test review UI without a paid model call, then removes only its own workspace/users. Existing authentication/memory smoke still requires memory enabled. Neither proves live model grounding.

## Recovery

### Offline retrieval evaluation

Prepare a sanitized JSONL file with one object per answerable held-out question: `{"question":"What is our refund window?","expected_document_ids":["actual-document-uuid"]}`. Use IDs from that workspace's ready knowledge. Run from the backend:

```powershell
.\.venv\Scripts\python.exe -m app.evaluations.support --workspace YOUR_WORKSPACE_UUID --dataset YOUR_DATASET.jsonl
```

This command measures keyword evidence hits at five and makes no model/embedding calls, even if semantic mode is configured. It does not claim answer accuracy or assess unanswerable/adversarial questions; those require the separate live-provider and human review gates in the implementation plan. No real customer evaluation dataset has been supplied yet.

- **Queued forever:** start the worker with the same database/environment as the API. Check worker logs. There is no automatic OS service installation or hosted monitoring yet.
- **Failed document:** inspect its sanitized error. Correct unsupported/empty/encrypted input, or fix provider connectivity, then use Retry. An old ready version remains available after failed replacement.
- **Interrupted worker:** processing jobs older than five minutes become failed during the next claim cycle. Ingestion can be retried explicitly. Paid generation is never blindly replayed; inspect usage before requesting another draft.
- **Provider missing/error:** configure the backend key/model and restart API plus worker. Key presence in Usage does not validate credentials or account quota. Do not substitute a fake successful answer.
- **Stale editor:** unsaved text is preserved. Copy your edits, load the newer revision, then reconcile. Approval is removed by a saved edit.
- **Source archived/deleted:** regenerate the answer from current knowledge. Old source links become unavailable, and approval/copy validation rejects them.
- **Removed member:** subsequent requests fail authorization; pending jobs for that member are cancelled. Already-visible text cannot be recalled from a browser, and provider requests already sent cannot be guaranteed unbilled.
- **Rollback:** disable `SUPPORT_ENABLED` and stop the worker, preserving the additive tables. Do not downgrade migrations as automatic recovery; downgrading 0029 deletes all support data.

## Before a public release

Finish customer discovery and the held-out evidence/answer-quality evaluation. Add deployment-specific private object storage, sandboxed/malware-scanned parsing, worker supervision and health alerts, provider usage reconciliation, retention/anonymization rules, backup/restore verification, and a measured load test. Review public account bootstrap and rate limiting. Live testing is authorized, but currently blocked by exhausted API credits. Resolve the findings in the functional review before a public release. The current work is a local functional pilot, not a completed production rollout.
