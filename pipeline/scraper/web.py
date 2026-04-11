"""Web scraper using Crawl4AI with stealth mode and content filtering."""

import logging

from crawl4ai import (
    AsyncWebCrawler,
    BrowserConfig,
    CacheMode,
    CrawlerRunConfig,
    MemoryAdaptiveDispatcher,
)
from crawl4ai.content_filter_strategy import PruningContentFilter
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator

from pipeline.config import settings
from pipeline.scraper.models import RawSignal
from pipeline.scraper.registry import Target

logger = logging.getLogger(__name__)


def _build_browser_config() -> BrowserConfig:
    return BrowserConfig(
        headless=True,
        verbose=False,
        extra_args=["--disable-gpu", "--no-sandbox"],
    )


def _build_run_config() -> CrawlerRunConfig:
    return CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        stream=True,
        wait_until="domcontentloaded",
        markdown_generator=DefaultMarkdownGenerator(
            content_filter=PruningContentFilter(
                threshold=0.4,
                threshold_type="dynamic",
            ),
        ),
    )


def _build_dispatcher() -> MemoryAdaptiveDispatcher:
    return MemoryAdaptiveDispatcher(
        max_session_permit=settings.scraper_max_concurrent,
        memory_threshold_percent=70.0,
    )


async def scrape_targets(targets: list[Target]) -> list[RawSignal]:
    """Scrape all URLs from targets that have scrape_urls defined.

    Returns a flat list of RawSignal objects. Failed URLs are logged and skipped.
    """
    url_to_target: dict[str, Target] = {}
    for target in targets:
        for url in target.scrape_urls:
            url_to_target[url] = target

    if not url_to_target:
        logger.warning("No URLs to scrape")
        return []

    urls = list(url_to_target.keys())
    logger.info(f"Scraping {len(urls)} URLs from {len(targets)} targets")

    signals: list[RawSignal] = []
    browser_config = _build_browser_config()
    run_config = _build_run_config()
    dispatcher = _build_dispatcher()

    failed = 0
    skipped = 0

    async with AsyncWebCrawler(config=browser_config) as crawler:
        async for result in await crawler.arun_many(
            urls=urls,
            config=run_config,
            dispatcher=dispatcher,
        ):
            if not result.success:
                logger.warning(f"Failed to scrape {result.url}: {result.error_message}")
                failed += 1
                continue

            content = result.markdown.fit_markdown or result.markdown.raw_markdown
            if not content or len(content.strip()) < 50:
                logger.info(f"Skipped {result.url}: content too short")
                skipped += 1
                continue

            target = url_to_target.get(result.url)
            source_name = target.name if target else "Unknown"

            signals.append(
                RawSignal(
                    url=result.url,
                    title=(result.extracted_content or "Untitled")[:200],
                    content=content[:5000],
                    source=source_name,
                )
            )

    logger.info(
        f"Web scrape: {len(signals)}/{len(urls)} success, "
        f"{failed} failed, {skipped} skipped (too short)"
    )
    return signals
