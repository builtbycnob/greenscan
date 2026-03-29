"""Entity linking via pg_trgm fuzzy matching.

Links extracted entity names (companies, people) to existing records
in the companies/contacts tables. Creates new records if no match found.
"""

import logging

import asyncpg

from pipeline.classifier.categorizer import ClassifiedSignal

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 0.6


async def link_entities(
    pool: asyncpg.Pool,
    classified: list[ClassifiedSignal],
) -> dict[str, list[int]]:
    """Link entities from classified signals to DB records.

    Returns mapping of entity name -> list of DB record IDs (company or contact).
    """
    linked: dict[str, list[int]] = {}

    for signal in classified:
        for company_name in signal.entities.companies:
            company_id = await _link_company(pool, company_name)
            if company_id:
                linked.setdefault(company_name, []).append(company_id)

        for person_name in signal.entities.people:
            contact_id = await _link_contact(pool, person_name)
            if contact_id:
                linked.setdefault(person_name, []).append(contact_id)

    logger.info(f"Linked {len(linked)} entities")
    return linked


async def _link_company(pool: asyncpg.Pool, name: str) -> int | None:
    """Find or create a company by fuzzy name match."""
    if not name or len(name) < 2:
        return None

    async with pool.acquire() as conn:
        # Try fuzzy match
        row = await conn.fetchrow(
            """
            SELECT id, name, similarity(name, $1) AS sim
            FROM companies
            WHERE similarity(name, $1) > $2
            ORDER BY sim DESC
            LIMIT 1
            """,
            name,
            SIMILARITY_THRESHOLD,
        )

        if row:
            logger.debug(f"Matched '{name}' -> '{row['name']}' (sim={row['sim']:.2f})")
            return row["id"]

        # Create new company
        new_id = await conn.fetchval(
            """
            INSERT INTO companies (name, confidence)
            VALUES ($1, 0.5)
            RETURNING id
            """,
            name,
        )
        logger.debug(f"Created company '{name}' (id={new_id})")
        return new_id


async def _link_contact(pool: asyncpg.Pool, name: str) -> int | None:
    """Find or create a contact by fuzzy name match."""
    if not name or len(name) < 2:
        return None

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, full_name, similarity(full_name, $1) AS sim
            FROM contacts
            WHERE similarity(full_name, $1) > $2
            ORDER BY sim DESC
            LIMIT 1
            """,
            name,
            SIMILARITY_THRESHOLD,
        )

        if row:
            logger.debug(f"Matched '{name}' -> '{row['full_name']}' (sim={row['sim']:.2f})")
            return row["id"]

        new_id = await conn.fetchval(
            """
            INSERT INTO contacts (full_name, confidence)
            VALUES ($1, 0.5)
            RETURNING id
            """,
            name,
        )
        logger.debug(f"Created contact '{name}' (id={new_id})")
        return new_id
