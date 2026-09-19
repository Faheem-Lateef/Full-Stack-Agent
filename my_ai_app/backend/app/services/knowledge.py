"""Bounded extraction, lexical retrieval, and optional exact semantic ranking."""

import asyncio
import json
import math
import re
import sys
from collections import Counter

from openai import AsyncOpenAI

from app.core.config import settings
from app.core.exceptions import ValidationError


def split_pages(pages: list[str]) -> list[dict]:
    result = []
    for page, text in enumerate(pages, 1):
        words = text.split()
        for start in range(0, len(words), 400):
            content = " ".join(words[start : start + 480])
            if content:
                result.append({"ordinal": len(result), "page": page, "text": content})
    if not result:
        raise ValidationError("No readable text. Scanned PDFs need OCR before upload.")
    if len(result) > 500:
        raise ValidationError("Document exceeds the 500-chunk pilot limit")
    return result


async def extract(filename: str, data: bytes) -> list[dict]:
    # Separate process: parsing cannot block the API/worker event loop. No file paths
    # or user code are executed; worker kills parsing after the bounded timeout.
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "app.worker.parse_document",
        filename.rsplit(".", 1)[-1].lower(),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        output, _ = await asyncio.wait_for(process.communicate(data), timeout=45)
    except (TimeoutError, asyncio.CancelledError):
        process.kill()
        await process.wait()
        raise ValidationError("Document parsing timed out") from None
    if process.returncode:
        raise ValidationError(
            "Unreadable, encrypted, oversized, or scanned document. Upload a text PDF or UTF-8 text."
        )
    return split_pages(json.loads(output))


async def embeddings(texts: list[str]) -> list[list[float] | None]:
    if not settings.SUPPORT_EMBEDDINGS_ENABLED:
        return [None for _ in texts]
    if not settings.OPENAI_API_KEY.strip():
        raise ValidationError("OpenAI key required for semantic indexing")
    async with AsyncOpenAI(api_key=settings.OPENAI_API_KEY, max_retries=0, timeout=30) as client:
        results = []
        for offset in range(0, len(texts), 32):
            response = await client.embeddings.create(
                model=settings.SUPPORT_EMBEDDING_MODEL, input=texts[offset : offset + 32]
            )
            results.extend(row.embedding for row in sorted(response.data, key=lambda r: r.index))
        return results


def tokens(text: str) -> list[str]:
    words = re.findall(r"\w+", text.lower())
    return [
        word[:-1] if len(word) > 4 and word.endswith("s") and not word.endswith("ss") else word
        for word in words
    ]


def cosine(a, b):
    if not a or not b or len(a) != len(b):
        return 0.0
    divisor = math.sqrt(sum(x * x for x in a) * sum(x * x for x in b))
    return sum(x * y for x, y in zip(a, b, strict=True)) / divisor if divisor else 0.0


def rank_chunks(rows, query: str, query_embedding=None, limit=6):
    """Exact, workspace-bounded pilot ranking. No score is presented as confidence."""
    terms = set(tokens(query)) - {
        "the",
        "a",
        "an",
        "is",
        "are",
        "can",
        "i",
        "we",
        "you",
        "to",
        "of",
        "and",
        "for",
        "in",
        "what",
        "how",
        "do",
    }
    lexical, semantic = [], []
    for chunk, title in rows:
        counts = Counter(tokens(chunk.text))
        score = sum(math.log1p(counts[t]) for t in terms) / math.sqrt(max(len(counts), 1))
        if score:
            lexical.append((score, chunk, title))
        similarity = cosine(query_embedding, chunk.embedding)
        if similarity >= 0.3:
            semantic.append((similarity, chunk, title))
    fused, objects = {}, {}
    for ranked in [lexical, semantic]:
        for position, (_, chunk, title) in enumerate(
            sorted(ranked, key=lambda row: row[0], reverse=True)[:30]
        ):
            fused[chunk.id] = fused.get(chunk.id, 0) + 1 / (60 + position + 1)
            objects[chunk.id] = (chunk, title)
    result = []
    for cid in sorted(fused, key=fused.get, reverse=True)[:limit]:
        chunk, title = objects[cid]
        result.append(
            {
                "id": str(chunk.id),
                "document_id": str(chunk.document_id),
                "title": title,
                "page": chunk.page,
                "text": chunk.text,
            }
        )
    return result


async def search(repo, wid, question: str):
    rows = await repo.chunks(wid)
    if len(rows) > 5000:
        raise ValidationError("Pilot search limit exceeded; archive documents before searching")
    vector = (await embeddings([question]))[0] if settings.SUPPORT_EMBEDDINGS_ENABLED else None
    return rank_chunks(rows, question, vector)
