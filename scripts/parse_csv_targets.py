"""Parse founder's CSV exports into unified targets.yaml.

One-time migration script. Reads 4 CSVs from 'March New List/',
deduplicates EU/US entries, merges with existing verified URLs,
and outputs a new targets.yaml with extended schema.
"""

import csv
import re
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).parent.parent
CSV_DIR = PROJECT_ROOT / "March New List"
EXISTING_TARGETS = PROJECT_ROOT / "targets.yaml"
OUTPUT_TARGETS = PROJECT_ROOT / "targets_new.yaml"

# CSV header rows that are category descriptions, not companies
COMPETITOR_CATEGORY_PREFIXES = ("Direct", "Partial / Indirect", "OEM / Platform")
CUSTOMER_CATEGORY_KEYWORDS = (
    "Direct Farm Operator",
    "Food Processor",
    "Farmland Investor",
    "Cooperative",
    "Agri Input Company",
    "Grain Trader",
    "Sugar Processor",
    "Bank / Lender",
    "Crop Insurance",
)


def normalize_name(name: str) -> str:
    """Normalize company name for dedup matching."""
    name = name.strip()
    # Remove region suffixes like "(EU)", "(US Operations)", "(EU expansion)"
    name = re.sub(r"\s*\((?:EU|US|EU expansion|US Operations)\)\s*$", "", name, flags=re.I)
    # Remove trailing " EU" or " US"
    name = re.sub(r"\s+(EU|US)$", "", name)
    return name.strip()


def dedup_key(name: str) -> str:
    """Generate a lowercase key for dedup."""
    n = normalize_name(name)
    # Remove common suffixes for matching
    for suffix in (" Inc.", " Inc", " LLC", " AG", " Group", " Holdings"):
        n = n.replace(suffix, "")
    return n.lower().strip()


# Explicit name aliases for cross-source dedup
NAME_ALIASES: dict[str, str] = {
    # CSV "John Deere Operations Center" variants → canonical
    "john deere operations center": "John Deere",
    "john deere operations center (eu)": "John Deere",
    "john deere see & spray": "John Deere See & Spray",  # keep separate
    # Trimble variants
    "trimble agriculture (ptx trimble eu)": "Trimble Agriculture",
    "trimble agriculture (ptx trimble)": "Trimble Agriculture",
    "ptx trimble": "Trimble Agriculture",
    # McCain variants — EU and US are separate operations, but merge
    "mccain foods europe (belgium hq)": "McCain Foods",
    "mccain foods usa": "McCain Foods",
    "mccain foods": "McCain Foods",
    # Raven duplicates
    "raven slingshot (cnh)": "Raven Industries (CNH)",
    # CLAAS duplicates
    "claas easy precision farming": "CLAAS (EASY Precision Farming)",
    "claas (easy precision farming)": "CLAAS (EASY Precision Farming)",
    # CNH variants
    "cnh industrial (case ih / new holland afs)": "CNH (Case IH / New Holland AFS Connect)",
    # Corteva variants
    "corteva agriscience / granular": "Corteva Agriscience",
    "granular (corteva agriscience)": "Corteva Agriscience",
    # Bayer variants
    "bayer crop science (us)": "Bayer Crop Science",
    "bayer cropscience europe": "Bayer Crop Science",
    "climate fieldview (bayer)": "Climate FieldView (Bayer)",  # keep separate
    # BASF variants
    "basf agricultural solutions europe": "BASF Agricultural Solutions",
    "basf agricultural solutions": "BASF Agricultural Solutions",
    # Syngenta variants
    "syngenta europe (chemchina)": "Syngenta",
    "syngenta / cropwise": "Syngenta",
    "cropwise (syngenta) eu": "Cropwise (Syngenta)",  # keep separate
    # Cargill
    "cargill europe": "Cargill",
    # xarvio vs BASF
    "xarvio (basf) eu": "xarvio (BASF)",  # keep separate from BASF
    # Proagrica
    "proagrica (relx) eu": "Proagrica (RELX)",
    "proagrica (relx)": "Proagrica (RELX)",
}


