"""Contact discovery for customer signals.

Enriches signals with LinkedIn contact info for decision-makers.
Uses Serper.dev SERP queries to find LinkedIn profiles.
"""

import logging

from pipeline.classifier.categorizer import ClassifiedSignal
from pipeline.config import settings
from pipeline.scraper.serp import search_company_leaders, search_linkedin_contact

logger = logging.getLogger(__name__)


class ContactResult:
    """Contact found for a signal."""

    def __init__(
        self,
        name: str,
        headline: str,
        linkedin_url: str,
        source: str,
    ):
        self.name = name
        self.headline = headline
        self.linkedin_url = linkedin_url
        self.source = source  # "signal_mention" or "company_lookup"

    def format_for_brief(self) -> str:
        """Format contact for brief output."""
        prefix = "🔍 " if self.source == "company_lookup" else ""
        return f"{prefix}[{self.name}]({self.linkedin_url}) — {self.headline}"


async def discover_contacts(
    classified: list[ClassifiedSignal],
    target_types: list[str],
    source_names: list[str],
    signal_keys: list[str] | None = None,
    decision_maker_titles: dict[str, list[str]] | None = None,
) -> dict[str, list[ContactResult]]:
    """Discover contacts for customer signals above threshold.

    Args:
        classified: classified signals
        target_types: parallel list of "customer" or "competitor"
        source_names: parallel list of target/source names
        signal_keys: parallel list of stable keys (content_hash) for each signal
        decision_maker_titles: map of source_name → list of titles from YAML

    Returns:
        dict mapping signal key (content_hash) → list of ContactResult.
        If signal_keys not provided, falls back to string index keys.
    """
    if not settings.serper_api_key:
        logger.info("Serper not configured, skipping contact discovery")
        return {}

    if decision_maker_titles is None:
        decision_maker_titles = {}
    if signal_keys is None:
        signal_keys = [str(i) for i in range(len(classified))]

    contacts_by_key: dict[str, list[ContactResult]] = {}
    lookups_done = 0
    cap = settings.serper_daily_contact_cap

    for cls, ttype, source, key in zip(classified, target_types, source_names, signal_keys):
        if lookups_done >= cap:
            logger.info(f"Contact lookup cap reached ({cap})")
            break

        # Only for customers above threshold
        if ttype != "customer":
            continue
        if cls.relevance_score < settings.contact_min_score:
            continue

        contacts = []
        people = cls.entities.people if cls.entities else []

        if people:
            # Direct match: people mentioned in signal
            for person in people[:3]:
                if lookups_done >= cap:
                    break
                result = await search_linkedin_contact(person, source)
                lookups_done += 1
                if result:
                    contacts.append(
                        ContactResult(
                            name=result["name"],
                            headline=result["headline"],
                            linkedin_url=result["linkedin_url"],
                            source="signal_mention",
                        )
                    )
        else:
            # Company lookup: use decision_maker_titles from YAML
            titles = decision_maker_titles.get(source)
            results = await search_company_leaders(source, titles)
            lookups_done += 1
            for r in results:
                contacts.append(
                    ContactResult(
                        name=r["name"],
                        headline=r["headline"],
                        linkedin_url=r["linkedin_url"],
                        source="company_lookup",
                    )
                )

        if contacts:
            contacts_by_key[key] = contacts
            logger.info(f"Found {len(contacts)} contacts for {source} ({key[:12]})")

    logger.info(
        f"Contact discovery: {lookups_done} Serper lookups, "
        f"{sum(len(c) for c in contacts_by_key.values())} contacts found"
    )
    return contacts_by_key
