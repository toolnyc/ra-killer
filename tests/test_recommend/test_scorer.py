from datetime import date

from src.models import Event, TasteEntry
from src.recommend.scorer import heuristic_prefilter, heuristic_score
from src.recommend.taste import TasteProfile


def _make_taste() -> TasteProfile:
    return TasteProfile(
        entries=[
            TasteEntry(category="artist", name="Honey Dijon", weight=2.0),
            TasteEntry(category="artist", name="DJ Harvey", weight=2.0),
            TasteEntry(category="venue", name="Nowadays", weight=2.0),
            TasteEntry(category="venue", name="Bad Venue", weight=-1.0),
        ]
    )


def test_heuristic_score_known_artist():
    taste = _make_taste()
    event = Event(
        title="Test",
        event_date=date(2025, 4, 1),
        artists=["Honey Dijon"],
        venue_name="Unknown Venue",
    )
    score = heuristic_score(event, taste)
    assert score > 0  # Should get artist bonus


def test_heuristic_score_known_venue():
    taste = _make_taste()
    event = Event(
        title="Test",
        event_date=date(2025, 4, 1),
        artists=[],
        venue_name="Nowadays",
    )
    score = heuristic_score(event, taste)
    assert score > 0  # Should get venue bonus


def test_heuristic_score_disliked_venue():
    taste = _make_taste()
    event = Event(
        title="Test",
        event_date=date(2025, 4, 1),
        artists=[],
        venue_name="Bad Venue",
    )
    score = heuristic_score(event, taste)
    assert score < 0  # Should be negative


def test_heuristic_score_unknown():
    taste = _make_taste()
    event = Event(
        title="Random Event",
        event_date=date(2025, 4, 1),
        artists=["Unknown DJ"],
        venue_name="Unknown Venue",
    )
    score = heuristic_score(event, taste)
    assert score == 0  # No matches


def test_heuristic_prefilter():
    taste = _make_taste()
    events = [
        Event(id="1", title="Known", event_date=date(2025, 4, 1), artists=["Honey Dijon"]),
        Event(id="2", title="Unknown", event_date=date(2025, 4, 1), artists=["DJ Nobody"]),
        Event(id="3", title="Also Known", event_date=date(2025, 4, 1), venue_name="Nowadays"),
    ]
    scored, discovery = heuristic_prefilter(events, taste)
    assert len(scored) == 2  # events with known artist/venue
    assert len(discovery) == 1  # unknown event for discovery


def test_taste_profile_prompt():
    taste = _make_taste()
    text = taste.to_prompt_text()
    assert "honey dijon" in text
    assert "nowadays" in text
    assert "genre" not in text.lower()