def is_header_row(row: list[str], file_type: str) -> bool:
    """Check if a row is a category header or column header, not data."""
    if not row or not row[0].strip():
        return True
    first = row[0].strip()
    if first == "Company Name":
        return True
    if file_type == "competitor":
        return any(first.startswith(p) for p in COMPETITOR_CATEGORY_PREFIXES)
    return first in CUSTOMER_CATEGORY_KEYWORDS


def parse_competitor_row(row: list[str], region: str) -> dict | None:
    """Parse a single competitor CSV row."""
    if len(row) < 11:
        return None
    name = row[0].strip()
    if not name:
        return None
    website = row[10].strip() if len(row) > 10 else ""
    if website and not website.startswith("http"):
        website = f"https://{website}"
    return {
        "name": normalize_name(name),
        "original_name": name,
        "type": "competitor",
        "region": [region],
        "competitor_type": row[1].strip().lower().replace(" / ", "_").replace(" ", "_"),
        "hq": row[2].strip() or None,
        "founded": row[3].strip() or None,
        "core_product": row[4].strip() or None,
        "overlap": row[5].strip() or None,
        "differentiator": row[6].strip() or None,
        "pricing": row[7].strip() or None,
        "funding_scale": row[8].strip() or None,
        "threat_level": row[9].strip().upper() or "MEDIUM",
        "industry": _infer_competitor_industry(row[1].strip(), row[4].strip()),
        "priority": _parse_priority(row[9].strip()),
        "website": website,
        "contact_lookup": False,
    }


def _parse_priority(raw: str) -> str:
    """Parse priority, defaulting to MEDIUM."""
    upper = raw.upper()
    return upper if upper in ("HIGH", "MEDIUM", "LOW") else "MEDIUM"


def _infer_competitor_industry(comp_type: str, product: str) -> str:
    """Infer industry from competitor type and product."""
    product_lower = product.lower()
    if "sorting" in product_lower or "grading" in product_lower:
        return "food_processing_tech"
    if "yield" in product_lower or "sensor" in product_lower or "monitor" in product_lower:
        return "precision_ag"
    if "satellite" in product_lower or "drone" in product_lower or "aerial" in product_lower:
        return "remote_sensing"
    if "farm management" in product_lower or "record" in product_lower:
        return "farm_management"
    if "oem" in comp_type.lower() or "platform" in comp_type.lower():
        return "oem_platform"
    return "precision_ag"


def parse_customer_row(row: list[str], region: str) -> dict | None:
    """Parse a single customer CSV row."""
    if len(row) < 11:
        return None
    name = row[0].strip()
    if not name:
        return None
    website = row[10].strip() if len(row) > 10 else ""
    if website and website != "n/a" and not website.startswith("http"):
        website = f"https://{website}"
    if website == "n/a":
        website = ""
    # Parse decision maker titles
    titles_raw = row[6].strip() if len(row) > 6 else ""
    titles = [t.strip() for t in titles_raw.split(",") if t.strip()]
    return {
        "name": normalize_name(name),
        "original_name": name,
        "type": "customer",
        "region": [region],
        "industry": _map_customer_industry(row[1].strip()),
        "company_type": row[2].strip() or None,
        "hq": row[3].strip() or None,
        "scale": row[4].strip() or None,
        "crop_focus": row[5].strip() or None,
        "decision_maker_titles": titles,
        "why_icp": row[7].strip() or None,
        "recent_signals": row[8].strip() or None,
        "priority": _parse_priority(row[9].strip()),
        "website": website,
        "contact_lookup": True,
    }


