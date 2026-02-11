from __future__ import annotations

from datetime import date, datetime, time
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Source(str, Enum):
    RA = "ra"
    DICE = "dice"
    PARTIFUL = "partiful"
    BASEMENT = "basement"
    LIGHT_AND_SOUND = "lightandsound"
    NYC_NOISE = "nycnoise"


class ScrapedEvent(BaseModel):
    """Raw event as returned by a scraper, before dedup."""

    source: Source
    source_id: str
    title: str
    event_date: date
    start_time: time | None = None
    end_time: time | None = None
    venue_name: str | None = None
    venue_address: str | None = None
    artists: list[str] = Field(default_factory=list)
    cost_display: str | None = None
    price_min_cents: int | None = None
    price_max_cents: int | None = None
    source_url: str | None = None
    attending_count: int | None = None
    description: str | None = None
    image_url: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class Event(BaseModel):
    """Canonical deduplicated event stored in DB."""

    id: str | None = None
    title: str
    event_date: date
    start_time: time | None = None
    end_time: time | None = None
    venue_name: str | None = None
    venue_address: str | None = None
    artists: list[str] = Field(default_factory=list)
    cost_display: str | None = None
    price_min_cents: int | None = None
    price_max_cents: int | None = None
    source_urls: dict[str, str] = Field(default_factory=dict)
    sources: list[str] = Field(default_factory=list)
    attending_count: int | None = None
    description: str | None = None
    image_url: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class Recommendation(BaseModel):
    id: str | None = None
    event_id: str
    score: float
    reasoning: str = ""
    telegram_message_id: int | None = None
    feedback: str | None = None  # "approve" | "reject" | None
    created_at: datetime | None = None


class TasteEntry(BaseModel):
    id: str | None = None
    category: str  # artist, venue, promoter, genre, vibe
    name: str
    weight: float = 1.0
    source: str = "manual"  # manual | learned
