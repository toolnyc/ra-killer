from __future__ import annotations

from src import db
from src.models import TasteEntry


class TasteProfile:
    """Load and query taste preferences from the DB."""

    def __init__(self, entries: list[TasteEntry] | None = None) -> None:
        self._entries = entries if entries is not None else db.get_taste_profile()
        self._by_category: dict[str, dict[str, float]] = {}
        for e in self._entries:
            self._by_category.setdefault(e.category, {})[e.name.lower()] = e.weight

    def artist_weight(self, name: str) -> float:
        return self._by_category.get("artist", {}).get(name.lower(), 0.0)

    def venue_weight(self, name: str) -> float:
        return self._by_category.get("venue", {}).get(name.lower(), 0.0)

    def genre_weight(self, name: str) -> float:
        return self._by_category.get("genre", {}).get(name.lower(), 0.0)

    def promoter_weight(self, name: str) -> float:
        return self._by_category.get("promoter", {}).get(name.lower(), 0.0)

    def vibe_weight(self, name: str) -> float:
        return self._by_category.get("vibe", {}).get(name.lower(), 0.0)

    def known_artists(self) -> dict[str, float]:
        return self._by_category.get("artist", {})

    def known_venues(self) -> dict[str, float]:
        return self._by_category.get("venue", {})

    def to_prompt_text(self) -> str:
        """Render taste profile as text for Claude prompt."""
        lines = []
        for category in ("artist", "venue", "genre", "promoter", "vibe"):
            items = self._by_category.get(category, {})
            if not items:
                continue
            lines.append(f"\n## {category.title()}s")
            for name, weight in sorted(items.items(), key=lambda x: -x[1]):
                emoji = "+" if weight > 0 else "-"
                lines.append(f"  {emoji} {name} (weight: {weight:.1f})")
        return "\n".join(lines)
