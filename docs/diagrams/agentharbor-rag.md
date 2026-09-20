# AgentHarbor: how document-grounded replies work

RAG means Retrieval-Augmented Generation: retrieve company evidence, then draft a reply using that evidence. It does not train the model on uploaded documents.

## 1. Prepare company knowledge

```mermaid
flowchart LR
    A["Owner / admin<br/>uploads TXT, MD or PDF"] --> B["Validate access,<br/>file type and size"]
    B --> C["Store private original<br/>and queue a job"]
    C --> D["Worker extracts text<br/>Scans need OCR first"]
    D --> E["Chunk text<br/>480 words / 80 overlap"]
    E --> F{"Embeddings<br/>enabled?"}
    F -->|"No: current"| G["Store text chunks<br/>with page references"]
    F -->|"Yes: optional"| H["OpenAI embeddings<br/>Vectors stored in PostgreSQL"]
    G --> I["Mark document<br/>ready to search"]
    H --> I
    classDef optional fill:#fff7ed,stroke:#d97706,color:#78350f;
    class H optional;
```

## 2. Retrieve relevant evidence

```mermaid
flowchart LR
    A["Employee enters<br/>customer question"] --> B["Check workspace<br/>membership"]
    B --> C["Search only this workspace's<br/>ready documents"]
    C --> D["Rank chunks<br/>Keyword search currently"]
    O["Optional hybrid search<br/>Keywords + vector similarity"] -.-> D
    D --> E["Select up to<br/>6 relevant passages"]
    E --> F{"Evidence<br/>found?"}
    F -->|Yes| G["Send passages and<br/>question to drafting"]
    F -->|No| H["Insufficient evidence<br/>No model call"]
    classDef optional fill:#fff7ed,stroke:#d97706,color:#78350f;
    classDef fallback fill:#f1f5f9,stroke:#64748b,color:#334155;
    class O optional;
    class H fallback;
```

## 3. Draft, validate and review

```mermaid
flowchart LR
    A["Restricted AI<br/>Use supplied evidence"] --> B["Structured reply<br/>Outcome + citation IDs"]
    B --> C["Validate citations<br/>Answerable replies need sources"]
    C --> D["Recheck membership<br/>and source availability"]
    D --> E["Save draft<br/>and usage"]
    E --> F["Human checks sources<br/>and edits reply"]
    F --> G["Approve current revision<br/>Edits clear approval"]
    G --> H["Copy into helpdesk<br/>No automatic sending"]
```

## What improves accuracy

- Overlap preserves nearby context; document and page references make evidence inspectable.
- Workspace scoping restricts retrieval to authorized company knowledge.
- The drafting agent has no tools and is instructed to avoid invented policies and treat document instructions as untrusted.
- Missing evidence gets a safe fallback. The model is instructed to flag ambiguity or conflicting sources when evidence is supplied.
- Citation validation and human review add checks. Valid citation IDs do not prove that every claim is supported.

## Current limitations

Keyword search missed "Can I get my money back?" in a refund-policy test. Hybrid embeddings are implemented but not enabled or live-verified. OpenAI returned exhausted API credits during testing, so successful live answer quality remains unverified. RAG reduces unsupported answers; it does not guarantee accuracy.

Implementation: `backend/app/services/knowledge.py`, `backend/app/worker/support.py`, `backend/app/agents/support.py` under `my_ai_app/`.
