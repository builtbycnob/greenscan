"""Apply manual URL research results to targets.yaml.

One-time script based on web research from 2026-04-08.
"""

from collections import Counter

import yaml

with open("targets.yaml") as f:
    data = yaml.safe_load(f)

targets = data["targets"]

# === REMOVALS (defunct companies) ===
REMOVE_NAMES = {
    "Gro Intelligence",  # Shut down 2024, IP acquired by Almanac
    "Precisionhawk",  # Bankrupt Dec 2023
    "SST Software (Proagrica)",  # Absorbed into Proagrica 2018
}

# Remove AGCO duplicate (keep one)
seen_agco = False
remove_indices = []
for i, t in enumerate(targets):
    if t["name"] in REMOVE_NAMES:
        remove_indices.append(i)
        print(f"REMOVE: {t['name']} (defunct)")
    # Remove AGCO duplicate
    if "AGCO Fuse" in t["name"]:
        if seen_agco:
            remove_indices.append(i)
            print(f"REMOVE: {t['name']} (duplicate)")
        seen_agco = True

for i in sorted(remove_indices, reverse=True):
    targets.pop(i)

# === URL UPDATES ===
UPDATES = {
    "AGCO Fuse Technology": {
        "scrape_urls": ["https://news.agcocorp.com/fuse"],
        "monitoring": "direct_scrape",
    },
    "Ag Connections": {
        "website": "https://agconnections.com",
        "scrape_urls": [],
        "notes": "Acquired by Syngenta 2015, rebranded Syngenta Digital",
    },
    "AgJunction (Hexagon)": {
        "website": "https://agjunction.com",
        "scrape_urls": [],
        "notes": "Acquired by Kubota Dec 2021 (not Hexagon)",
    },
    "AgriSompo North America": {
        "scrape_urls": ["https://www.agrisompo.com/resources/company-and-industry-news/"],
        "monitoring": "direct_scrape",
    },
    "Ardo Group": {
        "scrape_urls": ["https://ardo.com/en/stories"],
        "monitoring": "direct_scrape",
    },
    "Aviko (Royal Cosun)": {
        "website": "https://corporate.aviko.com/en",
        "scrape_urls": [],
    },
    "BASF Agricultural Solutions": {
        "website": "https://agriculture.basf.com/global/en",
        "scrape_urls": ["https://agriculture.basf.com/global/en/media/press-releases"],
        "monitoring": "direct_scrape",
    },
    "BayWa AG (Agri Finance)": {
        "website": "https://www.baywa.com",
        "scrape_urls": ["https://www.baywa.com/en/pressinformation"],
        "monitoring": "direct_scrape",
    },
    "CNH (Case IH / New Holland AFS Connect)": {
        "scrape_urls": ["https://media.cnh.com/NORTH-AMERICA/case-ih"],
        "monitoring": "direct_scrape",
    },
    "Cargill": {
        "website": "https://www.cargill.com",
        "scrape_urls": ["https://www.cargill.com/news/press-releases"],
        "monitoring": "direct_scrape",
    },
    "Crop Risk Services (AIG)": {
        "website": "https://www.cropriskservices.com",
        "scrape_urls": [],
        "notes": "Now under Great American Insurance (AFG), not AIG",
    },
    "Cropwise (Syngenta)": {
        "scrape_urls": ["https://www.syngenta.com/media/media-releases"],
        "monitoring": "direct_scrape",
    },
    "Descartes Labs": {
        "website": "https://earthdaily.com",
        "scrape_urls": ["https://earthdaily.com/press/"],
        "monitoring": "direct_scrape",
        "name": "EarthDaily Analytics (ex-Descartes Labs)",
    },
    "Exfarm (Italy)": {
        "website": "https://xfarm.ag",
        "scrape_urls": [],
        "notes": "exfarm.it not found; xFarm Technologies is the active Italian platform",
    },
    "Gavilon (Marubeni)": {
        "website": "https://www.viterra.us",
        "scrape_urls": ["https://www.viterra.us/media/news"],
        "monitoring": "direct_scrape",
        "name": "Viterra US (ex-Gavilon)",
    },
    "Grant 4-D Farms": {
        "scrape_urls": [],
    },
    "Hancock Natural Resource Group": {
        "website": "https://hancocknaturalresourcegroup.com",
        "scrape_urls": ["https://hancocknaturalresourcegroup.com/newsroom/"],
        "monitoring": "direct_scrape",
    },
    "Hexagon Agriculture (Leica Geosystems)": {
        "scrape_urls": ["https://hexagonpositioning.com/about-us/press-releases"],
        "monitoring": "direct_scrape",
    },
    "Hummingbird Technologies": {
        "website": "https://agreena.com",
        "scrape_urls": ["https://agreena.com/news"],
        "monitoring": "direct_scrape",
        "name": "Agreena (ex-Hummingbird Technologies)",
    },
    "Lutosa (PinguinLutosa)": {
        "scrape_urls": ["https://www.lutosa.com/en/news/"],
        "monitoring": "direct_scrape",
    },
    "MC Elettronica": {
        "website": "https://www.mcelettronica.it/en/",
        "scrape_urls": ["https://www.mcelettronica.it/en/newsblog/"],
        "monitoring": "direct_scrape",
    },
    "Potandon Produce": {
        "scrape_urls": ["https://www.greengiantfreshpotatoes.com/blog/"],
        "monitoring": "direct_scrape",
    },
    "Proagrica (RELX)": {
        "website": "https://proagrica.com",
        "scrape_urls": [],
        "notes": "Acquired by TELUS Agriculture Feb 2024",
    },
    "Rabo AgriFinance (Rabobank US)": {
        "website": "https://www.raboag.com",
        "scrape_urls": ["https://www.raboag.com/news-press-108"],
        "monitoring": "direct_scrape",
    },
    "Rabobank (Netherlands)": {
        "website": "https://www.rabobank.com",
        "scrape_urls": ["https://www.rabobank.com/about-us/press/press-releases"],
        "monitoring": "direct_scrape",
    },
    "SAME Deutz-Fahr / SDF Group": {
        "scrape_urls": ["https://www.sdfgroup.com/en-us/news"],
        "monitoring": "direct_scrape",
    },
    "Sentera": {
        "scrape_urls": ["https://sentera.com/resources/news/"],
        "monitoring": "direct_scrape",
        "notes": "Acquired by John Deere May 2025",
    },
    "TOMRA Food": {
        "scrape_urls": ["https://www.tomra.com/food/media-center/news"],
        "monitoring": "direct_scrape",
    },
    "Toepfer International (ADM Europe)": {
        "website": "https://www.adm.com",
        "scrape_urls": ["https://www.adm.com/en-us/news/news-releases/"],
        "monitoring": "direct_scrape",
        "name": "ADM Europe (ex-Toepfer International)",
    },
    "UBS Farmland / Westchester Group": {
        "website": "https://www.ubs.com/global/en/assetmanagement/capabilities/food-agriculture.html",
        "scrape_urls": [],
        "notes": "No dedicated news page; entity is UBS Farmland Investors LLC",
    },
    "Unifarm / De Heus Group (NL)": {
        "website": "https://www.deheus.com",
        "scrape_urls": ["https://www.deheus.com/news"],
        "monitoring": "direct_scrape",
        "name": "De Heus Group (NL)",
        "notes": "unifarm.nl was wrong (Wageningen University)",
    },
    "Viterra (Glencore Agri) Europe": {
        "scrape_urls": ["https://www.viterra.com/Media/News"],
        "monitoring": "direct_scrape",
        "notes": "Merged with Bunge July 2025",
    },
    "Western Sugar Cooperative": {
        "scrape_urls": [],
    },
    "xarvio (BASF)": {
        "scrape_urls": ["https://www.xarvio.com/global/en/news.html"],
        "monitoring": "direct_scrape",
    },
    "Sackett Ranch Inc.": {
        "website": "https://www.sackettpotatoes.com",
        "scrape_urls": [],
    },
    "Climate FieldView (Bayer)": {
        "scrape_urls": [
            "https://climate.com/en-us/resources/blog.html",
            "https://climate.com/en-us/resources/press-releases.html",
        ],
        "monitoring": "direct_scrape",
    },
}

