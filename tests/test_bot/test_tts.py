from datetime import date, time

from src.bot.tts import build_week_tts_script, event_to_tts_script
from src.models import Event, Recommendation


def _make_event(**overrides) -> Event:
    defaults = dict(
        id="ev1",
        title="Warehouse Rave",
        event_date=date(2026, 3, 7),
        venue_name="Knockdown Center",
        artists=["Ben UFO", "Joy Orbison"],
    )
    defaults.update(overrides)
    return Event(**defaults)


def _make_rec(**overrides) -> Recommendation:
    defaults = dict(event_id="ev1", score=85.0, reasoning="Great lineup.")
    defaults.update(overrides)
    return Recommendation(**defaults)


def test_basic_event_tts():
    ev = _make_event()
    script = event_to_tts_script(ev)
    assert "Warehouse Rave" in script
    assert "Ben UFO and Joy Orbison" in script
    assert "Knockdown Center" in script
    assert "Saturday, March 07" in script


def test_event_tts_with_time():
    ev = _make_event(start_time=time(23, 0))
    script = event_to_tts_script(ev)
    assert "11:00 PM" in script


def test_event_tts_with_price():
    ev = _make_event(cost_display="$30")
    script = event_to_tts_script(ev)
    assert "Tickets are $30" in script


def test_event_tts_with_attending():
    ev = _make_event(attending_count=200)
    script = event_to_tts_script(ev)
    assert "200 people attending" in script


def test_event_tts_low_attending_omitted():
    ev = _make_event(attending_count=10)
    script = event_to_tts_script(ev)
    assert "people attending" not in script


def test_event_tts_with_recommendation():
    ev = _make_event()
    rec = _make_rec()
    script = event_to_tts_script(ev, rec)
    assert "Great lineup." in script


def test_event_tts_no_artists():
    ev = _make_event(artists=[])
    script = event_to_tts_script(ev)
    assert "lineup to be announced" in script


def test_event_tts_no_venue():
    ev = _make_event(venue_name=None)
    script = event_to_tts_script(ev)
    assert "venue to be announced" in script


def test_build_week_empty():
    script = build_week_tts_script([])
    assert "No recommended events" in script


def test_build_week_multiple():
    ev1 = _make_event(title="Event One")
    ev2 = _make_event(title="Event Two", id="ev2")
    rec1 = _make_rec()
    rec2 = _make_rec(event_id="ev2")
    script = build_week_tts_script([(ev1, rec1), (ev2, rec2)])
    assert "top 2 recommended" in script
    assert "Number 1" in script
    assert "Number 2" in script
    assert "Event One" in script
    assert "Event Two" in script
    assert "That's all for this week" in script


def test_build_week_single():
    ev = _make_event()
    rec = _make_rec()
    script = build_week_tts_script([(ev, rec)])
    assert "top 1 recommended" in script
    assert "Number 1" in script
