from src.scrapers.basement import BasementScraper


def test_parse_event_basic():
    scraper = BasementScraper()
    ev = {
        "id": "evt-001",
        "title": "Basement Sessions",
        "start_date": "2026-03-14T23:00:00-04:00",
        "end_date": "2026-03-15T06:00:00-04:00",
        "basement_stage": "DJ Nobu, Objekt",
        "studio_stage": "Local Support",
        "venue_name": "Basement NY",
        "price": "$25",
        "ticket_link": "https://ra.co/events/123",
        "attending_count": 80,
        "description": "Deep techno night.",
        "image": "https://basement.com/img.jpg",
    }
    result = scraper._parse_event(ev)
    assert result is not None
    assert result.source_id == "evt-001"
    assert result.title == "Basement Sessions"
    assert result.artists == ["DJ Nobu", "Objekt", "Local Support"]
    assert result.venue_name == "Basement NY"
    assert result.cost_display == "$25"
    assert result.source_url == "https://ra.co/events/123"
    assert result.attending_count == 80
    assert result.image_url == "https://basement.com/img.jpg"


def test_parse_event_no_date():
    scraper = BasementScraper()
    result = scraper._parse_event({"id": "x", "title": "No Date"})
    assert result is None


def test_parse_event_alternative_date_keys():
    scraper = BasementScraper()
    ev = {
        "id": "evt-002",
        "title": "Alt Key Event",
        "startDate": "2026-04-01T20:00:00Z",
    }
    result = scraper._parse_event(ev)
    assert result is not None
    assert result.event_date.isoformat() == "2026-04-01"


def test_parse_event_artists_as_list():
    scraper = BasementScraper()
    ev = {
        "id": "evt-003",
        "title": "List Artists",
        "start_date": "2026-05-01T22:00:00Z",
        "artists": [{"name": "Artist A"}, {"name": "Artist B"}],
    }
    result = scraper._parse_event(ev)
    assert result is not None
    assert result.artists == ["Artist A", "Artist B"]


def test_parse_event_artists_dedup():
    scraper = BasementScraper()
    ev = {
        "id": "evt-004",
        "title": "Dedup Artists",
        "start_date": "2026-05-01T22:00:00Z",
        "basement_stage": "DJ A, DJ B",
        "lineup": "DJ B, DJ C",
    }
    result = scraper._parse_event(ev)
    assert result is not None
    assert result.artists == ["DJ A", "DJ B", "DJ C"]


def test_parse_event_fallback_url():
    scraper = BasementScraper()
    ev = {
        "id": "evt-005",
        "title": "No Link",
        "start_date": "2026-05-01T22:00:00Z",
    }
    result = scraper._parse_event(ev)
    assert result is not None
    assert result.source_url == "https://basementny.net/events/evt-005"


def test_parse_event_default_venue():
    scraper = BasementScraper()
    ev = {
        "id": "evt-006",
        "title": "No Venue Key",
        "start_date": "2026-05-01T22:00:00Z",
    }
    result = scraper._parse_event(ev)
    assert result is not None
    assert result.venue_name == "Basement NY"
