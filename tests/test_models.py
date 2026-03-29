"""Unit tests for data models."""

from pipeline.classifier.categorizer import Category, ClassifiedSignal, EntityList
from pipeline.scraper.models import RawSignal


def test_raw_signal_hash_deterministic():
    s1 = RawSignal(url="https://a.com", content="hello world", source="Test")
    s2 = RawSignal(url="https://b.com", content="hello world", source="Test")
    assert s1.content_hash == s2.content_hash


def test_raw_signal_hash_differs():
    s1 = RawSignal(url="https://a.com", content="hello world", source="Test")
    s2 = RawSignal(url="https://a.com", content="different", source="Test")
    assert s1.content_hash != s2.content_hash


def test_entity_list_coerce_from_list():
    result = EntityList.coerce(["Bayer", "McCain"])
    assert result.companies == ["Bayer", "McCain"]
    assert result.people == []


def test_entity_list_coerce_from_dict():
    result = EntityList.coerce(
        {"companies": ["Bayer"], "people": ["John"], "products": ["FieldView"]}
    )
    assert result.companies == ["Bayer"]
    assert result.people == ["John"]


def test_entity_list_coerce_empty():
    result = EntityList.coerce(None)
    assert result.companies == []


def test_classified_signal_from_raw():
    data = {
        "category": "vendor_search",
        "relevance_score": 5,
        "summary": "Test summary",
        "entities": ["Bayer", "McCain"],
    }
    signal = ClassifiedSignal.from_raw(data)
    assert signal.category == Category.VENDOR_SEARCH
    assert signal.relevance_score == 5
    assert signal.entities.companies == ["Bayer", "McCain"]


def test_classified_signal_from_raw_with_dict_entities():
    data = {
        "category": "expansion",
        "relevance_score": 3,
        "summary": "Test",
        "entities": {
            "companies": ["Lamb Weston"],
            "people": [],
            "products": ["YieldSense"],
        },
    }
    signal = ClassifiedSignal.from_raw(data)
    assert signal.entities.products == ["YieldSense"]
