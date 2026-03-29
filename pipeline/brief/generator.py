"""Battlefield Brief generator using Gemini 2.5 Flash."""

import logging
from datetime import UTC, datetime

import httpx

from pipeline.classifier.categorizer import ClassifiedSignal
from pipeline.config import settings
from pipeline.scraper.models import RawSignal

logger = logging.getLogger(__name__)

BRIEF_SYSTEM_PROMPT = """\
You are a market intelligence analyst for Green Growth Innovations, a precision \
agriculture startup that builds universal retrofit yield monitors for combine \
harvesters and potato harvesters.

Generate a concise Battlefield Brief from today's classified signals. The brief \
helps the founder identify sales opportunities among target customers (large US \
farm operators, food processors, farmland investors, agri-input companies).

Structure:
1. **Executive Summary** — 2-3 sentences on the most important findings
2. **Top Opportunities** — Score 4-5 signals with specific outreach recommendations
3. **Other Signals** — Score 3 signals grouped by category
4. **Key Takeaways** — 2-3 strategic insights
5. **Suggested Actions** — Concrete next steps for the Green Growth team

Keep the brief under 1000 words. Be direct and actionable. Use bullet points.
Output the brief EXACTLY ONCE. Do not repeat any section.\
"""


def _format_signals_for_brief(
    raw_signals: list[RawSignal],
    classified: list[ClassifiedSignal],
) -> str:
    """Format classified signals as input for the brief generator."""
    lines = []
    for raw, cls in zip(raw_signals, classified):
        lines.append(
            f"- [{cls.category.value}] Score {cls.relevance_score}/5 | {raw.source}: {cls.summary}"
        )
    return "\n".join(lines)


async def generate_brief(
    raw_signals: list[RawSignal],
    classified: list[ClassifiedSignal],
    min_score: int = 3,
) -> str | None:
    """Generate a Battlefield Brief from today's classified signals.

    Uses Gemini 2.5 Flash for narrative quality. Falls back to Groq if
    Gemini is not configured.
    """
    pairs = [(r, c) for r, c in zip(raw_signals, classified) if c.relevance_score >= min_score]

    if not pairs:
        logger.info("No signals with score >= %d, skipping brief", min_score)
        return None

    filtered_raw = [p[0] for p in pairs]
    filtered_cls = [p[1] for p in pairs]
    signals_text = _format_signals_for_brief(filtered_raw, filtered_cls)
    today = datetime.now(UTC).strftime("%Y-%m-%d")

    user_prompt = (
        f"Generate the Battlefield Brief for {today}.\n\n"
        f"Today's signals ({len(pairs)} with relevance >= {min_score}):\n"
        f"{signals_text}"
    )

    if settings.gemini_api_key:
        return await _generate_with_gemini(user_prompt)
    return await _generate_with_groq(user_prompt)


async def _generate_with_gemini(user_prompt: str) -> str:
    """Use Gemini 2.5 Flash for brief generation (best narrative quality)."""
    async with httpx.AsyncClient(timeout=60.0) as client:
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
