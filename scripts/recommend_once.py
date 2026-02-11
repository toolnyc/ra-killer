#!/usr/bin/env python3
"""One-shot recommendation: score upcoming events and print results."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import db
from src.recommend.ranker import rank_events
from src.recommend.taste import TasteProfile


async def main():
    print("Loading upcoming events...")
    events = db.get_upcoming_events()
    print(f"Found {len(events)} upcoming events.")

    if not events:
        print("No events to score. Run scrape_once.py first.")
        return

    taste = TasteProfile()
    print(f"Taste profile:\n{taste.to_prompt_text()}\n")

    print("Ranking events...")
    recs = await rank_events(events, taste, top_n=15, use_claude=True)

    events_map = {e.id: e for e in events}

    print(f"\nTop {len(recs)} recommendations:\n")
    for i, rec in enumerate(recs, 1):
        event = events_map.get(rec.event_id)
        if not event:
            continue
        artists = ", ".join(event.artists) if event.artists else "TBA"
        print(
            f"{i:2d}. [{rec.score:.0f}] {event.title}\n"
            f"    {event.event_date} | {event.venue_name or 'TBA'} | {artists}\n"
            f"    {rec.reasoning}\n"
        )


if __name__ == "__main__":
    asyncio.run(main())