updated = 0
for t in targets:
    if t["name"] in UPDATES:
        u = UPDATES[t["name"]]
        if "name" in u:
            print(f"RENAME: {t['name']} -> {u['name']}")
            t["name"] = u["name"]
        if "website" in u:
            t["website"] = u["website"]
        if "scrape_urls" in u and u["scrape_urls"]:
            t["scrape_urls"] = u["scrape_urls"]
        if "monitoring" in u:
            t["monitoring"] = u["monitoring"]
        if "rss_feeds" in u:
            t["rss_feeds"] = u["rss_feeds"]
        updated += 1
        print(f"UPDATE: {t['name']} -> {u.get('monitoring', t['monitoring'])}")


# Write
class D(yaml.SafeDumper):
    pass


def sr(dumper, d):
    if "\n" in d:
        return dumper.represent_scalar("tag:yaml.org,2002:str", d, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", d)


D.add_representer(str, sr)

customers = [t for t in targets if t["type"] == "customer"]
competitors = [t for t in targets if t["type"] == "competitor"]

with open("targets.yaml", "w") as f:
    nc, nk = len(customers), len(competitors)
    f.write("# GreenScan — Target Companies & Competitors\n")
    f.write(f"# Total: {len(targets)} ({nc} customers + {nk} competitors)\n\n")
    yaml.dump(
        {"targets": targets},
        f,
        Dumper=D,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
        width=120,
    )

# Stats
mon = Counter(t["monitoring"] for t in targets)
serp = sum(1 for t in targets if t["monitoring"] == "serp_only")
print("\n=== Results ===")
print(f"Total targets: {len(targets)} ({len(customers)} cust + {len(competitors)} comp)")
print(f"Updated: {updated}")
print(f"Removed: {len(remove_indices)}")
print(f"Monitoring: {dict(mon)}")
print(f"Still serp-only: {serp}")
