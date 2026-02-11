import json

from src.scrapers.dice import DICEScraper


def test_parse_event():
    scraper = DICEScraper()
    ev = {
        "id": "abc123",
        "name": "Techno Warehouse Party",
        "dates": {
            "event_start_date": "2025-03-15T23:00:00-05:00",
            "event_end_date": "2025-03-16T06:00:00-05:00",
        },
        "venues": [{"name": "Knockdown Center", "address": "52-19 Flushing Ave"}],
        "summary_lineup": {
            "top_artists": [{"name": "Ben UFO"}, {"name": "Joy Orbison"}],
            "total_artists": 2,
        },
        "price": {"currency": "USD", "amount": 2500},
        "perm_name": "abc123-techno-warehouse-party-tickets",
        "images": {"square": "https://dice.fm/images/abc.jpg"},
        "about": {"description": "A night of quality selections"},
    }
    result = scraper._parse_event(ev)
    assert result is not None
    assert result.source_id == "abc123"
    assert result.title == "Techno Warehouse Party"
    assert result.venue_name == "Knockdown Center"
    assert result.artists == ["Ben UFO", "Joy Orbison"]
    assert result.price_min_cents == 2500
    assert result.cost_display == "$25"
    assert result.source_url == "https://dice.fm/event/abc123-techno-warehouse-party-tickets"


def test_parse_page_with_next_data():
    scraper = DICEScraper()
    data = {
        "props": {
            "pageProps": {
                "events": [
                    {
                        "id": "ev1",
                        "name": "Test Event",
                        "date_unix": 1743548400,
                        "dates": {
                            "event_start_date": "2025-04-01T21:00:00-04:00",
                        },
                        "venues": [{"name": "Elsewhere"}],
                    }
                ]
            }
        }
    }
    html = f'<html><body><script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script></body></html>'
    events = scraper._parse_page(html)
    assert len(events) == 1
    assert events[0].title == "Test Event"


def test_parse_page_no_next_data():
    scraper = DICEScraper()
    events = scraper._parse_page("<html><body>No data here</body></html>")
    assert events == []
