"""Load and validate target companies from YAML."""

import logging
from enum import StrEnum
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

TARGETS_PATH = Path(__file__).parent.parent.parent / "targets.yaml"


class Priority(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"


class MonitoringType(StrEnum):
    DIRECT_SCRAPE = "direct_scrape"
    SERP_ONLY = "serp_only"
    SEC_IR = "sec_ir"


class Target(BaseModel):
    name: str
    industry: str
    priority: Priority
    monitoring: MonitoringType
    website: str
    scrape_urls: list[str] = Field(default_factory=list)
    rss_feeds: list[str] = Field(default_factory=list)
    serp_queries: list[str] = Field(default_factory=list)
    ticker: str | None = None


def load_targets(path: Path = TARGETS_PATH) -> list[Target]:
    """Load target companies from YAML file."""
    with open(path) as f:
        data = yaml.safe_load(f)

    targets = [Target.model_validate(t) for t in data["targets"]]
    high = sum(1 for t in targets if t.priority == Priority.HIGH)
    logger.info(f"Loaded {len(targets)} targets ({high} HIGH)")
    return targets


def get_scrapable_targets(targets: list[Target]) -> list[Target]:
    """Return only targets that have URLs to scrape."""
    return [t for t in targets if t.scrape_urls]
