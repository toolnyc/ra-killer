from datetime import date, time

from bs4 import BeautifulSoup

from src.scrapers.nycnoise import NYCNoiseScraper


def _make_soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


def test_parse_basic_event():
    html = """
    <div class="event" data-date="032525" data-starttime="10pm"
         data-title-and-artists="House Party | DJ Harvey, Floating Points"
         data-venue-id="123">
        <span>@ Nowadays (21+), ridgewood, queens</span>
        <a href="https://ra.co/events/123">Tickets</a>
    </div>
    """
    scraper = NYCNoiseScraper()
    events = scraper._parse_page(_make_soup(html))
    assert len(events) == 1
    ev = events[0]
    assert ev.event_date == date(2025, 3, 25)
    assert ev.start_time == time(22, 0)
    assert ev.title == "House Party"
    assert ev.artists == ["DJ Harvey", "Floating Points"]
    assert ev.venue_name == "Nowadays"
    assert ev.source_url == "https://ra.co/events/123"


def test_parse_no_date():
    html = '<div data-title-and-artists="Event">content</div>'
    scraper = NYCNoiseScraper()
    events = scraper._parse_page(_make_soup(html))
    assert len(events) == 0


def test_parse_time_str():
    assert NYCNoiseScraper._parse_time_str("8pm") == time(20, 0)
    assert NYCNoiseScraper._parse_time_str("10:30 PM") == time(22, 30)
    assert NYCNoiseScraper._parse_time_str("12am") == time(0, 0)
    assert NYCNoiseScraper._parse_time_str("12pm") == time(12, 0)
    assert NYCNoiseScraper._parse_time_str("") is None
    # Time ranges should parse start time only
    assert NYCNoiseScraper._parse_time_str("7pm-10pm") == time(19, 0)


def test_parse_dash_separator():
    html = """
    <div class="event" data-date="040125" data-title-and-artists="Techno Night - DJ A, DJ B"
         data-venue-id="456">
        <span>@ Basement (21+), bushwick, bklyn</span>
    </div>
    """
    scraper = NYCNoiseScraper()
    events = scraper._parse_page(_make_soup(html))
    assert len(events) == 1
    assert events[0].title == "Techno Night"
    assert events[0].artists == ["DJ A", "DJ B"]


def test_parse_date_code():
    assert NYCNoiseScraper._parse_date_code("021126") == date(2026, 2, 11)
    assert NYCNoiseScraper._parse_date_code("123125") == date(2025, 12, 31)
    assert NYCNoiseScraper._parse_date_code("") is None
    assert NYCNoiseScraper._parse_date_code("invalid") is None
