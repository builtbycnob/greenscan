"""GreenScan pipeline orchestrator."""

import asyncio
import logging
import sys

from pipeline.brief.generator import generate_brief
from pipeline.classifier.categorizer import classify_signals
from pipeline.classifier.llm import LLMClient
from pipeline.delivery.telegram import send_brief, send_failure_alert
from pipeline.enrichment.dedup import Deduplicator
from pipeline.enrichment.linker import link_entities
from pipeline.scraper.registry import get_scrapable_targets, load_targets
from pipeline.scraper.web import scrape_targets
from pipeline.storage.db import Database

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


async def run_demo(max_targets: int = 3) -> None:
    """E2E demo: scrape → dedup → classify → brief → deliver."""
    targets = load_targets()
    scrapable = get_scrapable_targets(targets)[:max_targets]

    if not scrapable:
        logger.error("No scrapable targets found")
        return

    logger.info(f"=== GreenScan Demo — {len(scrapable)} targets ===")

    # Stage 1: Scrape
    logger.info("Stage 1: Scraping...")
    raw_signals = await scrape_targets(scrapable)
    logger.info(f"Got {len(raw_signals)} raw signals")

    if not raw_signals:
        logger.warning("No signals scraped. Check target URLs.")
        return

    # Stage 2: Dedup
    logger.info("Stage 2: Deduplicating...")
    dedup = Deduplicator()
    unique_signals = dedup.filter(raw_signals)
    logger.info(f"{len(unique_signals)} unique signals after dedup")

    if not unique_signals:
        logger.info("All signals were duplicates. Nothing new.")
        return

    # Stage 3: Classify (batch of up to 5)
    logger.info("Stage 3: Classifying...")
    async with LLMClient() as client:
        classified = await classify_signals(
            client,
            [s.model_dump() for s in unique_signals[:5]],
        )

    # Print classified signals
    for i, (raw, cls) in enumerate(zip(unique_signals[:5], classified), 1):
        score_bar = "🟢" * cls.relevance_score + "⚪" * (5 - cls.relevance_score)
        print(f"\n--- Signal {i} ---")
        print(f"Source:   {raw.source}")
        print(f"Category: {cls.category.value}")
        print(f"Score:    {score_bar} ({cls.relevance_score}/5)")
        print(f"Summary:  {cls.summary}")

    # Stage 4: Generate brief
    logger.info("Stage 4: Generating brief...")
    brief = await generate_brief(unique_signals[:5], classified, min_score=2)

    if brief:
        print(f"\n{'=' * 60}")
        print("BATTLEFIELD BRIEF")
        print(f"{'=' * 60}")
        print(brief)

        # Stage 5: Deliver
        logger.info("Stage 5: Delivering via Telegram...")
        await send_brief(brief)
    else:
        logger.info("No brief generated (no signals above threshold)")

    # Summary
    high = sum(1 for c in classified if c.relevance_score >= 4)
    print("\n--- Pipeline Complete ---")
    print(f"Scraped: {len(raw_signals)} | Unique: {len(unique_signals)}")
    print(f"Classified: {len(classified)} | High relevance: {high}")


async def run_daily() -> None:
    """Full daily pipeline run with DB persistence and logging."""
    import time
    import uuid

    run_id = str(uuid.uuid4())[:8]
    start_time = time.monotonic()

    try:
        async with Database() as db:
            targets = load_targets()
            scrapable = get_scrapable_targets(targets)
            logger.info(f"=== Daily Pipeline {run_id} — {len(scrapable)} targets ===")

            log_id = await db.start_scrape_log(run_id, len(scrapable))

            # Scrape
            raw_signals = await scrape_targets(scrapable)
            if not raw_signals:
                logger.warning("No signals scraped")
                await db.finish_scrape_log(
                    log_id,
                    status="success",
                    targets_success=0,
                    duration_ms=int((time.monotonic() - start_time) * 1000),
                )
                return

            # Dedup against DB
            known_hashes = await db.load_known_hashes()
            dedup = Deduplicator(known_hashes)
            unique = dedup.filter(raw_signals)

            if not unique:
                logger.info("No new signals")
                await db.finish_scrape_log(
                    log_id,
                    status="success",
                    targets_success=len(raw_signals),
                    signals_deduped=len(raw_signals),
                    duration_ms=int((time.monotonic() - start_time) * 1000),
                )
                return

            # Classify in batches of 5
            all_classified = []
            async with LLMClient() as client:
                for i in range(0, len(unique), 5):
                    batch = unique[i : i + 5]
                    classified = await classify_signals(
                        client,
                        [s.model_dump() for s in batch],
                    )
                    all_classified.extend(classified)

            # Link entities to companies/contacts
            await link_entities(db._pool, all_classified)

            # Store in DB
            inserted = await db.insert_signals_batch(unique, all_classified)
            logger.info(f"Stored {inserted} signals in DB")

            # Generate brief (min_score=1: always generate if there are signals)
            brief = await generate_brief(unique, all_classified, min_score=1)
            if brief:
                await db.save_brief(brief, len(all_classified))
                await send_brief(brief)
                logger.info("Brief delivered and saved")

            # Log success
            duration_ms = int((time.monotonic() - start_time) * 1000)
            await db.finish_scrape_log(
                log_id,
                status="success",
                targets_success=len(scrapable),
                signals_new=inserted,
                signals_deduped=len(raw_signals) - len(unique),
                duration_ms=duration_ms,
                metadata={
                    "total_scraped": len(raw_signals),
                    "total_classified": len(all_classified),
                    "brief_generated": brief is not None,
                },
            )
            logger.info(f"Pipeline {run_id} complete in {duration_ms}ms")

    except Exception as e:
        logger.exception(f"Pipeline {run_id} failed: {e}")
        try:
            async with Database() as db:
                await db.finish_scrape_log(
                    log_id,
                    status="failure",
                    error_message=str(e),
                    duration_ms=int((time.monotonic() - start_time) * 1000),
                )
        except Exception:
            pass
        await send_failure_alert(str(e), "daily_pipeline")


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "demo"
    if mode == "demo":
        asyncio.run(run_demo())
    elif mode == "daily":
        asyncio.run(run_daily())
    else:
        print("Usage: python -m pipeline.main [demo|daily]")
        sys.exit(1)


if __name__ == "__main__":
    main()