def _map_customer_industry(industry_raw: str) -> str:
    """Map CSV industry label to target industry enum."""
    mapping = {
        "Direct Farm Operator": "direct_farm_operator",
        "Food Processor": "food_processor",
        "Farmland Investor": "farmland_investor",
        "Cooperative": "cooperative",
        "Agri Input Company": "agri_input",
        "Grain Trader": "grain_trader",
        "Sugar Processor": "sugar_processor",
        "Bank / Lender": "agri_finance",
        "Crop Insurance": "crop_insurance",
    }
    return mapping.get(industry_raw, industry_raw.lower().replace(" ", "_"))


def load_csv(path: Path, file_type: str, region: str) -> list[dict]:
    """Load a CSV and return parsed entries."""
    entries = []
    with open(path, encoding="utf-8") as f:
        reader = csv.reader(f, delimiter=";")
        for row in reader:
            if is_header_row(row, file_type):
                continue
            parser = parse_competitor_row if file_type == "competitor" else parse_customer_row
            entry = parser(row, region)
            if entry:
                entries.append(entry)
    return entries


def load_existing_targets() -> dict[str, dict]:
    """Load current targets.yaml and index by dedup key."""
    existing = {}
    if not EXISTING_TARGETS.exists():
        return existing
    with open(EXISTING_TARGETS) as f:
        data = yaml.safe_load(f)
    for t in data.get("targets", []):
        canonical = resolve_alias(t["name"])
        key = dedup_key(canonical)
        existing[key] = t
    return existing


def resolve_alias(name: str) -> str:
    """Resolve name to canonical form via aliases."""
    lower = name.lower().strip()
    return NAME_ALIASES.get(lower, lower)


def merge_entries(all_entries: list[dict]) -> list[dict]:
    """Deduplicate entries, merging EU/US duplicates."""
    seen: dict[str, dict] = {}
    for entry in all_entries:
        canonical = resolve_alias(entry["name"])
        key = dedup_key(canonical)
        # Update name to canonical form if alias matched
        alias_name = NAME_ALIASES.get(entry["name"].lower().strip())
        if alias_name:
            entry["name"] = alias_name.title() if alias_name.islower() else alias_name
        if key in seen:
            existing = seen[key]
            # Merge regions
            for r in entry["region"]:
                if r not in existing["region"]:
                    existing["region"].append(r)
            # Keep higher priority
            priority_order = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
            existing_prio = priority_order.get(existing["priority"], 0)
            if priority_order.get(entry["priority"], 0) > existing_prio:
                existing["priority"] = entry["priority"]
            # Keep higher threat level for competitors
            if entry["type"] == "competitor" and existing["type"] == "competitor":
                if priority_order.get(entry.get("threat_level", ""), 0) > priority_order.get(
                    existing.get("threat_level", ""), 0
                ):
                    existing["threat_level"] = entry["threat_level"]
        else:
            seen[key] = entry
    return list(seen.values())


def enrich_with_existing(merged: list[dict], existing: dict[str, dict]) -> list[dict]:
    """Carry over verified scrape_urls, rss_feeds, serp_queries from current targets."""
    for entry in merged:
        canonical = resolve_alias(entry["name"])
        key = dedup_key(canonical)
        if key in existing:
            old = existing[key]
            entry["scrape_urls"] = old.get("scrape_urls", [])
            entry["rss_feeds"] = old.get("rss_feeds", [])
            entry["serp_queries"] = old.get("serp_queries", [])
            entry["monitoring"] = old.get("monitoring", "pending_discovery")
            if old.get("ticker"):
                entry["ticker"] = old["ticker"]
    return merged


