import json

from src.scrapers.partiful import PartifulScraper


def test_parse_event_basic():
    scraper = PartifulScraper()
    ev = {
        "id": "abc123",
        "title": "Rooftop Party",
        "startDate": "2026-03-15T22:00:00-04:00",
        "endDate": "2026-03-16T04:00:00-04:00",
        "locationInfo": {
            "mapsInfo": {
                "approximateLocation": "Elsewhere",
                "addressLines": ["599 Johnson Ave", "Brooklyn, NY"],
            }
        },
        "goingGuestCount": 150,
        "description": "A vibe.",
        "image": "https://partiful.com/img/abc.jpg",
    }
    result = scraper._parse_event(ev)
    assert result is not None
    assert result.source_id == "abc123"
    assert result.title == "Rooftop Party"
    assert result.venue_name == "Elsewhere"
    assert result.venue_address == "599 Johnson Ave, Brooklyn, NY"
    assert result.attending_count == 150
    assert result.source_url == "https://partiful.com/e/abc123"
    assert result.image_url == "https://partiful.com/img/abc.jpg"


def test_parse_event_no_start_date():
    scraper = PartifulScraper()
    result = scraper._parse_event({"id": "x", "title": "No Date"})
    assert result is None


def test_parse_event_image_as_dict():
    scraper = PartifulScraper()
    ev = {
        "id": "img1",
        "title": "Test",
        "startDate": "2026-04-01T20:00:00Z",
        "image": {"url": "https://partiful.com/img/dict.jpg"},
    }
    result = scraper._parse_event(ev)
    assert result is not None
    assert result.image_url == "https://partiful.com/img/dict.jpg"


def test_parse_page_trending_and_sections():
    scraper = PartifulScraper()
    data = {
        "props": {
            "pageProps": {
                "trendingSection": {
                    "items": [
                        {
                            "event": {
                                "id": "t1",
                                "title": "Trending Event",
                                "startDate": "2026-03-20T21:00:00Z",
                            }
                        }
                    ]
                },
                "sections": [
                    {
                        "items": [
                            {
                                "event": {
                                    "id": "s1",
                                    "title": "Section Event",
                                    "startDate": "2026-03-21T22:00:00Z",
                                }
                            }
                        ]
                    }
                ],
                "feedItems": [
                    {
                        "event": {
                            "id": "f1",
                            "title": "Feed Event",
                            "startDate": "2026-03-22T23:00:00Z",
                        }
                    }
                ],
            }
        }
    }
    html = f'<html><body><script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script></body></html>'
    events = scraper._parse_page(html)
    assert len(events) == 3
    titles = {e.title for e in events}
    assert titles == {"Trending Event", "Section Event", "Feed Event"}


def test_parse_page_deduplicates():
    scraper = PartifulScraper()
    data = {
        "props": {
            "pageProps": {
                "trendingSection": {
                    "items": [
                        {
                            "event": {
                                "id": "dup1",
                                "title": "Same Event",
                                "startDate": "2026-04-01T20:00:00Z",
                            }
                        }
                    ]
                },
                "feedItems": [
                    {
                        "event": {
                            "id": "dup1",
                            "title": "Same Event",
                            "startDate": "2026-04-01T20:00:00Z",
                        }
                    }
                ],
            }
        }
    }
    html = f'<html><body><script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script></body></html>'
    events = scraper._parse_page(html)
    assert len(events) == 1


def test_parse_page_no_next_data():
    scraper = PartifulScraper()
    events = scraper._parse_page("<html><body>Nothing here</body></html>")
    assert events == []
