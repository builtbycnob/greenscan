"""Discover scrape URLs and RSS feeds for all targets.

One-time discovery script. For each target with monitoring=pending_discovery:
- Checks website accessibility
- Probes common newsroom/blog/press paths
- Probes RSS/Atom feed paths
- Checks HTML <link rel="alternate"> for RSS
- Updates targets.yaml with discovered URLs and monitoring type

Usage:
    uv run python scripts/discover_urls.py              # full run
    uv run python scripts/discover_urls.py --dry-run    # report only, no YAML update
    uv run python scripts/discover_urls.py --limit 10   # process first N pending targets
"""

import asyncio
import logging
import re
import sys
from pathlib import Path

import httpx
import yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
TARGETS_PATH = PROJECT_ROOT / "targets.yaml"

NEWSROOM_PATHS = [
    "/news",
    "/newsroom",
    "/blog",
    "/press-releases",
    "/press",
    "/media",
    "/media-center",
    "/company/news",
    "/about/news",
    "/our-company/news",
    "/about-us/news",
    "/investors/news",
    "/investors/press-releases",
    "/news-events/news-releases",
    "/information-centre/news",
    "/en/our-company/news-and-announcements",
]

RSS_PATHS = [
    "/feed",
    "/rss",
    "/blog/feed",
    "/feed.xml",
    "/atom.xml",
    "/rss.xml",
    "/news/feed",
    "/blog/rss",
    "/feed/rss",
    "/feeds/posts/default",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


async def check_url(client: httpx.AsyncClient, url: str, expect_rss: bool = False) -> bool:
    """Check if a URL returns a valid response."""
    try:
        resp = await client.head(url, follow_redirects=True, timeout=10)
        if resp.status_code < 400:
            if expect_rss:
                content_type = resp.headers.get("content-type", "")
                if any(t in content_type for t in ["xml", "rss", "atom", "text/plain"]):
                    return True
                # HEAD might not give content-type for RSS, try GET
                resp = await client.get(url, follow_redirects=True, timeout=10)
                text = resp.text[:500]
                return "<rss" in text or "<feed" in text or "<channel" in text
            return True
    except (httpx.TimeoutException, httpx.ConnectError, httpx.TooManyRedirects):
        pass
    except Exception:
        pass
    return False


async def find_rss_in_html(client: httpx.AsyncClient, url: str) -> list[str]:
    """Check page HTML for <link rel="alternate" type="application/rss+xml">."""
    feeds = []
    try:
        resp = await client.get(url, follow_redirects=True, timeout=10)
        if resp.status_code >= 400:
            return feeds
        html = resp.text[:50000]
        pattern = (
            r'<link[^>]+type=["\']application/(?:rss|atom)\+xml["\']'
            r'[^>]+href=["\']([^"\']+)["\']'
        )
        matches = re.findall(pattern, html, re.IGNORECASE)
        pattern2 = (
            r'<link[^>]+href=["\']([^"\']+)["\']'
            r'[^>]+type=["\']application/(?:rss|atom)\+xml["\']'
        )
        matches += re.findall(pattern2, html, re.IGNORECASE)
        for href in matches:
            if href.startswith("/"):
                from urllib.parse import urljoin

                href = urljoin(url, href)
            if href.startswith("http"):
                feeds.append(href)
    except Exception:
        pass
    return list(set(feeds))


async def discover_target(
    client: httpx.AsyncClient,
    target: dict,
    semaphore: asyncio.Semaphore,
) -> dict:
    """Discover URLs and feeds for a single target."""
    async with semaphore:
        name = target["name"]
        website = target.get("website", "")
        if not website:
            return {
                "name": name,
                "status": "no_website",
                "scrape_urls": [],
                "rss_feeds": [],
            }

        # Normalize website
        if not website.startswith("http"):
            website = f"https://{website}"
        website = website.rstrip("/")

        logger.info(f"Discovering {name} ({website})...")

        # Check if website is accessible
        accessible = await check_url(client, website)
        if not accessible:
            # Try www variant
            from urllib.parse import urlparse

            parsed = urlparse(website)
            if not parsed.hostname.startswith("www."):
                www_url = f"{parsed.scheme}://www.{parsed.hostname}"
                if parsed.path:
                    www_url += parsed.path
                accessible = await check_url(client, www_url)
                if accessible:
                    website = www_url

        if not accessible:
            logger.warning(f"  {name}: website not accessible")
            return {
                "name": name,
                "status": "inaccessible",
                "scrape_urls": [],
                "rss_feeds": [],
            }

        # Probe newsroom paths
        scrape_urls = []
        probe_tasks = [check_url(client, f"{website}{path}") for path in NEWSROOM_PATHS]
        results = await asyncio.gather(*probe_tasks)
        for path, ok in zip(NEWSROOM_PATHS, results):
            if ok:
                scrape_urls.append(f"{website}{path}")

        # Probe RSS paths
        rss_feeds = []
        rss_tasks = [check_url(client, f"{website}{path}", expect_rss=True) for path in RSS_PATHS]
        rss_results = await asyncio.gather(*rss_tasks)
        for path, ok in zip(RSS_PATHS, rss_results):
            if ok:
                rss_feeds.append(f"{website}{path}")

        # Check HTML for RSS links
        html_feeds = await find_rss_in_html(client, website)
        for feed in html_feeds:
            if feed not in rss_feeds:
                rss_feeds.append(feed)

        status = "found" if scrape_urls or rss_feeds else "no_urls_found"
        if scrape_urls:
            logger.info(f"  {name}: {len(scrape_urls)} URLs, {len(rss_feeds)} RSS")
        elif rss_feeds:
            logger.info(f"  {name}: {len(rss_feeds)} RSS only")
        else:
            logger.info(f"  {name}: no URLs or RSS found")

        return {
            "name": name,
            "status": status,
            "scrape_urls": scrape_urls[:3],  # Cap at 3 best URLs
            "rss_feeds": rss_feeds[:2],  # Cap at 2 feeds
        }


def classify_monitoring(target: dict) -> str:
    """Determine monitoring type based on discovered resources."""
    has_urls = bool(target.get("scrape_urls"))
    has_rss = bool(target.get("rss_feeds"))
    if has_urls and has_rss:
        return "direct_scrape_and_rss"
    if has_urls:
        return "direct_scrape"
    if has_rss:
        return "rss"
    return "serp_only"


async def run_discovery(dry_run: bool = False, limit: int | None = None):
    """Run URL discovery for all pending targets."""
    with open(TARGETS_PATH) as f:
        data = yaml.safe_load(f)

    targets = data["targets"]
    pending = [(i, t) for i, t in enumerate(targets) if t.get("monitoring") == "pending_discovery"]

    if limit:
        pending = pending[:limit]

    logger.info(f"Discovering URLs for {len(pending)} pending targets...")

    semaphore = asyncio.Semaphore(10)  # Max 10 concurrent
    async with httpx.AsyncClient(headers=HEADERS) as client:
        tasks = [discover_target(client, t, semaphore) for _, t in pending]
        results = await asyncio.gather(*tasks)

    # Build results index
    results_by_name = {r["name"]: r for r in results}

    # Stats
    found_urls = sum(1 for r in results if r["scrape_urls"])
    found_rss = sum(1 for r in results if r["rss_feeds"])
    inaccessible = sum(1 for r in results if r["status"] == "inaccessible")
    no_website = sum(1 for r in results if r["status"] == "no_website")

    print(f"\n{'=' * 60}")
    print("DISCOVERY REPORT")
    print(f"{'=' * 60}")
    print(f"Targets scanned:    {len(pending)}")
    print(f"Found scrape URLs:  {found_urls}")
    print(f"Found RSS feeds:    {found_rss}")
    print(f"Inaccessible:       {inaccessible}")
    print(f"No website:         {no_website}")
    serp_only = len(pending) - found_urls - found_rss - inaccessible - no_website
    print(f"Serp-only (no URLs):{serp_only}")

    # Detailed report
    print("\n--- Targets with discovered URLs ---")
    for r in sorted(results, key=lambda x: x["name"]):
        if r["scrape_urls"] or r["rss_feeds"]:
            urls = ", ".join(r["scrape_urls"][:2])
            rss = ", ".join(r["rss_feeds"][:1])
            print(f"  {r['name']:40s} URLs: {urls or '-':50s} RSS: {rss or '-'}")

    print("\n--- Inaccessible websites ---")
    for r in sorted(results, key=lambda x: x["name"]):
        if r["status"] == "inaccessible":
            t = next(t for _, t in pending if t["name"] == r["name"])
            print(f"  {r['name']:40s} {t.get('website', 'N/A')}")

    if dry_run:
        print("\n[DRY RUN] No changes written to targets.yaml")
        return

    # Apply discoveries to targets
    updated = 0
    for i, target in enumerate(targets):
        name = target["name"]
        if name in results_by_name:
            r = results_by_name[name]
            if r["scrape_urls"] and not target.get("scrape_urls"):
                target["scrape_urls"] = r["scrape_urls"]
            if r["rss_feeds"] and not target.get("rss_feeds"):
                target["rss_feeds"] = r["rss_feeds"]
            if target.get("monitoring") == "pending_discovery":
                target["monitoring"] = classify_monitoring(target)
                updated += 1

    # Write updated YAML
    class YamlDumper(yaml.SafeDumper):
        pass

    def str_representer(dumper, data):
        if "\n" in data:
            return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
        return dumper.represent_scalar("tag:yaml.org,2002:str", data)

    YamlDumper.add_representer(str, str_representer)

    with open(TARGETS_PATH, "w") as f:
        customers = [t for t in targets if t["type"] == "customer"]
        competitors = [t for t in targets if t["type"] == "competitor"]
        n_cust, n_comp = len(customers), len(competitors)
        f.write("# GreenScan — Target Companies & Competitors\n")
        f.write("# Updated with URL discovery results.\n")
        f.write(f"# Total: {len(targets)} ({n_cust} customers + {n_comp} competitors)\n\n")
        yaml.dump(
            data,
            f,
            Dumper=YamlDumper,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
            width=120,
        )

    print(f"\nUpdated {updated} targets in {TARGETS_PATH}")


def main():
    dry_run = "--dry-run" in sys.argv
    limit = None
    for i, arg in enumerate(sys.argv):
        if arg == "--limit" and i + 1 < len(sys.argv):
            limit = int(sys.argv[i + 1])
    asyncio.run(run_discovery(dry_run=dry_run, limit=limit))


if __name__ == "__main__":
    main()
