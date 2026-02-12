#!/usr/bin/env python3
"""Seed the taste_profile table with initial preferences from CSVs."""

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import db
from src.models import TasteEntry

ROOT = Path(__file__).resolve().parent.parent


def _load_artists_csv() -> list[tuple[str, float]]:
    """Load artists from bandcamp_artists.csv where weight > 0."""
    path = ROOT / "bandcamp_artists.csv"
    artists = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row["artist"].strip()
            weight_str = row.get("weight", "").strip()
            if not name or not weight_str:
                continue
            try:
                weight = float(weight_str)
            except ValueError:
                continue
            if weight > 0:
                artists.append((name, weight))
    return artists


def _load_venues_csv() -> list[tuple[str, float]]:
    """Load venues from venues.csv where weight > 0."""
    path = ROOT / "venues.csv"
    venues = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row["venue"].strip()
            weight_str = row.get("weight", "").strip()
            if not name or not weight_str:
                continue
            try:
                weight = float(weight_str)
            except ValueError:
                continue
            if weight > 0:
                venues.append((name, weight))
    return venues


def main():
    entries = []

    # Load from CSVs
    artists = _load_artists_csv()
    venues = _load_venues_csv()
    print(f"Loaded {len(artists)} artists from CSV, {len(venues)} venues from CSV")

    for name, weight in artists:
        entries.append(TasteEntry(category="artist", name=name, weight=weight, source="manual"))
    for name, weight in venues:
        entries.append(TasteEntry(category="venue", name=name, weight=weight, source="manual"))

    for entry in entries:
        db.upsert_taste_entry(entry)
        print(f"  {entry.category}: {entry.name} ({entry.weight:+.1f})")

    print(f"\nSeeded {len(entries)} taste entries.")


if __name__ == "__main__":
    main()
