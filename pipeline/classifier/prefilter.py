"""Pre-classification filter: skip non-event signals to save LLM calls.

The classifier system prompt already scores static pages as 0, but we still
pay for the LLM call. This pre-filter rejects obviously non-event content
(navigation pages, product catalogs, missing event verbs) before classification.
"""

from pipeline.scraper.models import RawSignal

EVENT_VERB_TOKENS = (
    "announc",
    "launch",
    "raise",
    "raised",
    "hire",
    "appoint",
    "partner",
    "acquir",
    "merger",
    "merged",
    "expand",
    "invest",
    "deploy",
    "releas",
    "debut",
    "secure",
    "complet",
    "integrat",
    "introduc",
    "unveil",
    "roll out",
    "rollout",
    "sign ",
    "signed ",
    "develop",
    "ipo",
    "funded",
    "funding",
    "won ",
    "wins ",
    "pilot",
    "joint",
    "collaborat",
    "select",
    "chose",
    "chosen",
    "named",
    "promote",
    "promoted",
    "joins ",
    "joined ",
    "leads ",
    "open ",
    "opens ",
    "opened ",
    "build",
    "built",
    "report",
    "reports",
    "reported",
    "shipped",
    "shipping",
    "delivers",
    "delivered",
    "launches",
    "rais",
    "trial",
)

MIN_CONTENT_CHARS = 80
SCAN_HEAD_CHARS = 600


def is_event_signal(signal: RawSignal) -> bool:
    """Return True if the signal looks event-driven (vs a static page)."""
    content = (signal.content or "").strip()
    if len(content) < MIN_CONTENT_CHARS:
        return False
    haystack = (signal.title + " " + content[:SCAN_HEAD_CHARS]).lower()
    return any(token in haystack for token in EVENT_VERB_TOKENS)


def filter_event_signals(signals: list[RawSignal]) -> list[RawSignal]:
    """Keep only signals that look event-driven."""
    return [s for s in signals if is_event_signal(s)]
