"""Tests for storage module (requires DB connection)."""

import pytest

from pipeline.classifier.categorizer import ClassifiedSignal, EntityList
from pipeline.scraper.models import RawSignal
from pipeline.storage.db import Database

pytestmark = pytest.mark.integration


@pytest.fixture
async def db():
    database = Database()
    await database.connect()
    yield database
    await database.close()


@pytest.mark.asyncio
async def test_insert_and_dedup(db):
    """Insert a signal, then verify dedup catches it."""
    raw = RawSignal(
        url="https://test.com/storage-test",
        title="Storage Test",
        content="Unique content for storage test xyz123",
        source="TestCo",
    )
    classified = ClassifiedSignal(
        category="expansion",
        relevance_score=3,
        summary="Test signal for storage",
        entities=EntityList(companies=["TestCo"]),
    )

    # Insert
    ok = await db.insert_signal(raw, classified)
    assert ok

    # Dedup should find it
    hashes = await db.load_known_hashes()
    assert raw.content_hash in hashes

    # Cleanup
    async with db._pool.acquire() as conn:
        await conn.execute("DELETE FROM signals WHERE content_hash = $1", raw.content_hash)


@pytest.mark.asyncio
async def test_save_and_get_brief(db):
    """Save and retrieve a brief."""
    brief_id = await db.save_brief("# Test Brief\n\nContent here.", 5)
    assert brief_id > 0

    latest = await db.get_latest_brief()
    assert latest is not None
    assert "Test Brief" in latest["content"]

    # Cleanup
    async with db._pool.acquire() as conn:
        await conn.execute("DELETE FROM briefs WHERE id = $1", brief_id)


@pytest.mark.asyncio
async def test_scrape_log_lifecycle(db):
    """Start and finish a scrape log entry."""
    log_id = await db.start_scrape_log("test-run-xyz", 5)
    assert log_id > 0

    await db.finish_scrape_log(
        log_id,
        status="success",
        targets_success=5,
        signals_new=10,
        signals_deduped=3,
        duration_ms=5000,
    )

    async with db._pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM scrape_logs WHERE id = $1", log_id)

    assert row["status"] == "success"
    assert row["signals_new"] == 10
    assert row["duration_ms"] == 5000

    # Cleanup
    async with db._pool.acquire() as conn:
        await conn.execute("DELETE FROM scrape_logs WHERE id = $1", log_id)
