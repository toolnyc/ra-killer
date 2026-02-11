from __future__ import annotations

from datetime import date, time

from src.models import ScrapedEvent, Source
from src.scrapers.base import BaseScraper

GRAPHQL_URL = "https://ra.co/graphql"
AREA_ID = 8  # New York

QUERY = """
query GET_DEFAULT_EVENTS_LISTING(
  $filters: FilterInputDtoInput
  $pageSize: Int
  $page: Int
) {
  eventListings(filters: $filters, pageSize: $pageSize, page: $page) {
    data {
      id
      event {
        id
        title
        date
        startTime
        endTime
        contentUrl
        images { filename }
        venue { id name address }
        artists { id name }
        attending
        cost
        pick { blurb }
      }
    }
    totalResults
  }
}
"""


class RAScraper(BaseScraper):
    name = "ra"

    async def scrape(self) -> list[ScrapedEvent]:
        events: list[ScrapedEvent] = []
        page = 1
        while True:
            variables = {
                "filters": {
                    "areas": {"eq": AREA_ID},
                    "listingDate": {"gte": date.today().isoformat()},
                },
                "pageSize": 100,
                "page": page,
            }
            resp = await self.post(
                GRAPHQL_URL,
                json={"query": QUERY, "variables": variables},
            )
            data = resp.json()
            listings = data.get("data", {}).get("eventListings", {})
            items = listings.get("data", [])
            if not items:
                break

            for item in items:
                ev = item.get("event", {})
                if not ev:
                    continue
                parsed = self._parse_event(ev)
                if parsed:
                    events.append(parsed)

            total = listings.get("totalResults", 0)
            if page * 100 >= total:
                break
            page += 1
            if page > 5:  # safety cap
                break

        return events

    def _parse_event(self, ev: dict) -> ScrapedEvent | None:
        try:
            event_date = date.fromisoformat(ev["date"][:10])
        except (ValueError, TypeError, KeyError):
            return None

        start_time = self._parse_time(ev.get("startTime"))
        end_time = self._parse_time(ev.get("endTime"))

        venue = ev.get("venue") or {}
        artists = [a["name"] for a in (ev.get("artists") or []) if a.get("name")]

        images = ev.get("images") or []
        image_url = None
        if images:
            filename = images[0].get("filename", "")
            if filename:
                image_url = f"https://ra.co/images/events/flyer/{filename}"

        content_url = ev.get("contentUrl", "")
        source_url = f"https://ra.co{content_url}" if content_url else None

        return ScrapedEvent(
            source=Source.RA,
            source_id=str(ev["id"]),
            title=ev.get("title", ""),
            event_date=event_date,
            start_time=start_time,
            end_time=end_time,
            venue_name=venue.get("name"),
            venue_address=venue.get("address"),
            artists=artists,
            cost_display=ev.get("cost"),
            source_url=source_url,
            attending_count=ev.get("attending"),
            description=(ev.get("pick") or {}).get("blurb"),
            image_url=image_url,
        )

    @staticmethod
    def _parse_time(val: str | None) -> time | None:
        if not val:
            return None
        try:
            return time.fromisoformat(val)
        except (ValueError, TypeError):
            return None
