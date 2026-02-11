from __future__ import annotations

from datetime import date, datetime, time

from src.models import ScrapedEvent, Source
from src.scrapers.base import BaseScraper

CATEGORIES = ["dj", "party", "gig"]
BASE_URL = "https://dice.fm/browse/new_york-5bbf4db0f06331478e9b2c59/music"


class DICEScraper(BaseScraper):
    name = "dice"

    async def scrape(self) -> list[ScrapedEvent]:
        events: list[ScrapedEvent] = []
        seen_ids: set[str] = set()
        for cat in CATEGORIES:
            url = f"{BASE_URL}/{cat}"
            resp = await self.fetch(url)
            page_events = self._parse_page(resp.text)
            for ev in page_events:
                if ev.source_id not in seen_ids:
                    seen_ids.add(ev.source_id)
                    events.append(ev)
        return events

    def _parse_page(self, html: str) -> list[ScrapedEvent]:
        import json
        import re

        match = re.search(
            r'<script\s+id="__NEXT_DATA__"\s+type="application/json">(.*?)</script>',
            html,
            re.DOTALL,
        )
        if not match:
            return []

        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError:
            return []

        events = []
        props = data.get("props", {}).get("pageProps", {})
        event_list = props.get("events") or []

        for ev in event_list:
            parsed = self._parse_event(ev)
            if parsed:
                events.append(parsed)

        return events

    def _parse_event(self, ev: dict) -> ScrapedEvent | None:
        # Parse date from dates.event_start_date (ISO) or date_unix
        dates_info = ev.get("dates") or {}
        start_str = dates_info.get("event_start_date")
        end_str = dates_info.get("event_end_date")

        event_date = None
        start_time = None
        end_time = None

        if start_str:
            try:
                dt = datetime.fromisoformat(start_str)
                event_date = dt.date()
                start_time = dt.time()
            except (ValueError, TypeError):
                pass

        if not event_date:
            date_unix = ev.get("date_unix")
            if date_unix:
                try:
                    dt = datetime.fromtimestamp(date_unix)
                    event_date = dt.date()
                    start_time = dt.time()
                except (ValueError, TypeError, OSError):
                    pass

        if not event_date:
            return None

        if end_str:
            try:
                end_time = datetime.fromisoformat(end_str).time()
            except (ValueError, TypeError):
                pass

        # Venue from venues list
        venue_name = None
        venue_address = None
        venues = ev.get("venues") or []
        if venues and isinstance(venues[0], dict):
            venue_name = venues[0].get("name")
            venue_address = venues[0].get("address")

        # Artists from summary_lineup.top_artists
        artists = []
        lineup = ev.get("summary_lineup") or {}
        for a in lineup.get("top_artists") or []:
            if isinstance(a, dict) and a.get("name"):
                artists.append(a["name"])

        # Price
        price_info = ev.get("price") or {}
        amount = price_info.get("amount")
        price_min_cents = None
        cost_display = None
        if amount is not None:
            price_min_cents = int(amount)
            if amount == 0:
                cost_display = "Free"
            else:
                cost_display = f"${amount / 100:.0f}"

        # URL from perm_name
        perm_name = ev.get("perm_name", "")
        source_url = f"https://dice.fm/event/{perm_name}" if perm_name else None

        # Image
        images = ev.get("images") or {}
        image_url = images.get("square") or images.get("landscape")

        # Description
        about = ev.get("about")
        description = None
        if isinstance(about, dict):
            description = about.get("description")
        elif isinstance(about, str):
            description = about

        return ScrapedEvent(
            source=Source.DICE,
            source_id=str(ev.get("id", "")),
            title=ev.get("name") or "",
            event_date=event_date,
            start_time=start_time,
            end_time=end_time,
            venue_name=venue_name,
            venue_address=venue_address,
            artists=artists,
            cost_display=cost_display,
            price_min_cents=price_min_cents,
            source_url=source_url,
            description=description,
            image_url=image_url,
        )
