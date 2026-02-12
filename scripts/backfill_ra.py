#!/usr/bin/env python3
"""Backfill historical RA events for training.

Wipes raw_events and events tables, then scrapes RA from 60 days ago
plus all other sources (upcoming only), deduplicates everything together,
and stores canonical events.
"""

import asyncio
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import db
from src.scrapers.ra import RAScraper
from src.scrapers.runner import deduplicate_and_store, run_all_scrapers


async def main():
    # Step 1: Wipe existing data
    print("Clearing tables...")
    client = db.get_client()
    client.table("recommendations").delete().gte("created_at", "2000-01-01").execute()
    client.table("events").delete().gte("created_at", "2000-01-01").execute()
    client.table("raw_events").delete().gte("created_at", "2000-01-01").execute()
    print("Cleared.")

    # Step 2: Scrape RA with historical date range
    from_date = date.today() - timedelta(days=60)
    print(f"Scraping RA from {from_date}...")
    scraper = RAScraper()
    try:
        ra_historical = await scraper.scrape(from_date=from_date)
    finally:
        await scraper.close()
    print(f"Got {len(ra_historical)} RA events (historical + upcoming)")

    # Step 3: Scrape all other sources (upcoming only)
    print("Scraping all sources (upcoming)...")
    all_events = await run_all_scrapers()

    # Replace RA's upcoming-only results with our historical+upcoming set
    all_events["ra"] = ra_historical
    total = sum(len(v) for v in all_events.values())
    print(f"Total scraped: {total} events from {len(all_events)} sources")

    # Step 4: Deduplicate and store everything as canonical events
    print("Deduplicating and storing...")
    new_count = deduplicate_and_store(all_events)
    print(f"Done! {new_count} canonical events stored.")

    # Verify
    past = db.get_past_events(days_back=60)
    upcoming = db.get_upcoming_events()
    print(f"\nResult: {len(past)} past events, {len(upcoming)} upcoming events")


if __name__ == "__main__":
    asyncio.run(main())
