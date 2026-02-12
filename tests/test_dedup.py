from datetime import date

from src.models import Event, ScrapedEvent, Source
from src.normalize import normalize
from src.scrapers.runner import (
    artist_jaccard,
    is_fuzzy_match,
    merge_into_canonical,
)


def test_normalize():
    assert normalize("Hello World!") == "hello world"
    assert normalize("DJ Harvey (Live)") == "dj harvey live"
    assert normalize("  multiple   spaces  ") == "multiple spaces"


def test_artist_jaccard_identical():
    assert artist_jaccard(["DJ A", "DJ B"], ["DJ A", "DJ B"]) == 1.0


def test_artist_jaccard_partial():
    result = artist_jaccard(["DJ A", "DJ B", "DJ C"], ["DJ A", "DJ B"])
    assert 0.5 < result < 1.0


def test_artist_jaccard_empty():
    assert artist_jaccard([], ["DJ A"]) == 0.0
    assert artist_jaccard([], []) == 0.0


def test_is_fuzzy_match_same_title_venue():
    scraped = ScrapedEvent(
        source=Source.DICE,
        source_id="123",
        title="Honey Dijon at Nowadays",
        event_date=date(2025, 3, 15),
        venue_name="Nowadays",
        artists=["Honey Dijon"],
    )
    existing = Event(
        id="abc",
        title="Honey Dijon at Nowadays",
        event_date=date(2025, 3, 15),
        venue_name="Nowadays",
        artists=["Honey Dijon"],
    )
    assert is_fuzzy_match(scraped, existing) is True


def test_is_fuzzy_match_different_date():
    scraped = ScrapedEvent(
        source=Source.DICE,
        source_id="123",
        title="Same Event",
        event_date=date(2025, 3, 15),
    )
    existing = Event(
        id="abc",
        title="Same Event",
        event_date=date(2025, 3, 16),
    )
    assert is_fuzzy_match(scraped, existing) is False


def test_is_fuzzy_match_similar_title():
    scraped = ScrapedEvent(
        source=Source.RA,
        source_id="456",
        title="Honey Dijon All Night Long",
        event_date=date(2025, 3, 15),
        venue_name="Nowadays",
        artists=["Honey Dijon"],
    )
    existing = Event(
        id="abc",
        title="Honey Dijon: All Night Long",
        event_date=date(2025, 3, 15),
        venue_name="Nowadays",
        artists=["Honey Dijon"],
    )
    assert is_fuzzy_match(scraped, existing) is True


def test_no_fuzzy_match_different_events():
    scraped = ScrapedEvent(
        source=Source.RA,
        source_id="789",
        title="Techno Night with DJ A",
        event_date=date(2025, 3, 15),
        venue_name="Basement",
        artists=["DJ A"],
    )
    existing = Event(
        id="abc",
        title="House Party with DJ B",
        event_date=date(2025, 3, 15),
        venue_name="Good Room",
        artists=["DJ B"],
    )
    assert is_fuzzy_match(scraped, existing) is False


def test_merge_new_event():
    scraped = ScrapedEvent(
        source=Source.RA,
        source_id="100",
        title="Test Event",
        event_date=date(2025, 4, 1),
        venue_name="Nowadays",
        artists=["DJ A", "DJ B"],
        cost_display="$20",
        source_url="https://ra.co/events/100",
    )
    result = merge_into_canonical(scraped, None)
    assert result.title == "Test Event"
    assert result.venue_name == "Nowadays"
    assert result.artists == ["DJ A", "DJ B"]
    assert result.sources == ["ra"]
    assert result.source_urls == {"ra": "https://ra.co/events/100"}


def test_merge_enriches_existing():
    existing = Event(
        id="existing-1",
        title="Test Event",
        event_date=date(2025, 4, 1),
        venue_name="Nowadays",
        artists=["DJ A"],
        sources=["ra"],
        source_urls={"ra": "https://ra.co/events/100"},
    )
    scraped = ScrapedEvent(
        source=Source.DICE,
        source_id="200",
        title="Test Event",
        event_date=date(2025, 4, 1),
        venue_name="Nowadays",
        venue_address="56-06 Cooper Ave, Brooklyn",
        artists=["DJ A", "DJ B", "DJ C"],
        cost_display="$25",
        source_url="https://dice.fm/events/200",
    )
    result = merge_into_canonical(scraped, existing)
    assert result.venue_address == "56-06 Cooper Ave, Brooklyn"
    assert result.artists == ["DJ A", "DJ B", "DJ C"]  # richer list wins
    assert "dice" in result.sources
    assert "ra" in result.sources
    assert result.source_urls["dice"] == "https://dice.fm/events/200"
