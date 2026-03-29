"""Unit tests for target registry."""

from pipeline.scraper.registry import (
    Priority,
    get_scrapable_targets,
    load_targets,
)


def test_load_targets():
    targets = load_targets()
    assert len(targets) > 0
    assert all(t.name for t in targets)
    assert all(t.priority in Priority for t in targets)


def test_high_priority_count():
    targets = load_targets()
    high = [t for t in targets if t.priority == Priority.HIGH]
    assert len(high) == 10


def test_scrapable_targets_have_urls():
    targets = load_targets()
    scrapable = get_scrapable_targets(targets)
    assert len(scrapable) > 0
    for t in scrapable:
        assert len(t.scrape_urls) > 0


def test_all_targets_have_serp_query():
    targets = load_targets()
    for t in targets:
        assert len(t.serp_queries) > 0, f"{t.name} has no SERP queries"
