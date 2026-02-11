from __future__ import annotations

import re
from datetime import date, time

from bs4 import BeautifulSoup

from src.models import ScrapedEvent, Source
from src.scrapers.base import BaseScraper

BASE_URL = "https://nyc-noise.com"


class NYCNoiseScraper(BaseScraper):
    name = "nycnoise"

    async def scrape(self) -> list[ScrapedEvent]:
        resp = await self.fetch(BASE_URL)
        soup = BeautifulSoup(resp.text, "lxml")
        return self._parse_page(soup)

    def _parse_page(self, soup: BeautifulSoup) -> list[ScrapedEvent]:
        events = []
        for item in soup.select("div.event[data-date]"):
            parsed = self._parse_item(item)
            if parsed:
                events.append(parsed)
        return events

    def _parse_item(self, item) -> ScrapedEvent | None:
        date_str = item.get("data-date", "")
        if not date_str:
            return None

        event_date = self._parse_date_code(date_str)
        if not event_date:
            return None

        # data-starttime for start time (e.g. "7pm-10pm", "8pm")
        start_time = None
        time_str = item.get("data-starttime", "")
        if time_str:
            start_time = self._parse_time_str(time_str)

        # data-title-and-artists contains event title/artist info
        title_artists = item.get("data-title-and-artists", "")
        title = title_artists
        artists = []

        # Try to split title from artists
        for sep in (" | ", " - ", " w/ ", " ft. ", " feat. "):
            if sep in title_artists:
                parts = title_artists.split(sep, 1)
                title = parts[0].strip()
                artist_str = parts[1].strip()
                artists = [a.strip() for a in artist_str.split(",") if a.strip()]
                break

        if not title:
            title = item.get_text(strip=True)[:200]
        if not title:
            return None

        # Extract venue from text content (appears after @ symbol)
        venue_name = self._extract_venue(item)

        # Extract cost from text content
        cost = self._extract_cost(item)

        # Source URL from first external link
        link = None
        link_el = item.select_one("a[href]")
        if link_el:
            href = link_el.get("href", "")
            if href.startswith("http"):
                link = href
            elif href.startswith("/"):
                link = f"{BASE_URL}{href}"

        # Generate a stable source_id
        source_id = f"{date_str}_{title[:50]}"

        return ScrapedEvent(
            source=Source.NYC_NOISE,
            source_id=source_id,
            title=title,
            event_date=event_date,
            start_time=start_time,
            venue_name=venue_name,
            artists=artists,
            cost_display=cost or None,
            source_url=link,
            extra={"venue_id": item.get("data-venue-id", "")} if item.get("data-venue-id") else {},
        )

    @staticmethod
    def _parse_date_code(s: str) -> date | None:
        """Parse MMDDYY date format (e.g. '021126' = Feb 11, 2026)."""
        s = s.strip()
        if len(s) == 6 and s.isdigit():
            try:
                month = int(s[0:2])
                day = int(s[2:4])
                year = 2000 + int(s[4:6])
                return date(year, month, day)
            except ValueError:
                return None
        # Fallback: try ISO
        try:
            return date.fromisoformat(s[:10])
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _extract_venue(item) -> str | None:
        """Extract venue name from text after @ symbol."""
        text = item.get_text(" ", strip=True)
        # Pattern: "... @ venue_name (age_restriction), neighborhood, borough"
        m = re.search(r"@\s*([^(,\n]+)", text)
        if m:
            venue = m.group(1).strip()
            if venue:
                return venue
        return None

    @staticmethod
    def _extract_cost(item) -> str | None:
        """Extract cost info from text content."""
        text = item.get_text(" ", strip=True)
        # Look for common cost patterns
        if "notaflof" in text.lower():
            return "NOTAFLOF"
        m = re.search(r"\$\$|\$\d+", text)
        if m:
            return m.group(0)
        if "free" in text.lower():
            return "Free"
        return None

    @staticmethod
    def _parse_time_str(s: str) -> time | None:
        """Parse time strings like '8pm', '10:30 PM', '22:00', '7pm-10pm'."""
        # Take only the start time if it's a range
        s = s.split("-")[0].split("–")[0].split("*")[0].strip().lower()
        if not s:
            return None

        try:
            return time.fromisoformat(s)
        except ValueError:
            pass

        m = re.match(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)", s)
        if m:
            hour = int(m.group(1))
            minute = int(m.group(2) or 0)
            if m.group(3) == "pm" and hour != 12:
                hour += 12
            elif m.group(3) == "am" and hour == 12:
                hour = 0
            try:
                return time(hour, minute)
            except ValueError:
                pass

        return None
