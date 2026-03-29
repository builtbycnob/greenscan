"""Unit tests for deduplication."""

from pipeline.enrichment.dedup import Deduplicator
from pipeline.scraper.models import RawSignal


def _make_signal(content: str, url: str = "https://example.com") -> RawSignal:
    return RawSignal(url=url, title="Test", content=content, source="Test Co")


def test_dedup_removes_exact_duplicates():
    signals = [
        _make_signal("Same content here"),
        _make_signal("Same content here"),
        _make_signal("Different content"),
    ]
    dedup = Deduplicator()
    result = dedup.filter(signals)
    assert len(result) == 2


def test_dedup_preserves_unique():
    signals = [
        _make_signal("Content A"),
        _make_signal("Content B"),
        _make_signal("Content C"),
    ]
    dedup = Deduplicator()
    result = dedup.filter(signals)
    assert len(result) == 3


def test_dedup_with_known_hashes():
    existing = _make_signal("Already seen")
    dedup = Deduplicator(known_hashes={existing.content_hash})

    signals = [
        _make_signal("Already seen"),
        _make_signal("Brand new"),
    ]
    result = dedup.filter(signals)
    assert len(result) == 1
    assert result[0].content == "Brand new"


def test_dedup_seen_count():
    dedup = Deduplicator()
    assert dedup.seen_count == 0
    dedup.filter([_make_signal("A"), _make_signal("B")])
    assert dedup.seen_count == 2
