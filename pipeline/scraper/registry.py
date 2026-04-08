"""Load and validate target companies from YAML."""

import logging
from enum import StrEnum
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

TARGETS_PATH = Path(__file__).parent.parent.parent / "targets.yaml"


class TargetType(StrEnum):
    CUSTOMER = "customer"
    COMPETITOR = "competitor"


class Priority(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class MonitoringType(StrEnum):
    DIRECT_SCRAPE = "direct_scrape"
    RSS = "rss"
    DIRECT_SCRAPE_AND_RSS = "direct_scrape_and_rss"
    SERP_ONLY = "serp_only"
    SEC_IR = "sec_ir"
    PENDING_DISCOVERY = "pending_discovery"


class Target(BaseModel):
    name: str
    type: TargetType
    region: list[str] = Field(default_factory=list)
    industry: str
    priority: Priority
    monitoring: MonitoringType
    website: str
    contact_lookup: bool = False
    scrape_urls: list[str] = Field(default_factory=list)
    rss_feeds: list[str] = Field(default_factory=list)
    serp_queries: list[str] = Field(default_factory=list)
    ticker: str | None = None
    # Competitor-specific
    competitor_type: str | None = None
    threat_level: str | None = None
    overlap: str | None = None
    core_product: str | None = None
    # Customer-specific
    decision_maker_titles: list[str] = Field(default_factory=list)
    crop_focus: str | None = None
    why_icp: str | None = None
    # Common optional
    hq: str | None = None


def load_targets(path: Path = TARGETS_PATH) -> list[Target]:
    """Load target companies from YAML file."""
    with open(path) as f:
        data = yaml.safe_load(f)

    targets = [Target.model_validate(t) for t in data["targets"]]
    customers = sum(1 for t in targets if t.type == TargetType.CUSTOMER)
    competitors = len(targets) - customers
    high = sum(1 for t in targets if t.priority == Priority.HIGH)
    logger.info(
        f"Loaded {len(targets)} targets "
        f"({customers} customers, {competitors} competitors, {high} HIGH)"
    )
    return targets


def get_scrapable_targets(targets: list[Target]) -> list[Target]:
    """Return only targets that have URLs to scrape."""
    return [t for t in targets if t.scrape_urls]


def get_rss_targets(targets: list[Target]) -> list[Target]:
    """Return only targets that have RSS feeds."""
    return [t for t in targets if t.rss_feeds]


def get_customer_targets(targets: list[Target]) -> list[Target]:
    """Return only customer targets."""
    return [t for t in targets if t.type == TargetType.CUSTOMER]


def get_competitor_targets(targets: list[Target]) -> list[Target]:
    """Return only competitor targets."""
    return [t for t in targets if t.type == TargetType.COMPETITOR]
