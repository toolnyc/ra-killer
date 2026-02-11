from __future__ import annotations

import abc
import time as time_mod

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from src.log import get_logger
from src.models import ScrapedEvent

logger = get_logger("scraper")

BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


class BaseScraper(abc.ABC):
    """Abstract base scraper. Subclasses implement `scrape()`."""

    name: str = "base"

    def __init__(self) -> None:
        self.client = httpx.AsyncClient(
            timeout=30,
            headers={"User-Agent": BROWSER_UA},
            follow_redirects=True,
        )

    async def close(self) -> None:
        await self.client.aclose()

    @abc.abstractmethod
    async def scrape(self) -> list[ScrapedEvent]:
        """Fetch and parse events from this source."""
        ...

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=15))
    async def fetch(self, url: str, **kwargs) -> httpx.Response:
        resp = await self.client.get(url, **kwargs)
        resp.raise_for_status()
        return resp

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=15))
    async def post(self, url: str, **kwargs) -> httpx.Response:
        resp = await self.client.post(url, **kwargs)
        resp.raise_for_status()
        return resp

    async def run(self) -> tuple[list[ScrapedEvent], float, str | None]:
        """Run the scraper with timing and error handling."""
        start = time_mod.monotonic()
        error = None
        events = []
        try:
            events = await self.scrape()
            logger.info("scrape_complete", source=self.name, count=len(events))
        except Exception as e:
            error = str(e)
            logger.error("scrape_failed", source=self.name, error=error)
        finally:
            await self.close()
        duration = time_mod.monotonic() - start
        return events, duration, error
