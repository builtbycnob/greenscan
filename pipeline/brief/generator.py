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

Generate a concise Battlefield Brief from today's signals. Focus on CONCRETE \
NEWS, PEOPLE, and LINKS — not generic strategy advice.

Structure:
1. **Executive Summary** — 2-3 sentences on what happened today

2. **Signals** — For EACH signal, include:
   - What happened (the actual news)
   - Source link (the URL)
   - People mentioned (name, title, LinkedIn if findable)
   - Company website
   - Why it matters for Green Growth (1 sentence max)

3. **People to Watch** — List any named individuals with their role and company. \
These are potential champions or decision-makers for Green Growth.

Rules:
- Include source URLs for every signal
- Include company website links
- Name specific people with their titles whenever mentioned
- Do NOT include generic "Key Takeaways" or "Suggested Actions" sections
- Do NOT give generic strategy advice — focus on the actual news content
- Keep it under 800 words
- Output the brief EXACTLY ONCE. Do not repeat any section.\
"""


def _format_signals_for_brief(
    raw_signals: list[RawSignal],
    classified: list[ClassifiedSignal],
) -> str:
    """Format classified signals as input for the brief generator."""
    lines = []
    for raw, cls in zip(raw_signals, classified):
        entities = cls.entities.model_dump()
        people = ", ".join(entities.get("people", [])) or "none mentioned"
        companies = ", ".join(entities.get("companies", [])) or raw.source
        lines.append(
            f"--- Signal ---\n"
            f"Source: {raw.source}\n"
            f"URL: {raw.url}\n"
            f"Category: {cls.category.value} | Score: {cls.relevance_score}/5\n"
            f"Summary: {cls.summary}\n"
            f"Companies: {companies}\n"
            f"People: {people}\n"
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
