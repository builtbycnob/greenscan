"""Deep URL discovery for serp-only targets.

More aggressive probing than discover_urls.py:
- Sitemap.xml parsing
- Localized paths (/en/, /de/, /nl/, /fr/, /it/)
- IR/investor-specific paths for public companies
- Broader newsroom path variants
- www/non-www fallback
- Checks actual page content length (not just HTTP 200)
"""

import asyncio
import logging
import re
import sys

import httpx
import yaml

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Extended newsroom paths (broader than discover_urls.py)
NEWS_PATHS = [
    "/news",
    "/newsroom",
    "/blog",
    "/press",
    "/press-releases",
    "/media",
    "/media-center",
    "/media-centre",
    "/company/news",
    "/about/news",
    "/about-us/news",
    "/our-company/news",
    "/investors/news",
    "/investors/press-releases",
    "/news-events",
    "/news-events/news-releases",
    "/information-centre/news",
    "/en/news",
    "/en/newsroom",
    "/en/press",
    "/en/media",
    "/en/our-company/news",
    "/de/news",
    "/de/presse",
    "/de/aktuelles",
    "/nl/nieuws",
    "/fr/actualites",
    "/it/news",
    "/it/notizie",
    "/insights",
    "/resources/news",
    "/resources/blog",
    "/sustainability/news",
    "/agronomy/news",
    "/about/press-releases",
    "/corporate/news",
    "/news-and-events",
    "/latest-news",
    "/whats-new",
    "/updates",
    "/announcements",
    # IR-specific
    "/investor-relations",
    "/investors",
    "/investor-relations/press-releases",
    "/investor-relations/news",
]

RSS_PATHS = [
    "/feed",
    "/rss",
    "/feed.xml",
    "/rss.xml",
    "/atom.xml",
    "/blog/feed",
    "/news/feed",
    "/en/feed",
    "/feeds/posts/default",
    "/blog/rss.xml",
]


async def check_page(client: httpx.AsyncClient, url: str) -> dict | None:
    """Check if URL returns meaningful content (not just a redirect/shell)."""
    try:
        resp = await client.get(url, follow_redirects=True, timeout=12)
        if resp.status_code >= 400:
            return None
        text = resp.text
        # Must have substantial content (not empty shell or redirect page)
        if len(text) < 500:
            return None
        # Check it's not just a generic homepage redirect
        final_url = str(resp.url)
        return {"url": url, "final_url": final_url, "length": len(text)}
    except Exception:
        return None


async def check_rss(client: httpx.AsyncClient, url: str) -> bool:
    """Check if URL is a valid RSS/Atom feed."""
    try:
        resp = await client.get(url, follow_redirects=True, timeout=10)
        if resp.status_code >= 400:
            return False
        text = resp.text[:1000]
        return "<rss" in text or "<feed" in text or "<channel" in text
    except Exception:
        return False


async def find_rss_in_html(client: httpx.AsyncClient, url: str) -> list[str]:
    """Extract RSS links from HTML source."""
    feeds = []
    try:
        resp = await client.get(url, follow_redirects=True, timeout=10)
        if resp.status_code >= 400:
            return feeds
        html = resp.text[:80000]
        from urllib.parse import urljoin

        for pattern in [
            r'<link[^>]+type=["\']application/(?:rss|atom)\+xml["\'][^>]+href=["\']([^"\']+)',
            r'<link[^>]+href=["\']([^"\']+)["\'][^>]+type=["\']application/(?:rss|atom)\+xml',
        ]:
            for href in re.findall(pattern, html, re.I):
                full = urljoin(url, href) if href.startswith("/") else href
                if full.startswith("http"):
                    feeds.append(full)
    except Exception:
        pass
    return list(set(feeds))


async def parse_sitemap(client: httpx.AsyncClient, base_url: str) -> list[str]:
    """Try to find news/blog URLs from sitemap.xml."""
    news_urls = []
    for sitemap_path in ["/sitemap.xml", "/sitemap_index.xml", "/sitemap-news.xml"]:
        try:
            resp = await client.get(f"{base_url}{sitemap_path}", follow_redirects=True, timeout=10)
            if resp.status_code >= 400:
                continue
            text = resp.text
            # Find URLs that look like news/blog/press pages
            urls = re.findall(r"<loc>(https?://[^<]+)</loc>", text)
            for u in urls:
                lower = u.lower()
                if any(
                    kw in lower
                    for kw in [
                        "/news",
                        "/blog",
                        "/press",
                        "/media",
                        "/aktuell",
                        "/nieuw",
                        "/actual",
                        "/notiz",
                    ]
                ):
                    news_urls.append(u)
            if news_urls:
                break
        except Exception:
            continue
    return news_urls[:5]


