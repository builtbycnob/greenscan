"""classify_signals must return classifications ALIGNED 1:1 with inputs (None for failures).

Regression guard for the salvage-path positional-misalignment bug: a mid-batch
validation failure must yield None at THAT index, never shift later pairs.
"""

import pytest

from pipeline.classifier.categorizer import classify_signals


class _FakeClient:
    def __init__(self, payload):
        self._payload = payload

    async def classify(self, system_prompt, user_prompt, json_schema=None):
        return self._payload


def _sig(i):
    return {"source": f"S{i}", "url": f"https://e.test/{i}", "title": "t", "content": "content"}


def _item(summary="a valid summary string", score=3, cat="other"):
    return {
        "category": cat,
        "relevance_score": score,
        "summary": summary,
        "entities": {"companies": [], "people": [], "products": []},
    }


@pytest.mark.asyncio
async def test_salvage_preserves_position():
    """A mid-batch invalid item → None at THAT index; neighbors stay correctly paired."""
    signals = [_sig(i) for i in range(4)]
    payload = {
        "signals": [
            _item(summary="zero"),
            _item(summary="one"),
            _item(summary="bad", score=99),  # invalid: relevance_score > 5
            _item(summary="three"),
        ]
    }
    out = await classify_signals(_FakeClient(payload), signals)
    assert len(out) == 4
    assert out[0].summary == "zero"
    assert out[1].summary == "one"
    assert out[2] is None
    assert out[3].summary == "three"


@pytest.mark.asyncio
async def test_extra_classifications_clamped_to_input_length():
    signals = [_sig(i) for i in range(3)]
    payload = {"signals": [_item() for _ in range(5)]}  # LLM returned more than asked
    out = await classify_signals(_FakeClient(payload), signals)
    assert len(out) == 3


@pytest.mark.asyncio
async def test_missing_classifications_padded_with_none():
    signals = [_sig(i) for i in range(3)]
    payload = {"signals": [_item(), _item()]}  # only 2 for 3 inputs
    out = await classify_signals(_FakeClient(payload), signals)
    assert len(out) == 3
    assert out[2] is None
