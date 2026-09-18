"""Shared asyncpg pool and store for persistent agent memory.

The pydantic-ai-harness ``PostgresMemoryStore`` speaks a raw asyncpg-compatible
pool, not SQLAlchemy. One process-wide pool is created in the app lifespan
against the same Postgres as the ORM; Alembic revision 0028 creates its ``agent_memory*`` tables, and the
store performs idempotent schema checks on first use (advisory-lock guarded). ``None`` when the pool could not be created â€” there is
deliberately no in-memory fallback, which would fake persistence: without the
store the memory capability and the ``/me/memory`` API are simply unavailable.

Startup is not the only chance to connect. A database that is unreachable while
the process boots must not leave memory dead until the next restart, so
``get_memory_store`` retries the connection, at most once every
``_RETRY_COOLDOWN_SECS`` so a down database can't be hammered per request.
"""

import asyncio
import logging
import time

import asyncpg
from pydantic_ai_harness.memory import PostgresMemoryStore

from app.core.config import settings

logger = logging.getLogger(__name__)

_RETRY_COOLDOWN_SECS = 10.0

_memory_pool: asyncpg.Pool | None = None
_memory_store: PostgresMemoryStore | None = None
_init_lock = asyncio.Lock()
_last_attempt_at: float | None = None


async def init_memory_pool() -> asyncpg.Pool | None:
    """Create the shared asyncpg pool and store, returning the pool or ``None``.

    Explicit connection fields preserve configured TLS and avoid driver-specific
    URL parameters. Failed connection attempts have a bounded timeout.
    """
    global _memory_pool, _memory_store, _last_attempt_at
    if _memory_pool is not None:
        return _memory_pool
    async with _init_lock:
        if _memory_pool is not None:
            return _memory_pool
        if (
            _last_attempt_at is not None
            and time.monotonic() - _last_attempt_at < _RETRY_COOLDOWN_SECS
        ):
            return None
        pool: asyncpg.Pool | None = None
        try:
            pool = await asyncpg.create_pool(
                host=settings.POSTGRES_HOST,
                port=settings.POSTGRES_PORT,
                user=settings.POSTGRES_USER,
                password=settings.POSTGRES_PASSWORD,
                database=settings.POSTGRES_DB,
                ssl=settings.POSTGRES_SSL_MODE,
                min_size=1,
                max_size=settings.DB_POOL_SIZE,
                timeout=5,
                command_timeout=10,
            )
            _memory_store = PostgresMemoryStore(pool)
            _memory_pool = pool
            logger.info("Agent memory pool connected")
        except Exception as e:
            if pool is not None:
                await pool.close()
            _memory_pool = None
            _memory_store = None
            logger.warning("Memory pool unavailable (%s)", type(e).__name__)
        finally:
            _last_attempt_at = time.monotonic()
        return _memory_pool


async def close_memory_pool() -> None:
    """Close the shared asyncpg pool on shutdown."""
    global _memory_pool, _memory_store, _last_attempt_at
    if _memory_pool is not None:
        await _memory_pool.close()
        _memory_pool = None
    _memory_store = None
    _last_attempt_at = None


async def get_memory_store() -> PostgresMemoryStore | None:
    """Return the shared memory store, or ``None`` when unavailable."""
    if not settings.ENABLE_MEMORY:
        return None
    if _memory_store is not None:
        return _memory_store
    if _last_attempt_at is not None and time.monotonic() - _last_attempt_at < _RETRY_COOLDOWN_SECS:
        return None
    await init_memory_pool()
    return _memory_store
