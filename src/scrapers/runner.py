from __future__ import annotations

import asyncio
from datetime import date

from thefuzz import fuzz

from src import db
from src.log import get_logger
from src.models import Event, ScrapedEvent
from src.normalize import normalize, normalize_artist_list, normalize_venue
from src.scrapers.basement import BasementScraper
from src.scrapers.dice import DICEScraper
from src.scrapers.lightandsound import LightAndSoundScraper
from src.scrapers.nycnoise import NYCNoiseScraper
from src.scrapers.partiful import PartifulScraper
from src.scrapers.ra import RAScraper

logger = get_logger("runner")

ALL_SCRAPERS = [
    RAScraper,
    DICEScraper,
    PartifulScraper,
    BasementScraper,
    LightAndSoundScraper,
    NYCNoiseScraper,
]


def artist_jaccard(a: list[str], b: list[str]) -> float:
    """Jaccard similarity of two artist lists (normalized).

    Uses normalize_artist_list which strips qualifiers like (Live), (DJ Set)
    and splits b2b entries into individual artists.
    """
    if not a or not b:
        return 0.0
    set_a = normalize_artist_list(a)
    set_b = normalize_artist_list(b)
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union) if union else 0.0


def is_fuzzy_match(a: ScrapedEvent, b: Event) -> bool:
    """Check if scraped event fuzzy-matches an existing canonical event.

    Two of three must pass:
    1. Title similarity > 85 (token_sort_ratio)
    2. Artist Jaccard > 0.5
    3. Venue similarity > 90
    """
    if a.event_date != b.event_date:
        return False

    checks = 0

    # Title
    title_score = fuzz.token_sort_ratio(normalize(a.title), normalize(b.title))
    if title_score > 85:
        checks += 1

    # Artists
    if artist_jaccard(a.artists, b.artists) > 0.5:
        checks += 1

    # Venue
    if a.venue_name and b.venue_name:
        venue_score = fuzz.token_sort_ratio(
            normalize_venue(a.venue_name), normalize_venue(b.venue_name)
        )
        if venue_score > 90:
            checks += 1

    return checks >= 2


def merge_into_canonical(scraped: ScrapedEvent, existing: Event | None) -> Event:
    """Merge a scraped event into a canonical event, preferring richer data."""
    if existing is None:
        return Event(
            title=scraped.title,
            event_date=scraped.event_date,
            start_time=scraped.start_time,
            end_time=scraped.end_time,
            venue_name=scraped.venue_name,
            venue_address=scraped.venue_address,
            artists=scraped.artists,
            cost_display=scraped.cost_display,
            price_min_cents=scraped.price_min_cents,
            price_max_cents=scraped.price_max_cents,
            source_urls=(
                {scraped.source.value: scraped.source_url}
                if scraped.source_url
                else {}
            ),
            sources=[scraped.source.value],
            attending_count=scraped.attending_count,
            description=scraped.description,
            image_url=scraped.image_url,
        )

    # Merge: prefer non-null, longer descriptions, more artists
    e = existing.model_copy()
    if scraped.start_time and not e.start_time:
        e.start_time = scraped.start_time
    if scraped.end_time and not e.end_time:
        e.end_time = scraped.end_time
    if scraped.venue_name and not e.venue_name:
        e.venue_name = scraped.venue_name
    if scraped.venue_address and not e.venue_address:
        e.venue_address = scraped.venue_address
    if len(scraped.artists) > len(e.artists):
        e.artists = scraped.artists
    if scraped.cost_display and not e.cost_display:
        e.cost_display = scraped.cost_display
    if scraped.price_min_cents and not e.price_min_cents:
        e.price_min_cents = scraped.price_min_cents
    if scraped.price_max_cents and not e.price_max_cents:
        e.price_max_cents = scraped.price_max_cents
    if scraped.source_url:
        e.source_urls[scraped.source.value] = scraped.source_url
    if scraped.source.value not in e.sources:
        e.sources.append(scraped.source.value)
    if scraped.attending_count and (
        not e.attending_count or scraped.attending_count > e.attending_count
    ):
        e.attending_count = scraped.attending_count
    if scraped.description and (
        not e.description or len(scraped.description) > len(e.description)
    ):
        e.description = scraped.description
    if scraped.image_url and not e.image_url:
        e.image_url = scraped.image_url

    return e


