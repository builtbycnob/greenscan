"""One failed classify batch must not abort the run; alignment is preserved."""

import pytest

from pipeline.classifier.categorizer import Category, ClassifiedSignal
from pipeline.classifier.llm import LLMError
from pipeline.scraper.models import RawSignal


def _sig(i):
    return RawSignal(
        source=f"S{i}", url=f"https://e.test/{i}", title=f"t{i}", content=f"content {i} " * 5
    )


def _classified(tag):
    return ClassifiedSignal(
        category=Category.OTHER, relevance_score=3, summary=f"summary {tag} ..."
    )


@pytest.mark.asyncio
async def test_failed_batch_skipped_alignment_preserved(monkeypatch):
    from pipeline import main as m

    signals = [_sig(i) for i in range(6)]
    types = ["customer"] * 6

    async def fake_classify(client, batch_dicts, target_types=None):
        # The batch starting with S2 (2nd batch, size 2) fails entirely.
        if batch_dicts[0]["source"] == "S2":
            raise LLMError("all providers down for this batch")
        return [_classified(d["source"]) for d in batch_dicts]

    monkeypatch.setattr(m, "classify_signals", fake_classify)

    processed, classified, out_types = await m._classify_in_batches(
        client=object(), signals=signals, types=types, batch_size=2
    )

    # Batch [S2, S3] dropped; 4 signals survive, perfectly aligned.
    assert [s.source for s in processed] == ["S0", "S1", "S4", "S5"]
    assert len(classified) == len(processed) == len(out_types) == 4


@pytest.mark.asyncio
async def test_none_classification_dropped_keeps_alignment(monkeypatch):
    """A None classification (salvage drop) removes only THAT signal; rest stay paired."""
    from pipeline import main as m

    signals = [_sig(i) for i in range(4)]
    types = ["customer"] * 4

    async def fake_classify(client, batch_dicts, target_types=None):
        # Aligned list with a None in the middle (S1 failed validation).
        return [None if d["source"] == "S1" else _classified(d["source"]) for d in batch_dicts]

    monkeypatch.setattr(m, "classify_signals", fake_classify)

    processed, classified, out_types = await m._classify_in_batches(
        client=object(), signals=signals, types=types, batch_size=4
    )
    assert [s.source for s in processed] == ["S0", "S2", "S3"]
    assert len(classified) == len(processed) == len(out_types) == 3
