"""Unit tests for DB resilience against Neon idle-connection drops."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import asyncpg
import pytest

from pipeline.storage.db import Database


def _make_pool(connections):
    """Build a MagicMock pool whose `acquire()` returns the next connection."""
    pool = MagicMock()
    pool.expire_connections = AsyncMock()
    it = iter(connections)

    @asynccontextmanager
    async def _acquire():
        yield next(it)

    pool.acquire = _acquire
    return pool


@pytest.mark.asyncio
async def test_load_known_hashes_retries_after_dropped_connection():
    """A ConnectionDoesNotExistError on first acquire is retried once."""
    bad_conn = MagicMock()
    bad_conn.fetch = AsyncMock(
        side_effect=asyncpg.exceptions.ConnectionDoesNotExistError("connection lost")
    )

    good_conn = MagicMock()
    good_conn.fetch = AsyncMock(return_value=[{"content_hash": "abc"}, {"content_hash": "def"}])

    db = Database()
    db._pool = _make_pool([bad_conn, good_conn])

    hashes = await db.load_known_hashes()

    assert hashes == {"abc", "def"}
    bad_conn.fetch.assert_awaited_once()
    good_conn.fetch.assert_awaited_once()
    db._pool.expire_connections.assert_awaited_once()


@pytest.mark.asyncio
async def test_load_known_hashes_propagates_unrelated_errors():
    """Non-connection errors should not trigger the retry."""
    bad_conn = MagicMock()
    bad_conn.fetch = AsyncMock(side_effect=RuntimeError("boom"))

    db = Database()
    db._pool = _make_pool([bad_conn])

    with pytest.raises(RuntimeError):
        await db.load_known_hashes()
    db._pool.expire_connections.assert_not_awaited()


@pytest.mark.asyncio
async def test_load_known_hashes_happy_path():
    """Normal case: one successful query, no retry."""
    good_conn = MagicMock()
    good_conn.fetch = AsyncMock(return_value=[{"content_hash": "h1"}])

    db = Database()
    db._pool = _make_pool([good_conn])

    hashes = await db.load_known_hashes()
    assert hashes == {"h1"}
    db._pool.expire_connections.assert_not_awaited()
