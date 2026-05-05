"""Battlefield Brief generator using Gemini 2.5 Flash."""

import asyncio
import logging
from datetime import UTC, datetime

import httpx

from pipeline.classifier.categorizer import ClassifiedSignal
from pipeline.config import settings
from pipeline.scraper.models import RawSignal

logger = logging.getLogger(__name__)

BRIEF_RETRY_MAX_ATTEMPTS = 3
BRIEF_RETRY_BASE_DELAY = 1.0

BRIEF_SYSTEM_PROMPT = """\
You are a market intelligence analyst for Green Growth Innovations, a precision \
agriculture startup that builds universal retrofit yield monitors for combine \
harvesters and potato harvesters.

Generate a concise Battlefield Brief from today's signals. The brief has TWO \
sections matching two intelligence layers:

Structure:
1. **Executive Summary** — 2-3 sentences on what happened today

2. **Opportunity Radar** (customer signals) — Sales opportunities detected:
   - For EACH signal: what happened, source URL, people mentioned with title, \
company website, why it matters for Green Growth (1 sentence max)

3. **Competitive Intelligence** (competitor signals) — Competitive moves:
   - For EACH signal: what the competitor did, source URL, threat assessment \
(1 sentence), how Green Growth should respond (1 sentence max)

4. **People to Watch** — Named individuals from BOTH sections with role, \
company, and why they matter (potential champions OR competitive leaders)

Rules:
- Include source URLs for every signal
- Include company website links
- Name specific people with their titles whenever mentioned
- Do NOT include generic "Key Takeaways" or "Suggested Actions" sections
- Do NOT give generic strategy advice — focus on the actual news content
- If one section has no signals, include the section header with "No signals today"
- HARD LIMIT: 400 words total. Be terse. One line per signal where possible.
- People to Watch: max 5 entries, one short line each (Name — Title @ Company).
- Output the brief EXACTLY ONCE. Do not repeat any section.\
"""


def _format_signals_for_brief(
    raw_signals: list[RawSignal],
    classified: list[ClassifiedSignal],
    target_types: list[str],
) -> tuple[str, str]:
    """Format classified signals into customer and competitor sections.

    Returns (customer_text, competitor_text).
    """
    customer_lines = []
    competitor_lines = []

    for raw, cls, ttype in zip(raw_signals, classified, target_types):
        entities = cls.entities.model_dump()
        people = ", ".join(entities.get("people", [])) or "none mentioned"
        companies = ", ".join(entities.get("companies", [])) or raw.source
        line = (
            f"--- Signal ---\n"
            f"Source: {raw.source}\n"
            f"URL: {raw.url}\n"
            f"Category: {cls.category.value} | Score: {cls.relevance_score}/5\n"
            f"Summary: {cls.summary}\n"
            f"Companies: {companies}\n"
            f"People: {people}\n"
        )
        if ttype == "competitor":
            competitor_lines.append(line)
        else:
            customer_lines.append(line)

    return "\n".join(customer_lines), "\n".join(competitor_lines)


