# 0004: Native support pilot

- Status: accepted for the local pilot; production infrastructure remains open.
- Date: 2026-09-20

The customer-support plan is implemented in `my_ai_app/` without regenerating the app. Workspaces, memberships, documents, chunks, support cases, drafts, jobs and audit events are separate from personal conversations and memory. Every support API requires authenticated workspace membership. Global application administrators do not automatically receive workspace access.

Preflight found no pgvector extension in native PostgreSQL, a stopped Docker engine, and no configured LLM key. The user selected OpenAI and explicitly deferred paid live AI tests.

For this local pilot, use PostgreSQL for durable job dispatch, private original documents and application records. A separate native Python worker claims committed jobs; short claim transactions use an advisory lock and `SKIP LOCKED`, with at most four processing jobs globally. There is no in-request ingestion or volatile background-task queue. Uncertain paid generations are not automatically replayed. Cancelled jobs stop publishing and are checked by the worker every two seconds; already-started provider work may still incur charges.

Search uses workspace-filtered lexical ranking. Optional OpenAI embeddings add exact cosine ranking and reciprocal-rank fusion over a maximum of 5,000 active chunks per workspace. Embeddings are stored as JSON arrays rather than requiring a database extension. This is a bounded pilot alternative to the plan's pgvector/Redis/Celery/object-storage deployment, not an equivalent large-scale implementation. Do not change embedding models on an existing corpus without reindexing it.

Uploads are restricted to text PDF, TXT and Markdown. A separate parser process has a 45-second timeout and file/page/extracted-text/chunk limits. This is not an OS-level sandbox or a malware-scanning service. Restrict the pilot to trusted company uploads until container isolation and malware scanning are deployed. Originals are private database bytes, never frontend assets or arbitrary filesystem paths.

Each document upload is an immutable version identified by UUID. A replacement becomes current only after successful processing and archives the old version atomically. Deletion purges original bytes and chunks, retains unavailable citation identifiers, and removes draft approval. Draft replies/history are separate support records; deleting a knowledge document is not a promise to erase all human-written or generated text that may refer to it. Workspace deletion removes its support records together; database backup retention is separate.

Membership role checks protect invitations, ownership transfers, upload/deletion and review operations. A database foreign key prevents account deletion from silently removing the last owner. Transfer ownership and leave memberships before deleting an account. Historic cases/jobs also retain user references; a full account anonymization policy remains a deployment decision.

Generation uses a dedicated PydanticAI agent with structured output and no tools, browser, shell or personal memory. Citation references are validated against supplied passages. This proves reference validity, not factual accuracy. Staff approval is mandatory for the UI copy action. No external customer messaging is implemented.

Validation: rollback-only PostgreSQL integration tests, structured-agent tests with PydanticAI TestModel, frontend editor regression tests, and a real browser/worker smoke test with an explicitly seeded disposable draft. No live provider success or production quality/latency target is claimed without the remaining evaluations.