MANUAL_ENTRIES = [
    {
        "name": "American Farm Bureau Federation",
        "type": "customer",
        "region": ["US"],
        "industry": "crop_insurance",
        "hq": "Illinois",
        "priority": "HIGH",
        "website": "https://www.fb.org",
        "scrape_urls": ["https://www.fb.org/news-release"],
        "rss_feeds": [],
        "serp_queries": ["Farm Bureau precision agriculture data"],
        "monitoring": "direct_scrape",
        "contact_lookup": True,
        "decision_maker_titles": ["Underwriting Manager", "Agricultural Risk Analyst"],
        "crop_focus": "All crops",
        "why_icp": "Largest US farm insurer. Needs farm performance data to price policies.",
    },
    {
        "name": "ProAg (Tokio Marine)",
        "type": "customer",
        "region": ["US"],
        "industry": "crop_insurance",
        "hq": "Texas",
        "priority": "MEDIUM",
        "website": "https://www.proag.com",
        "scrape_urls": [],
        "rss_feeds": [],
        "serp_queries": ["ProAg Tokio Marine farm data insurance"],
        "monitoring": "serp_only",
        "contact_lookup": True,
        "decision_maker_titles": ["Agronomy Risk Manager", "Underwriter", "Digital Risk Director"],
        "crop_focus": "All row crops",
        "why_icp": "Large crop insurance portfolio. Actively seeking farm performance data.",
    },
]

# Alpha competitor data with verified URLs and RSS feeds
ALPHA_VERIFIED = {
    dedup_key(resolve_alias("Corteva Agriscience")): {
        "scrape_urls": [
            "https://investors.corteva.com/news-events/news-releases",
            "https://www.corteva.com/us/news.html",
        ],
        "serp_queries": ["Corteva Agriscience precision agriculture news 2026"],
    },
    dedup_key(resolve_alias("Trimble Agriculture")): {
        "scrape_urls": ["https://news.trimble.com/news-releases?l=100"],
        "rss_feeds": ["https://news.trimble.com/index.php?s=20324&rsspage=20295"],
        "serp_queries": ["Trimble PTx agriculture technology news 2026"],
    },
    dedup_key(resolve_alias("John Deere")): {
        "scrape_urls": ["https://www.deere.com/en/our-company/news-and-announcements/"],
        "rss_feeds": ["https://investor.deere.com/rss/pressrelease.aspx"],
        "serp_queries": ["John Deere precision agriculture technology news 2026"],
    },
}


def format_target_for_yaml(entry: dict) -> dict:
    """Format a merged entry into final YAML structure."""
    target = {
        "name": entry["name"],
        "type": entry["type"],
        "region": sorted(entry["region"]),
        "industry": entry.get("industry", "other"),
        "priority": entry.get("priority", "MEDIUM"),
        "monitoring": entry.get("monitoring", "pending_discovery"),
        "website": entry.get("website", ""),
        "contact_lookup": entry.get("contact_lookup", entry["type"] == "customer"),
        "scrape_urls": entry.get("scrape_urls", []),
        "rss_feeds": entry.get("rss_feeds", []),
        "serp_queries": entry.get("serp_queries", []),
    }
    # Competitor-specific fields
    if entry["type"] == "competitor":
        target["competitor_type"] = entry.get("competitor_type", "direct")
        target["threat_level"] = entry.get("threat_level", "MEDIUM")
        if entry.get("overlap"):
            target["overlap"] = entry["overlap"]
        if entry.get("core_product"):
            target["core_product"] = entry["core_product"]
    # Customer-specific fields
    if entry["type"] == "customer":
        if entry.get("decision_maker_titles"):
            target["decision_maker_titles"] = entry["decision_maker_titles"]
        if entry.get("crop_focus"):
            target["crop_focus"] = entry["crop_focus"]
        if entry.get("why_icp"):
            target["why_icp"] = entry["why_icp"]
    # Common optional fields
    if entry.get("hq"):
        target["hq"] = entry["hq"]
    if entry.get("ticker"):
        target["ticker"] = entry["ticker"]
    return target