async def generate_brief(
    raw_signals: list[RawSignal],
    classified: list[ClassifiedSignal],
    target_types: list[str] | None = None,
    contacts: dict[str, list] | None = None,
) -> str | None:
    """Generate a Battlefield Brief from today's classified signals.

    Args:
        contacts: optional dict mapping content_hash → list of ContactResult
            (from enrichment.contacts.discover_contacts)

    Uses Gemini 2.5 Flash for narrative quality. Falls back to Groq if
    Gemini is not configured.
    """
    if target_types is None:
        target_types = ["customer"] * len(raw_signals)

    # Filter by score per type
    pairs = []
    for r, c, tt in zip(raw_signals, classified, target_types):
        if tt == "competitor":
            if c.relevance_score >= settings.brief_min_score_competitor:
                pairs.append((r, c, tt))
        elif c.relevance_score >= settings.brief_min_score_customer:
            pairs.append((r, c, tt))

    if not pairs:
        logger.info("No signals above threshold, skipping brief")
        return None

    # Cap competitor signals first
    customer_pairs = [(r, c, t) for r, c, t in pairs if t == "customer"]
    competitor_pairs = [(r, c, t) for r, c, t in pairs if t == "competitor"]
    competitor_pairs = sorted(competitor_pairs, key=lambda x: x[1].relevance_score, reverse=True)[
        : settings.competitor_signals_cap
    ]
    # Then enforce a hard total cap, keeping the highest-scoring customer
    # signals and all competitor signals (already capped above).
    customer_pairs = sorted(customer_pairs, key=lambda x: x[1].relevance_score, reverse=True)
    customer_budget = max(0, settings.brief_max_total_signals - len(competitor_pairs))
    customer_pairs = customer_pairs[:customer_budget]
    pairs = customer_pairs + competitor_pairs

    filtered_raw = [p[0] for p in pairs]
    filtered_cls = [p[1] for p in pairs]
    filtered_types = [p[2] for p in pairs]

    customer_text, competitor_text = _format_signals_for_brief(
        filtered_raw, filtered_cls, filtered_types
    )

    today = datetime.now(UTC).strftime("%Y-%m-%d")
    n_cust = len(customer_pairs)
    n_comp = len(competitor_pairs)

    # Build contacts section for customer signals (keyed by content_hash)
    contacts_text = ""
    if contacts:
        contact_lines = []
        for raw_signal in filtered_raw:
            contact_list = contacts.get(raw_signal.content_hash, [])
            for c in contact_list:
                prefix = "🔍 " if c.source == "company_lookup" else ""
                contact_lines.append(
                    f"  {prefix}{c.name} — {c.headline} ({c.linkedin_url}) "
                    f"[from: {raw_signal.source}]"
                )
        if contact_lines:
            contacts_text = "\n\nKEY CONTACTS (include in People to Watch):\n" + "\n".join(
                contact_lines
            )

    user_prompt = (
        f"Generate the Battlefield Brief for {today}.\n\n"
        f"OPPORTUNITY RADAR ({n_cust} customer signals):\n"
        f"{customer_text or 'No customer signals today.'}\n\n"
        f"COMPETITIVE INTELLIGENCE ({n_comp} competitor signals):\n"
        f"{competitor_text or 'No competitor signals today.'}"
        f"{contacts_text}"
    )

    if settings.gemini_api_key:
        try:
            return await _generate_with_gemini(user_prompt)
        except Exception as e:
            logger.warning(f"Gemini brief failed: {e}, falling back to Groq")
    return await _generate_with_groq(user_prompt)


async def _generate_with_gemini(user_prompt: str) -> str:
    """Use Gemini 2.5 Flash for brief generation, retrying on 5xx."""
    last_exc: Exception | None = None
    async with httpx.AsyncClient(timeout=60.0) as client:
        for attempt in range(BRIEF_RETRY_MAX_ATTEMPTS):
            try:
                resp = await client.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/"
                    f"{settings.gemini_model}:generateContent",
                    params={"key": settings.gemini_api_key},
                    headers={"Content-Type": "application/json"},
                    json={
                        "contents": [{"parts": [{"text": user_prompt}]}],
                        "systemInstruction": {"parts": [{"text": BRIEF_SYSTEM_PROMPT}]},
                        "generationConfig": {"temperature": 0.3},
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                return data["candidates"][0]["content"]["parts"][0]["text"]
            except httpx.HTTPStatusError as e:
                if e.response.status_code < 500:
                    raise
                last_exc = e
                logger.warning(
                    f"Gemini brief 5xx (attempt {attempt + 1}/{BRIEF_RETRY_MAX_ATTEMPTS}): "
                    f"{e.response.status_code}"
                )
                if attempt < BRIEF_RETRY_MAX_ATTEMPTS - 1:
                    await asyncio.sleep(BRIEF_RETRY_BASE_DELAY * (2**attempt))
    assert last_exc is not None
    raise last_exc


async def _generate_with_groq(user_prompt: str) -> str:
    """Fallback: use Groq for brief generation."""
    from groq import AsyncGroq

    async with AsyncGroq(api_key=settings.groq_api_key) as client:
        response = await client.chat.completions.create(
            model=settings.groq_model,
            messages=[
                {"role": "system", "content": BRIEF_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
        )
        return response.choices[0].message.content
