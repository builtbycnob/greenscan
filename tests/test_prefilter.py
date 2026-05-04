"""Unit tests for the pre-classification event filter."""

from pipeline.classifier.prefilter import (
    MIN_CONTENT_CHARS,
    filter_event_signals,
    is_event_signal,
)
from pipeline.scraper.models import RawSignal


def _signal(title: str, content: str, source: str = "Acme") -> RawSignal:
    return RawSignal(
        url="https://example.com/x",
        title=title,
        content=content,
        source=source,
    )


def test_event_signal_with_announce_verb_passes():
    s = _signal(
        title="Acme launches new yield monitor",
        content=(
            "Acme today announced the launch of a new universal retrofit yield "
            "monitor for combine harvesters. The product targets European farms."
        ),
    )
    assert is_event_signal(s) is True


def test_event_signal_with_partnership_verb_passes():
    s = _signal(
        title="Acme partners with Bayer",
        content=(
            "Acme has signed a strategic partnership with Bayer Crop Science to "
            "integrate yield data into the FieldView platform across 300 farms."
        ),
    )
    assert is_event_signal(s) is True


def test_static_page_without_event_verb_rejected():
    s = _signal(
        title="About us",
        content=(
            "Acme is a precision agriculture company headquartered in Brescia. "
            "Our mission is sustainable farming. Contact us via the form below."
        ),
    )
    assert is_event_signal(s) is False


def test_too_short_content_rejected():
    s = _signal(
        title="News",
        content="Short.",
    )
    assert is_event_signal(s) is False
    assert len("Short.") < MIN_CONTENT_CHARS


def test_filter_event_signals_keeps_only_events():
    sigs = [
        _signal(
            "Acme launches monitor",
            "Acme announced today the launch of its new universal retrofit yield "
            "monitor for combine harvesters across European markets.",
        ),
        _signal(
            "About",
            "Acme is a precision agriculture company. Our mission. Our values. "
            "Our offices. Contact us via the form on this page below the footer.",
        ),
        _signal(
            "Bayer raises round",
            "Bayer Crop Science raised a $200M Series C funding round this morning "
            "to expand its R&D division and accelerate digital ag products.",
        ),
    ]
    out = filter_event_signals(sigs)
    assert len(out) == 2
    assert out[0].title == "Acme launches monitor"
    assert out[1].title == "Bayer raises round"
