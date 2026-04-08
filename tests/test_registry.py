"""Unit tests for target registry."""

from pipeline.scraper.registry import (
    Priority,
    TargetType,
    get_competitor_targets,
    get_customer_targets,
    get_rss_targets,
    get_scrapable_targets,
    load_targets,
)


def test_load_targets():
    targets = load_targets()
    assert len(targets) >= 100
    assert all(t.name for t in targets)
    assert all(t.priority in Priority for t in targets)
    assert all(t.type in TargetType for t in targets)


def test_target_type_split():
    targets = load_targets()
    customers = get_customer_targets(targets)
    competitors = get_competitor_targets(targets)
    assert len(customers) > 50
    assert len(competitors) > 40
    assert len(customers) + len(competitors) == len(targets)


def test_high_priority_count():
    targets = load_targets()
    high = [t for t in targets if t.priority == Priority.HIGH]
    assert len(high) >= 30


def test_scrapable_targets_have_urls():
    targets = load_targets()
    scrapable = get_scrapable_targets(targets)
    assert len(scrapable) > 0
    for t in scrapable:
        assert len(t.scrape_urls) > 0


def test_rss_targets_have_feeds():
    targets = load_targets()
    rss = get_rss_targets(targets)
    assert len(rss) >= 2
    for t in rss:
        assert len(t.rss_feeds) > 0


def test_customer_contact_lookup():
    targets = load_targets()
    customers = get_customer_targets(targets)
    assert all(t.contact_lookup for t in customers)


def test_competitor_no_contact_lookup():
    targets = load_targets()
    competitors = get_competitor_targets(targets)
    assert all(not t.contact_lookup for t in competitors)
