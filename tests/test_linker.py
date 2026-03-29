"""Tests for entity linker (requires DB connection)."""

import asyncpg
import pytest

from pipeline.classifier.categorizer import ClassifiedSignal, EntityList
from pipeline.config import settings
from pipeline.enrichment.linker import _link_company, link_entities

pytestmark = pytest.mark.integration


@pytest.fixture
async def pool():
    pool = await asyncpg.create_pool(settings.neon_database_url, min_size=1, max_size=2)
    yield pool
    await pool.close()


@pytest.mark.asyncio
async def test_link_company_creates_new(pool):
    """First time linking a company should create a new record."""
    company_id = await _link_company(pool, "TestCo Linker Unit")
    assert company_id is not None
    assert isinstance(company_id, int)

    # Cleanup
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM companies WHERE name = 'TestCo Linker Unit'")


@pytest.mark.asyncio
async def test_link_company_fuzzy_match(pool):
    """Should match existing company with similar name."""
    # Create a company
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO companies (name, confidence) VALUES ('Bayer Crop Science', 0.9)"
        )

    # Should fuzzy match
    company_id = await _link_company(pool, "Bayer CropScience")
    assert company_id is not None

    # Cleanup
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM companies WHERE name = 'Bayer Crop Science'")


@pytest.mark.asyncio
async def test_link_entities_batch(pool):
    """Should link all entities from classified signals."""
    signals = [
        ClassifiedSignal(
            category="expansion",
            relevance_score=3,
            summary="Test",
            entities=EntityList(
                companies=["LinkerTest Corp"],
                people=["Jane Doe Linker"],
                products=[],
            ),
        )
    ]

    linked = await link_entities(pool, signals)
    assert "LinkerTest Corp" in linked
    assert "Jane Doe Linker" in linked

    # Cleanup
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM companies WHERE name = 'LinkerTest Corp'")
        await conn.execute("DELETE FROM contacts WHERE full_name = 'Jane Doe Linker'")
