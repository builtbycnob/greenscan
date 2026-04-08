"""Serper.dev API client for SERP queries (contact lookup + future signal monitoring)."""

import logging

import httpx

from pipeline.config import settings

logger = logging.getLogger(__name__)

SERPER_URL = "https://google.serper.dev/search"


async def search(query: str, num_results: int = 5) -> list[dict]:
    """Execute a SERP query via Serper.dev.

    Returns list of organic results: [{title, link, snippet}, ...]
    """
    if not settings.serper_api_key:
        logger.warning("SERPER_API_KEY not configured, skipping search")
        return []

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            SERPER_URL,
            headers={
                "X-API-KEY": settings.serper_api_key,
                "Content-Type": "application/json",
            },
            json={"q": query, "num": num_results},
        )
        resp.raise_for_status()
        data = resp.json()

    results = []
    for item in data.get("organic", []):
        results.append(
            {
                "title": item.get("title", ""),
                "link": item.get("link", ""),
                "snippet": item.get("snippet", ""),
            }
        )
    return results


def parse_linkedin_result(result: dict) -> dict | None:
    """Extract name, headline, and LinkedIn URL from a SERP result.

    Returns {name, headline, linkedin_url} or None if not a LinkedIn profile.
    """
    link = result.get("link", "")
    if "linkedin.com/in/" not in link:
        return None

    title = result.get("title", "")
    snippet = result.get("snippet", "")

    # LinkedIn titles are typically "Name - Title - Company | LinkedIn"
    # or "Name — Title — Company | LinkedIn"
    name = ""
    headline = ""

    # Remove "| LinkedIn" suffix
    clean_title = title.replace(" | LinkedIn", "").replace("| LinkedIn", "")

    # Split on " - " or " — " or " – "
    parts = []
    for sep in [" - ", " — ", " – "]:
        if sep in clean_title:
            parts = [p.strip() for p in clean_title.split(sep)]
            break

    if parts:
        name = parts[0]
        headline = " - ".join(parts[1:]) if len(parts) > 1 else ""
    else:
        name = clean_title.strip()

    if not name:
        return None

    # Use snippet as headline fallback if title didn't have role info
    if not headline and snippet:
        headline = snippet[:120]

    return {
        "name": name,
        "headline": headline,
        "linkedin_url": link,
    }


async def search_linkedin_contact(
    person_name: str,
    company_name: str,
) -> dict | None:
    """Search for a person's LinkedIn profile via SERP.

    Returns {name, headline, linkedin_url} or None.
    """
    query = f'"{person_name}" site:linkedin.com/in/ {company_name}'
    results = await search(query, num_results=3)

    for r in results:
        parsed = parse_linkedin_result(r)
        if parsed:
            return parsed

    return None


async def search_company_leaders(
    company_name: str,
    titles: list[str] | None = None,
) -> list[dict]:
    """Search for company decision-makers via SERP.

    Args:
        company_name: company to search
        titles: specific titles to search for (e.g., ["CEO", "VP Agronomy"])

    Returns list of {name, headline, linkedin_url}.
    """
    if titles:
        # Search for specific titles
        title_str = " OR ".join(f'"{t}"' for t in titles[:3])
        query = f"{title_str} site:linkedin.com/in/ {company_name}"
    else:
        query = f"CEO OR CTO OR VP site:linkedin.com/in/ {company_name}"

    results = await search(query, num_results=5)
    contacts = []
    for r in results:
        parsed = parse_linkedin_result(r)
        if parsed and parsed not in contacts:
            contacts.append(parsed)

    return contacts[:3]  # Cap at 3 per company
