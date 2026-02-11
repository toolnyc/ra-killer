#!/usr/bin/env python3
"""Seed the taste_profile table with initial preferences."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import db
from src.models import TasteEntry

# === CUSTOMIZE THESE ===

ARTISTS = [
    # (name, weight) - weight 2.0 = strong favorite, 1.0 = like, -1.0 = avoid
    ("Honey Dijon", 2.0),
    ("DJ Harvey", 2.0),
    ("Floating Points", 2.0),
    ("Four Tet", 1.5),
    ("Ben UFO", 1.5),
    ("Joy Orbison", 1.5),
    ("Bicep", 1.0),
    ("Peggy Gou", 1.0),
]

VENUES = [
    ("Nowadays", 2.0),
    ("Basement", 1.5),
    ("Knockdown Center", 1.5),
    ("Good Room", 1.0),
    ("Elsewhere", 1.0),
    ("Public Records", 1.0),
    ("Market Hotel", 0.5),
    ("Bossa Nova Civic Club", 0.5),
]

GENRES = [
    ("house", 2.0),
    ("techno", 1.5),
    ("disco", 1.5),
    ("ambient", 1.0),
    ("dnb", 0.5),
    ("breakbeat", 1.0),
]

VIBES = [
    ("underground", 1.5),
    ("warehouse", 1.5),
    ("outdoor", 1.0),
    ("late night", 1.0),
]


def main():
    entries = []
    for name, weight in ARTISTS:
        entries.append(TasteEntry(category="artist", name=name, weight=weight))
    for name, weight in VENUES:
        entries.append(TasteEntry(category="venue", name=name, weight=weight))
    for name, weight in GENRES:
        entries.append(TasteEntry(category="genre", name=name, weight=weight))
    for name, weight in VIBES:
        entries.append(TasteEntry(category="vibe", name=name, weight=weight))

    for entry in entries:
        db.upsert_taste_entry(entry)
        print(f"  {entry.category}: {entry.name} ({entry.weight:+.1f})")

    print(f"\nSeeded {len(entries)} taste entries.")


if __name__ == "__main__":
    main()
