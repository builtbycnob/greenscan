"""Async database operations with asyncpg."""

import json
import logging
from datetime import datetime

import asyncpg

from pipeline.classifier.categorizer import ClassifiedSignal
from pipeline.config import settings
from pipeline.scraper.models import RawSignal

logger = logging.getLogger(__name__)


class Database:
    """Manages asyncpg connection pool and provides CRUD operations."""

    def __init__(self) -> None:
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        self._pool = await asyncpg.create_pool(
            settings.neon_database_url,
            min_size=1,
            max_size=5,
        )
        logger.info("Database connected")

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            logger.info("Database disconnected")

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, *exc):
        await self.close()

    async def load_known_hashes(self) -> set[str]:
        """Load content hashes from the last 7 days for dedup."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT content_hash FROM signals WHERE scraped_at > NOW() - INTERVAL '7 days'"
            )
        hashes = {r["content_hash"] for r in rows}
        logger.info(f"Loaded {len(hashes)} known hashes for dedup")
        return hashes

    async def insert_signal(
        self,
        raw: RawSignal,
        classified: ClassifiedSignal,
    ) -> bool:
        """Insert a classified signal. Returns False if duplicate (hash conflict)."""
        async with self._pool.acquire() as conn:
            try:
                await conn.execute(
                    """
                    INSERT INTO signals
                        (url, title, content, content_hash, source,
                         category, relevance_score, summary, entities_json,
                         scraped_at, classified_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                    ON CONFLICT (content_hash) DO NOTHING
                    """,
                    raw.url,
                    raw.title[:200],
                    raw.content[:5000],
                    raw.content_hash,
                    raw.source,
                    classified.category.value,
                    classified.relevance_score,
                    classified.summary,
                    json.dumps(classified.entities.model_dump()),
                    raw.scraped_at,
                    datetime.utcnow(),
                )
                return True
            except Exception as e:
                logger.error(f"Failed to insert signal: {e}")
                return False

    async def insert_signals_batch(
        self,
        raw_signals: list[RawSignal],
        classified: list[ClassifiedSignal],
    ) -> int:
        """Insert a batch of signals. Returns count of newly inserted."""
        inserted = 0
        for raw, cls in zip(raw_signals, classified):
            if await self.insert_signal(raw, cls):
                inserted += 1
        logger.info(f"Inserted {inserted}/{len(raw_signals)} signals")
        return inserted

    async def save_brief(self, content: str, signal_count: int) -> int:
        """Save a generated brief. Returns the brief ID."""
        async with self._pool.acquire() as conn:
            brief_id = await conn.fetchval(
                """
                INSERT INTO briefs (content, signal_count)
                VALUES ($1, $2) RETURNING id
                """,
                content,
                signal_count,
            )
        logger.info(f"Saved brief #{brief_id}")
        return brief_id

    async def get_signal_count(self, days: int = 1) -> int:
        """Count signals from the last N days."""
        async with self._pool.acquire() as conn:
            return await conn.fetchval(
                f"SELECT COUNT(*) FROM signals WHERE scraped_at > NOW() - INTERVAL '{days} days'"
            )

    async def get_latest_brief(self) -> dict | None:
        """Get the most recent brief."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM briefs ORDER BY generated_at DESC LIMIT 1")
        return dict(row) if row else None
