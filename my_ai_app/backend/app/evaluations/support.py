"""Evaluate keyword retrieval against a supplied, labeled JSONL dataset."""

import argparse
import asyncio
import json
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, Field

from app.db.session import get_worker_db_context
from app.repositories.support import SupportRepository
from app.services.knowledge import rank_chunks


class EvaluationCase(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    expected_document_ids: list[UUID] = Field(min_length=1, max_length=20)


def score(rows, cases: list[EvaluationCase]):
    hits = 0
    for case in cases:
        retrieved = rank_chunks(rows, case.question, limit=5)
        actual = {UUID(source["document_id"]) for source in retrieved}
        hits += bool(actual.intersection(case.expected_document_ids))
    return {
        "answerable_questions": len(cases),
        "evidence_hits_at_5": hits,
        "hit_rate_at_5": hits / len(cases) if cases else None,
        "mode": "keyword",
        "live_provider_calls": 0,
        "answer_quality_assessed": False,
    }


async def evaluate(workspace: UUID, dataset: Path):
    cases = [
        EvaluationCase.model_validate_json(line)
        for line in dataset.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not cases:
        raise ValueError("Dataset is empty")
    async with get_worker_db_context() as db:
        repo = SupportRepository(db)
        await repo.workspace(workspace)
        rows = await repo.chunks(workspace)
    if len(rows) > 5000:
        raise ValueError("Pilot corpus limit exceeded")
    available = {chunk.document_id for chunk, _ in rows}
    if any(not set(case.expected_document_ids).issubset(available) for case in cases):
        raise ValueError("Dataset references documents outside this workspace's ready knowledge")
    print(json.dumps(score(rows, cases), indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=UUID, required=True)
    parser.add_argument(
        "--dataset",
        type=Path,
        required=True,
        help="Sanitized answerable questions with expected_document_ids, one JSON object per line",
    )
    args = parser.parse_args()
    asyncio.run(evaluate(args.workspace, args.dataset))


if __name__ == "__main__":
    main()
