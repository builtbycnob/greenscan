"""Deduplicate signals by SHA256 content hash.

For MVP: in-memory set per run. When DB is connected, checks against
the signals table's content_hash UNIQUE constraint via ON CONFLICT DO NOTHING.
"""

import logging

from pipeline.scraper.models import RawSignal

logger = logging.getLogger(__name__)


class Deduplicator:
    """Track seen content hashes and filter duplicates."""

    def __init__(self, known_hashes: set[str] | None = None) -> None:
        self._seen: set[str] = known_hashes or set()

    def filter(self, signals: list[RawSignal]) -> list[RawSignal]:
        """Remove signals with already-seen content hashes."""
        unique = []
        for signal in signals:
            if signal.content_hash in self._seen:
                continue
            self._seen.add(signal.content_hash)
            unique.append(signal)

        dropped = len(signals) - len(unique)
        if dropped:
            logger.info(f"Dedup: {dropped}/{len(signals)} duplicates removed")
        return unique

    @property
    def seen_count(self) -> int:
        return len(self._seen)
