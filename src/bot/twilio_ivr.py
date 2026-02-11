from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import Response
from twilio.twiml.voice_response import Gather, VoiceResponse

from src import db
from src.bot.tts import build_week_tts_script
from src.log import get_logger
from src.models import Event, Recommendation

logger = get_logger("twilio")

router = APIRouter(prefix="/twilio")


@router.post("/voice")
async def voice_entry(request: Request) -> Response:
    """Entry point for incoming calls."""
    resp = VoiceResponse()
    gather = Gather(
        num_digits=1,
        action="/twilio/gather",
        method="POST",
        timeout=5,
    )
    gather.say(
        "Welcome to ra killer, your NYC event hotline. "
        "Press 1 to hear this week's top picks. "
        "Press 2 to hear all recommended events.",
        voice="Polly.Matthew",
    )
    resp.append(gather)
    resp.say("No input received. Goodbye.", voice="Polly.Matthew")
    return Response(content=str(resp), media_type="application/xml")


@router.post("/gather")
async def gather_handler(request: Request) -> Response:
    """Handle digit input."""
    form = await request.form()
    digit = form.get("Digits", "")

    resp = VoiceResponse()

    if digit in ("1", "2"):
        limit = 5 if digit == "1" else 20
        script = _get_events_script(limit)
        resp.say(script, voice="Polly.Matthew")
    else:
        resp.say("Invalid input. Goodbye.", voice="Polly.Matthew")

    resp.hangup()
    return Response(content=str(resp), media_type="application/xml")


def _get_events_script(limit: int) -> str:
    """Build TTS script from this week's recommendations."""
    recs_data = db.get_week_recommendations()

    if not recs_data:
        return "No recommended events this week. Check back later."

    events_and_recs = []
    for r in recs_data[:limit]:
        ev_data = r.get("events", {})
        if not ev_data:
            continue

        # Parse event from joined data
        from datetime import date, time

        event = Event(
            id=ev_data.get("id"),
            title=ev_data.get("title", ""),
            event_date=date.fromisoformat(ev_data["event_date"]) if ev_data.get("event_date") else date.today(),
            start_time=time.fromisoformat(ev_data["start_time"]) if ev_data.get("start_time") else None,
            end_time=time.fromisoformat(ev_data["end_time"]) if ev_data.get("end_time") else None,
            venue_name=ev_data.get("venue_name"),
            artists=ev_data.get("artists") or [],
            cost_display=ev_data.get("cost_display"),
            attending_count=ev_data.get("attending_count"),
        )

        rec = Recommendation(
            id=r.get("id"),
            event_id=r.get("event_id", ""),
            score=r.get("score", 0),
            reasoning=r.get("reasoning", ""),
        )

        events_and_recs.append((event, rec))

    return build_week_tts_script(events_and_recs)