async def run_all_scrapers() -> dict[str, list[ScrapedEvent]]:
    """Run all scrapers concurrently. Returns {source_name: events}."""
    scrapers = [cls() for cls in ALL_SCRAPERS]
    results = await asyncio.gather(*(s.run() for s in scrapers), return_exceptions=True)

    all_events: dict[str, list[ScrapedEvent]] = {}
    for scraper_cls, result in zip(ALL_SCRAPERS, results):
        name = scraper_cls.name if hasattr(scraper_cls, "name") else scraper_cls.__name__
        if isinstance(result, Exception):
            logger.error("scraper_exception", source=name, error=str(result))
            db.log_scrape(name, "error", 0, 0, str(result))
            continue

        events, duration, error = result
        status = "success" if error is None else "error"
        db.log_scrape(name, status, len(events), duration, error)

        if events:
            all_events[name] = events

    return all_events


def deduplicate_and_store(all_events: dict[str, list[ScrapedEvent]]) -> int:
    """Deduplicate scraped events and store canonical events. Returns count stored."""
    # Step 1: Store all raw events
    for source_name, events in all_events.items():
        count = db.upsert_raw_events(events)
        logger.info("raw_events_stored", source=source_name, count=count)

    # Step 2: Group all scraped events by date
    by_date: dict[date, list[ScrapedEvent]] = {}
    for events in all_events.values():
        for e in events:
            by_date.setdefault(e.event_date, []).append(e)

    # Step 3: For each date, deduplicate against existing canonical + each other
    total_stored = 0
    for event_date, scraped_list in by_date.items():
        # Get existing canonical events for this date
        existing = db.get_canonical_events_by_date_venue(event_date, None)
        existing_map: dict[str, Event] = {}  # normalized key -> Event
        for e in existing:
            key = f"{normalize(e.title)}|{e.event_date}|{normalize_venue(e.venue_name or '')}"
            existing_map[key] = e

        for scraped in scraped_list:
            key = f"{normalize(scraped.title)}|{scraped.event_date}|{normalize_venue(scraped.venue_name or '')}"

            # Exact match
            if key in existing_map:
                merged = merge_into_canonical(scraped, existing_map[key])
                merged.id = existing_map[key].id
                db.upsert_canonical_event(merged)
                existing_map[key] = merged
                continue

            # Fuzzy match against existing
            matched = False
            for ex_key, ex_event in existing_map.items():
                if is_fuzzy_match(scraped, ex_event):
                    merged = merge_into_canonical(scraped, ex_event)
                    merged.id = ex_event.id
                    db.upsert_canonical_event(merged)
                    existing_map[ex_key] = merged
                    matched = True
                    break

            if not matched:
                # New event
                new_event = merge_into_canonical(scraped, None)
                event_id = db.upsert_canonical_event(new_event)
                new_event.id = event_id
                existing_map[key] = new_event
                total_stored += 1

    logger.info("dedup_complete", new_events=total_stored)
    return total_stored


async def run_scrape_pipeline() -> int:
    """Full pipeline: scrape all sources, deduplicate, store. Returns new event count."""
    all_events = await run_all_scrapers()
    total_scraped = sum(len(v) for v in all_events.values())
    logger.info("scrape_pipeline_scraped", total=total_scraped, sources=len(all_events))

    new_count = deduplicate_and_store(all_events)
    logger.info("scrape_pipeline_complete", new_events=new_count)
    return new_count
