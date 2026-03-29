"""Shared data models for scraper output."""

import hashlib
from datetime import UTC, datetime

from pydantic import BaseModel, Field, computed_field


class RawSignal(BaseModel):
    """A raw signal scraped from a target company's website or RSS feed."""

    url: str
    title: str = "Untitled"
    content: str
    source: str  # target company name
    scraped_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @computed_field
    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.content.encode()).hexdigest()
