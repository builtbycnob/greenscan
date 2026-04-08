"""Tests for Serper.dev client (mocked, no API calls)."""

from pipeline.scraper.serp import parse_linkedin_result


def test_parse_linkedin_profile():
    result = {
        "title": "John Smith - VP Agronomy - McCain Foods | LinkedIn",
        "link": "https://www.linkedin.com/in/john-smith-123",
        "snippet": "VP Agronomy at McCain Foods. 15 years in precision ag.",
    }
    parsed = parse_linkedin_result(result)
    assert parsed is not None
    assert parsed["name"] == "John Smith"
    assert "VP Agronomy" in parsed["headline"]
    assert parsed["linkedin_url"] == "https://www.linkedin.com/in/john-smith-123"


def test_parse_linkedin_dash_separator():
    result = {
        "title": "Jane Doe — CEO — Ceres Partners | LinkedIn",
        "link": "https://linkedin.com/in/jane-doe",
        "snippet": "",
    }
    parsed = parse_linkedin_result(result)
    assert parsed is not None
    assert parsed["name"] == "Jane Doe"
    assert "CEO" in parsed["headline"]


def test_parse_non_linkedin():
    result = {
        "title": "Some Page",
        "link": "https://example.com/page",
        "snippet": "Not a LinkedIn profile",
    }
    assert parse_linkedin_result(result) is None


def test_parse_linkedin_company_page():
    """Company pages (not /in/) should be rejected."""
    result = {
        "title": "McCain Foods | LinkedIn",
        "link": "https://linkedin.com/company/mccain-foods",
        "snippet": "",
    }
    assert parse_linkedin_result(result) is None


def test_parse_linkedin_simple_name():
    result = {
        "title": "Bob Johnson | LinkedIn",
        "link": "https://linkedin.com/in/bob-johnson",
        "snippet": "Director of Agronomy at Black Gold Farms",
    }
    parsed = parse_linkedin_result(result)
    assert parsed is not None
    assert parsed["name"] == "Bob Johnson"
    assert "Director of Agronomy" in parsed["headline"]
