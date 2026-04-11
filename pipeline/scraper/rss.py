"""RSS feed parser using feedparser + newspaper4k for full text extraction."""

import logging

import feedparser
from newspaper import Article

from pipeline.scraper.models import RawSignal
from pipeline.scraper.registry import Target

logger = logging.getLogger(__name__)


async def parse_rss_feeds(targets: list[Target]) -> list[RawSignal]:
    """Parse RSS feeds for targets that have rss_feeds defined.

    Uses newspaper4k to extract full article text from feed entry URLs.
    """
    signals: list[RawSignal] = []

    for target in targets:
        for feed_url in target.rss_feeds:
            try:
                entries = _parse_feed(feed_url, target.name)
                signals.extend(entries)
            except Exception as e:
                logger.warning(f"Failed to parse RSS {feed_url}: {e}")

    logger.info(f"Parsed {len(signals)} signals from RSS feeds")
    return signals


def _parse_feed(feed_url: str, source_name: str) -> list[RawSignal]:
    """Parse a single RSS feed and extract articles."""
    feed = feedparser.parse(feed_url)
    if feed.bozo and not feed.entries:
        logger.warning(f"Malformed feed {feed_url}: {feed.bozo_exception}")
        return []

    results = []
    extract_failures = 0
    for entry in feed.entries[:20]:
        link = entry.get("link", "")
        title = entry.get("title", "Untitled")

        content = entry.get("summary", "")
        if link and len(content) < 200:
            extracted = _extract_article(link)
            if extracted:
                content = extracted
            else:
                extract_failures += 1

        if not content or len(content.strip()) < 50:
            continue

        results.append(
            RawSignal(
                url=link,
                title=title[:200],
                content=content[:5000],
                source=source_name,
            )
        )

    entries_total = min(len(feed.entries), 20)
    if extract_failures:
        logger.info(
            f"RSS {source_name}: {len(results)}/{entries_total} entries, "
            f"{extract_failures} article extractions failed"
        )
    return results


def _extract_article(url: str) -> str | None:
    """Extract full article text using newspaper4k."""
    try:
        article = Article(url)
        article.download()
        article.parse()
        return article.text if article.text else None
    except Exception as e:
        logger.debug(f"Article extraction failed for {url}: {e}")
        return None
