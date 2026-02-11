from __future__ import annotations

from datetime import date, datetime, time

from src.models import ScrapedEvent, Source
from src.scrapers.base import BaseScraper

DISCOVER_URL = "https://partiful.com/discover/nyc"


class PartifulScraper(BaseScraper):
    name = "partiful"

    async def scrape(self) -> list[ScrapedEvent]:
        resp = await self.fetch(DISCOVER_URL)
        return self._parse_page(resp.text)

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

        props = data.get("props", {}).get("pageProps", {})

        # Collect events from all sections, deduplicating by id
        seen_ids: set[str] = set()
        events: list[ScrapedEvent] = []

        def add_event(ev_data: dict) -> None:
            eid = ev_data.get("id", "")
            if eid in seen_ids:
                return
            parsed = self._parse_event(ev_data)
            if parsed:
                seen_ids.add(eid)
                events.append(parsed)

        # trendingSection.items[].event
        trending = props.get("trendingSection") or {}
        for item in trending.get("items") or []:
            ev = item.get("event") or item
            add_event(ev)

        # sections[].items[].event
        for section in props.get("sections") or []:
            for item in section.get("items") or []:
                ev = item.get("event") or item
                add_event(ev)

        # feedItems[].event
        for item in props.get("feedItems") or []:
            ev = item.get("event") or item
            add_event(ev)

        return events

    def _parse_event(self, ev: dict) -> ScrapedEvent | None:
        start = ev.get("startDate")
        if not start:
            return None

        try:
            dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
            event_date = dt.date()
            start_time = dt.time()
        except (ValueError, TypeError):
            return None

        end_time = None
        end = ev.get("endDate")
        if end:
            try:
                end_time = datetime.fromisoformat(end.replace("Z", "+00:00")).time()
            except (ValueError, TypeError):
                pass

        # Location from locationInfo
        venue_name = None
        venue_address = None
        loc = ev.get("locationInfo") or {}
        if isinstance(loc, dict):
            maps_info = loc.get("mapsInfo") or {}
            addr_lines = (
                maps_info.get("addressLines")
                or loc.get("displayAddressLines")
                or []
            )
            if addr_lines:
                venue_address = ", ".join(addr_lines)
            venue_name = maps_info.get("approximateLocation")

        title = ev.get("title") or ev.get("name", "")
        description = ev.get("description") or ""
        event_id = ev.get("id") or ""
        source_url = f"https://partiful.com/e/{event_id}" if event_id else None

        # Image
        image = ev.get("image")
        image_url = None
        if isinstance(image, str):
            image_url = image
        elif isinstance(image, dict):
            image_url = image.get("url")

        # Guest count
        attending = (
            ev.get("goingGuestCount")
            or ev.get("approvedGuestCount")
            or ev.get("interestedGuestCount")
        )

        return ScrapedEvent(
            source=Source.PARTIFUL,
            source_id=str(event_id),
            title=title,
            event_date=event_date,
            start_time=start_time,
            end_time=end_time,
            venue_name=venue_name,
            venue_address=venue_address,
            artists=[],  # Partiful rarely has structured artist data
            cost_display=None,
            source_url=source_url,
            attending_count=attending,
            description=description,
            image_url=image_url,
        )
