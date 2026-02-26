from datetime import date

from src.scrapers.lightandsound import LightAndSoundScraper


def test_parse_listing_basic():
    scraper = LightAndSoundScraper()
    html = """
    <html><body>
        <a href="https://eventcreate.com/e/abc123">
            <span class="date">03.15.2026</span>
            Techno Night
        </a>
    </body></html>
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    events = scraper._parse_listing(soup)
    assert len(events) == 1
    assert events[0].title == "Techno Night"
    assert events[0].event_date == date(2026, 3, 15)
    assert events[0].source_id == "abc123"
    assert "eventcreate.com" in events[0].source_url


def test_parse_listing_dice_link():
    scraper = LightAndSoundScraper()
    html = """
    <html><body>
        <a href="https://dice.fm/event/some-event-slug">
            <span class="date">04.01.2026</span>
            Dice Event
        </a>
    </body></html>
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    events = scraper._parse_listing(soup)
    assert len(events) == 1
    assert events[0].title == "Dice Event"


def test_parse_listing_skips_non_event_links():
    scraper = LightAndSoundScraper()
    html = """
    <html><body>
        <a href="https://instagram.com/lightandsound">Follow us</a>
        <a href="/about">About</a>
        <a href="https://eventcreate.com/e/real-event">
            <span class="date">05.01.2026</span>
            Real Event
        </a>
    </body></html>
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    events = scraper._parse_listing(soup)
    assert len(events) == 1
    assert events[0].title == "Real Event"


def test_parse_listing_no_date_span():
    scraper = LightAndSoundScraper()
    html = """
    <html><body>
        <a href="https://eventcreate.com/e/no-date">
            No Date Event
        </a>
    </body></html>
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    events = scraper._parse_listing(soup)
    assert events == []


def test_parse_date_formats():
    scraper = LightAndSoundScraper()
    assert scraper._parse_date_text("03.15.2026") == date(2026, 3, 15)
    assert scraper._parse_date_text("2026-03-15") == date(2026, 3, 15)
    assert scraper._parse_date_text("March 15, 2026") == date(2026, 3, 15)
    assert scraper._parse_date_text("Mar 15, 2026") == date(2026, 3, 15)
    assert scraper._parse_date_text("03/15/2026") == date(2026, 3, 15)


def test_parse_date_empty():
    scraper = LightAndSoundScraper()
    assert scraper._parse_date_text("") is None
    assert scraper._parse_date_text(None) is None


def test_parse_date_invalid():
    scraper = LightAndSoundScraper()
    assert scraper._parse_date_text("not a date") is None
