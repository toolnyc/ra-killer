from datetime import date, time

from src.scrapers.ra import RAScraper


def test_parse_event():
    scraper = RAScraper()
    ev = {
        "id": 12345,
        "title": "Honey Dijon All Night",
        "date": "2025-03-15",
        "startTime": "23:00",
        "endTime": "06:00",
        "contentUrl": "/events/12345",
        "images": [{"filename": "abc123.jpg"}],
        "venue": {"id": 1, "name": "Nowadays", "address": "56-06 Cooper Ave"},
        "artists": [{"id": 1, "name": "Honey Dijon"}, {"id": 2, "name": "Octo Octa"}],
        "attending": 350,
        "cost": "$25-40",
        "pick": {"blurb": "A legendary night of house music"},
    }
    result = scraper._parse_event(ev)
    assert result is not None
    assert result.source_id == "12345"
    assert result.title == "Honey Dijon All Night"
    assert result.event_date == date(2025, 3, 15)
    assert result.start_time == time(23, 0)
    assert result.end_time == time(6, 0)
    assert result.venue_name == "Nowadays"
    assert result.artists == ["Honey Dijon", "Octo Octa"]
    assert result.attending_count == 350
    assert result.cost_display == "$25-40"
    assert result.source_url == "https://ra.co/events/12345"
    assert result.image_url == "https://ra.co/images/events/flyer/abc123.jpg"
    assert result.description == "A legendary night of house music"


def test_parse_event_missing_date():
    scraper = RAScraper()
    ev = {"id": 1, "title": "No Date"}
    assert scraper._parse_event(ev) is None


def test_parse_event_minimal():
    scraper = RAScraper()
    ev = {
        "id": 99,
        "title": "Minimal Event",
        "date": "2025-06-01",
    }
    result = scraper._parse_event(ev)
    assert result is not None
    assert result.title == "Minimal Event"
    assert result.artists == []
    assert result.venue_name is None