async def discover_target(client: httpx.AsyncClient, target: dict, sem: asyncio.Semaphore) -> dict:
    """Deep discovery for a single target."""
    async with sem:
        name = target["name"]
        website = target.get("website", "")
        if not website:
            return {"name": name, "scrape_urls": [], "rss_feeds": [], "notes": "no website"}

        if not website.startswith("http"):
            website = f"https://{website}"
        website = website.rstrip("/")

        # Try base URL accessibility (with www fallback)
        base_ok = await check_page(client, website)
        if not base_ok:
            from urllib.parse import urlparse

            p = urlparse(website)
            if not p.hostname.startswith("www."):
                www = f"{p.scheme}://www.{p.hostname}"
                base_ok = await check_page(client, www)
                if base_ok:
                    website = www

        if not base_ok:
            return {"name": name, "scrape_urls": [], "rss_feeds": [], "notes": "inaccessible"}

        # Probe all news paths
        scrape_urls = []
        tasks = [check_page(client, f"{website}{p}") for p in NEWS_PATHS]
        results = await asyncio.gather(*tasks)
        for path, result in zip(NEWS_PATHS, results):
            if result:
                # Skip if it just redirects to homepage
                if result["final_url"].rstrip("/") != website.rstrip("/"):
                    scrape_urls.append(result["final_url"])

        # Check sitemap
        sitemap_urls = await parse_sitemap(client, website)
        for u in sitemap_urls:
            if u not in scrape_urls:
                scrape_urls.append(u)

        # Probe RSS
        rss_feeds = []
        rss_tasks = [check_rss(client, f"{website}{p}") for p in RSS_PATHS]
        rss_results = await asyncio.gather(*rss_tasks)
        for path, ok in zip(RSS_PATHS, rss_results):
            if ok:
                rss_feeds.append(f"{website}{path}")

        # Check HTML for RSS links
        html_feeds = await find_rss_in_html(client, website)
        for f in html_feeds:
            if f not in rss_feeds:
                rss_feeds.append(f)

        # Deduplicate URLs that resolve to same final URL
        seen_finals = set()
        unique_scrape = []
        for u in scrape_urls:
            normalized = u.rstrip("/").lower()
            if normalized not in seen_finals:
                seen_finals.add(normalized)
                unique_scrape.append(u)

        return {
            "name": name,
            "scrape_urls": unique_scrape[:3],
            "rss_feeds": rss_feeds[:2],
            "notes": (
                f"{len(unique_scrape)} URLs, {len(rss_feeds)} RSS"
                if unique_scrape or rss_feeds
                else "nothing found"
            ),
        }


async def main():
    with open("targets.yaml") as f:
        data = yaml.safe_load(f)

    serp_targets = [t for t in data["targets"] if t.get("monitoring") == "serp_only"]
    # Remove duplicates (AGCO appears twice)
    seen = set()
    unique_targets = []
    for t in serp_targets:
        if t["name"] not in seen:
            seen.add(t["name"])
            unique_targets.append(t)

    logger.info(f"Deep discovery for {len(unique_targets)} serp-only targets...")

    sem = asyncio.Semaphore(8)
    async with httpx.AsyncClient(headers=HEADERS, timeout=15) as client:
        tasks = [discover_target(client, t, sem) for t in unique_targets]
        results = await asyncio.gather(*tasks)

    # Report
    found = [r for r in results if r["scrape_urls"] or r["rss_feeds"]]
    nothing = [r for r in results if not r["scrape_urls"] and not r["rss_feeds"]]

    print(f"\n{'=' * 70}")
    print(f"DEEP DISCOVERY REPORT — {len(unique_targets)} targets")
    print(f"{'=' * 70}")
    print(f"Found URLs/RSS: {len(found)}")
    print(f"Still nothing:  {len(nothing)}")

    if found:
        print(f"\n--- FOUND ({len(found)}) ---")
        for r in sorted(found, key=lambda x: x["name"]):
            urls = r["scrape_urls"][:2]
            rss = r["rss_feeds"][:1]
            print(f"\n  {r['name']}")
            for u in urls:
                print(f"    URL: {u}")
            for f in rss:
                print(f"    RSS: {f}")

    if nothing:
        print(f"\n--- STILL NOTHING ({len(nothing)}) ---")
        for r in sorted(nothing, key=lambda x: x["name"]):
            t = next((t for t in unique_targets if t["name"] == r["name"]), {})
            print(f"  {r['name']:45s} {t.get('website', 'N/A'):35s} ({r['notes']})")

    # Apply to targets.yaml if --apply flag
    if "--apply" in sys.argv:
        results_map = {r["name"]: r for r in results}
        updated = 0
        for t in data["targets"]:
            if t["name"] in results_map:
                r = results_map[t["name"]]
                if r["scrape_urls"] and not t.get("scrape_urls"):
                    t["scrape_urls"] = r["scrape_urls"]
                if r["rss_feeds"] and not t.get("rss_feeds"):
                    t["rss_feeds"] = r["rss_feeds"]
                if (r["scrape_urls"] or r["rss_feeds"]) and t["monitoring"] == "serp_only":
                    has_urls = bool(t.get("scrape_urls"))
                    has_rss = bool(t.get("rss_feeds"))
                    if has_urls and has_rss:
                        t["monitoring"] = "direct_scrape_and_rss"
                    elif has_urls:
                        t["monitoring"] = "direct_scrape"
                    elif has_rss:
                        t["monitoring"] = "rss"
                    updated += 1

        class D(yaml.SafeDumper):
            pass

        def sr(dumper, data):
            if "\n" in data:
                return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
            return dumper.represent_scalar("tag:yaml.org,2002:str", data)

        D.add_representer(str, sr)

        with open("targets.yaml", "w") as f:
            c = [t for t in data["targets"] if t["type"] == "customer"]
            k = [t for t in data["targets"] if t["type"] == "competitor"]
            nc, nk = len(c), len(k)
            f.write("# GreenScan — Target Companies & Competitors\n")
            f.write(f"# Total: {len(data['targets'])} ({nc} cust + {nk} comp)\n\n")
            yaml.dump(
                data,
                f,
                Dumper=D,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
                width=120,
            )
        print(f"\nApplied {updated} updates to targets.yaml")
    else:
        print("\nRun with --apply to update targets.yaml")


if __name__ == "__main__":
    asyncio.run(main())