def apply_alpha_verified(targets: list[dict]) -> list[dict]:
    """Apply verified URLs/RSS from greenscanalpha competitor research."""
    for target in targets:
        canonical = resolve_alias(target["name"])
        key = dedup_key(canonical)
        if key in ALPHA_VERIFIED:
            alpha = ALPHA_VERIFIED[key]
            if not target.get("scrape_urls"):
                target["scrape_urls"] = alpha.get("scrape_urls", [])
            if not target.get("rss_feeds"):
                target["rss_feeds"] = alpha.get("rss_feeds", [])
            if not target.get("serp_queries"):
                target["serp_queries"] = alpha.get("serp_queries", [])
            if target["scrape_urls"]:
                target["monitoring"] = "direct_scrape"
    return targets


def main():
    print("Loading CSVs...")
    eu_comp = load_csv(CSV_DIR / "EU Competitors-Table 1.csv", "competitor", "EU")
    us_comp = load_csv(CSV_DIR / "US Competitors-Table 1.csv", "competitor", "US")
    eu_cust = load_csv(CSV_DIR / "EU Potential Customers-Table 1.csv", "customer", "EU")
    us_cust = load_csv(CSV_DIR / "US Potential Customers-Table 1.csv", "customer", "US")

    print(f"  EU competitors: {len(eu_comp)}")
    print(f"  US competitors: {len(us_comp)}")
    print(f"  EU customers:   {len(eu_cust)}")
    print(f"  US customers:   {len(us_cust)}")

    all_entries = eu_comp + us_comp + eu_cust + us_cust + MANUAL_ENTRIES
    print(f"\nTotal raw entries: {len(all_entries)}")

    merged = merge_entries(all_entries)
    print(f"After dedup: {len(merged)}")

    existing = load_existing_targets()
    print(f"Existing targets with verified URLs: {len(existing)}")
    merged = enrich_with_existing(merged, existing)

    targets = [format_target_for_yaml(e) for e in merged]
    targets = apply_alpha_verified(targets)

    # Sort: customers first (HIGH then MEDIUM), then competitors
    priority_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    targets.sort(
        key=lambda t: (
            0 if t["type"] == "customer" else 1,
            priority_order.get(t["priority"], 2),
            t["name"],
        )
    )

    # Stats
    customers = [t for t in targets if t["type"] == "customer"]
    competitors = [t for t in targets if t["type"] == "competitor"]
    with_urls = [t for t in targets if t["scrape_urls"]]
    with_rss = [t for t in targets if t["rss_feeds"]]
    pending = [t for t in targets if t["monitoring"] == "pending_discovery"]

    print(f"\n=== Final targets: {len(targets)} ===")
    high_cust = sum(1 for c in customers if c["priority"] == "HIGH")
    high_comp = sum(1 for c in competitors if c["priority"] == "HIGH")
    print(f"  Customers:   {len(customers)} ({high_cust} HIGH)")
    print(f"  Competitors: {len(competitors)} ({high_comp} HIGH)")
    print(f"  With scrape URLs: {len(with_urls)}")
    print(f"  With RSS feeds:   {len(with_rss)}")
    print(f"  Pending discovery: {len(pending)}")

    # Write YAML
    output = {"targets": targets}

    class YamlDumper(yaml.SafeDumper):
        pass

    def str_representer(dumper, data):
        if "\n" in data:
            return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
        return dumper.represent_scalar("tag:yaml.org,2002:str", data)

    YamlDumper.add_representer(str, str_representer)

    with open(OUTPUT_TARGETS, "w") as f:
        f.write("# GreenScan — Target Companies & Competitors\n")
        f.write("# Generated from founder's March 2026 CSV export + existing verified URLs.\n")
        n_cust, n_comp = len(customers), len(competitors)
        f.write(f"# Total: {len(targets)} ({n_cust} customers + {n_comp} competitors)\n")
        f.write(f"# Pending URL discovery: {len(pending)}\n\n")
        yaml.dump(
            output,
            f,
            Dumper=YamlDumper,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
            width=120,
        )

    print(f"\nWritten to {OUTPUT_TARGETS}")


if __name__ == "__main__":
    main()
