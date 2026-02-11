from __future__ import annotations

from datetime import date, datetime, time

from src.models import ScrapedEvent, Source
from src.scrapers.base import BaseScraper

API_URL = "https://basement.mtebi.com/events/public?status=published&limit=100"


class BasementScraper(BaseScraper):
    name = "basement"

    async def scrape(self) -> list[ScrapedEvent]:
        resp = await self.fetch(API_URL)
        data = resp.json()
        events = []
        event_list = data if isinstance(data, list) else data.get("events", data.get("data", []))
        for ev in event_list:
            parsed = self._parse_event(ev)
            if parsed:
                events.append(parsed)
        return events

    def _parse_event(self, ev: dict) -> ScrapedEvent | None:
        start = ev.get("start_date") or ev.get("startDate") or ev.get("date")
        if not start:
            return None

        try:
            dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
            event_date = dt.date()
            start_time = dt.time()
        except (ValueError, TypeError):
            return None

        end_time = None
        end = ev.get("end_date") or ev.get("endDate")
        if end:
            try:
                end_time = datetime.fromisoformat(end.replace("Z", "+00:00")).time()
            except (ValueError, TypeError):
                pass

        # Lineup from basement_stage and studio_stage (comma-separated)
        artists = []
        for stage_key in ("basement_stage", "studio_stage", "lineup", "artists"):
            stage = ev.get(stage_key, "")
            if isinstance(stage, str) and stage:
                artists.extend(
                    a.strip() for a in stage.split(",") if a.strip()
                )
            elif isinstance(stage, list):
                for a in stage:
                    if isinstance(a, dict):
                        artists.append(a.get("name", ""))
                    elif isinstance(a, str):
                        artists.append(a)
        artists = list(dict.fromkeys(a for a in artists if a))  # dedup, preserve order

        # Price
        cost_display = ev.get("price") or ev.get("cost_display")
        price_min = ev.get("price_min") or ev.get("price_min_cents")
        price_max = ev.get("price_max") or ev.get("price_max_cents")

        event_id = str(ev.get("id", ""))
        source_url = ev.get("url") or ev.get("ticket_link") or ev.get("ticket_url")
        if not source_url and event_id:
            source_url = f"https://basementny.net/events/{event_id}"

        return ScrapedEvent(
            source=Source.BASEMENT,
            source_id=event_id,
            title=ev.get("title") or ev.get("name", ""),
            event_date=event_date,
            start_time=start_time,
            end_time=end_time,
            venue_name=ev.get("venue_name") or ev.get("venue", "Basement NY"),
            venue_address=ev.get("venue_address"),
            artists=artists,
            cost_display=str(cost_display) if cost_display else None,
            price_min_cents=price_min,
            price_max_cents=price_max,
            source_url=source_url,
            attending_count=ev.get("attending_count") or ev.get("rsvp_count"),
            description=ev.get("description"),
            image_url=ev.get("image") or ev.get("cover_image") or ev.get("imageUrl"),
        )
