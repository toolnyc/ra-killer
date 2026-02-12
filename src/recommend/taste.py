from __future__ import annotations

from src import db
from src.models import TasteEntry
from src.normalize import normalize, normalize_artist, normalize_venue


class TasteProfile:
    """Load and query taste preferences from the DB."""

    def __init__(self, entries: list[TasteEntry] | None = None) -> None:
        self._entries = entries if entries is not None else db.get_taste_profile()
        self._by_category: dict[str, dict[str, float]] = {}
        for e in self._entries:
            key = self._normalize_entry(e.category, e.name)
            self._by_category.setdefault(e.category, {})[key] = e.weight

    @staticmethod
    def _normalize_entry(category: str, name: str) -> str:
        if category == "artist":
            return normalize_artist(name)
        if category == "venue":
            return normalize_venue(name)
        return normalize(name)

    def artist_weight(self, name: str) -> float:
        return self._by_category.get("artist", {}).get(normalize_artist(name), 0.0)

    def venue_weight(self, name: str) -> float:
        return self._by_category.get("venue", {}).get(normalize_venue(name), 0.0)

    def known_artists(self) -> dict[str, float]:
        return self._by_category.get("artist", {})

    def known_venues(self) -> dict[str, float]:
        return self._by_category.get("venue", {})

    def to_prompt_text(self) -> str:
        """Render taste profile as text for Claude prompt."""
        lines = []
        for category in ("artist", "venue"):
            items = self._by_category.get(category, {})
            if not items:
                continue
            lines.append(f"\n## {category.title()}s")
            for name, weight in sorted(items.items(), key=lambda x: -x[1]):
                emoji = "+" if weight > 0 else "-"
                lines.append(f"  {emoji} {name} (weight: {weight:.1f})")
        return "\n".join(lines)
