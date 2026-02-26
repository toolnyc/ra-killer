from __future__ import annotations

import json
import re
from datetime import date, datetime, time
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from src.log import get_logger
from src.models import ScrapedEvent, Source
from src.scrapers.base import BaseScraper

logger = get_logger("lightandsound")

BASE_URL = "https://lightandsound.design"


class LightAndSoundScraper(BaseScraper):
    name = "lightandsound"

    async def scrape(self) -> list[ScrapedEvent]:
        # Phase 1: Get event listing page
        resp = await self.fetch(BASE_URL)
        soup = BeautifulSoup(resp.text, "lxml")
        stubs = self._parse_listing(soup)

        # Phase 2: Fetch detail pages for ticket URLs that have Event JSON-LD
        events = []
        for stub in stubs:
            enriched = await self._enrich_event(stub)
            events.append(enriched)

        return events

    def _parse_listing(self, soup: BeautifulSoup) -> list[ScrapedEvent]:
        """Parse the main listing page for event stubs.

        Each event is an <a> tag with an external href and a <span class="date">
        containing the date in MM.DD.YYYY format, with the title as remaining text.
        """
        events = []
        for link in soup.select("a[href]"):
            # Only consider external event links
            href = link.get("href", "")
            if not href.startswith("http"):
                continue
            # Skip non-event links (social media, navigation, etc.)
            if "eventcreate.com/e/" not in href and "dice.fm" not in href:
                continue

            # Extract date from <span class="date">
            date_el = link.select_one(".date")
            if not date_el:
                continue
            date_text = date_el.get_text(strip=True)
            event_date = self._parse_date_text(date_text)
            if not event_date:
                continue

            # Title is the link text minus the date span text
            full_text = link.get_text(strip=True)
            title = full_text.replace(date_text, "").strip()
            if not title:
                continue

            # Use the last path segment as a stable ID
            event_id = href.rstrip("/").split("/")[-1]

            events.append(
                ScrapedEvent(
                    source=Source.LIGHT_AND_SOUND,
                    source_id=event_id,
                    title=title,
                    event_date=event_date,
                    source_url=href,
                )
            )

        return events

    async def _enrich_event(self, stub: ScrapedEvent) -> ScrapedEvent:
        """Try to enrich event with JSON-LD data from the detail/ticket page."""
        if not stub.source_url:
            return stub

        try:
            resp = await self.fetch(stub.source_url)
            soup = BeautifulSoup(resp.text, "lxml")

            # Look for JSON-LD (Event schema)
            for script in soup.select('script[type="application/ld+json"]'):
                try:
                    ld = json.loads(script.string)
                except (json.JSONDecodeError, TypeError):
                    continue

                if isinstance(ld, list):
                    for item in ld:
                        if item.get("@type") == "Event":
                            ld = item
                            break
                    else:
                        continue

                if ld.get("@type") != "Event":
                    continue

                # Enrich from JSON-LD
                start = ld.get("startDate")
                if start:
                    try:
                        dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
                        stub.start_time = dt.time()
                    except (ValueError, TypeError):
                        pass

                end = ld.get("endDate")
                if end:
                    try:
                        dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
                        stub.end_time = dt.time()
                    except (ValueError, TypeError):
                        pass

                location = ld.get("location", {})
                if isinstance(location, dict):
                    stub.venue_name = location.get("name") or stub.venue_name
                    addr = location.get("address", {})
                    if isinstance(addr, dict):
                        stub.venue_address = addr.get("streetAddress")
                    elif isinstance(addr, str):
                        stub.venue_address = addr

                stub.description = ld.get("description") or stub.description
                stub.image_url = ld.get("image") or stub.image_url
                if isinstance(stub.image_url, list):
                    stub.image_url = stub.image_url[0] if stub.image_url else None

                # Artists from performers
                performers = ld.get("performer") or ld.get("performers") or []
                if isinstance(performers, dict):
                    performers = [performers]
                for p in performers:
                    if isinstance(p, dict) and p.get("name"):
                        stub.artists.append(p["name"])

                # Price from offers
                offers = ld.get("offers", {})
                if isinstance(offers, list):
                    offers = offers[0] if offers else {}
                if isinstance(offers, dict):
                    price = offers.get("price")
                    if price:
                        try:
                            cents = int(float(price) * 100)
                            stub.price_min_cents = cents
                            stub.cost_display = f"${float(price):.0f}"
                        except (ValueError, TypeError):
                            stub.cost_display = str(price)

                break  # Found event JSON-LD, done

        except Exception:
            logger.warning("enrich_failed", source_id=stub.source_id, url=stub.source_url)

        return stub

    @staticmethod
    def _parse_date_text(text: str) -> date | None:
        """Try to parse various date formats."""
        if not text:
            return None
        # Try ISO format first
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            pass
        # Try common formats (including MM.DD.YYYY used by L&S)
        for fmt in (
            "%m.%d.%Y",
            "%B %d, %Y",
            "%b %d, %Y",
            "%m/%d/%Y",
            "%m-%d-%Y",
            "%B %d",
        ):
            try:
                dt = datetime.strptime(text.strip(), fmt)
                if dt.year == 1900:  # No year specified
                    dt = dt.replace(year=date.today().year)
                return dt.date()
            except ValueError:
                continue
        return None
