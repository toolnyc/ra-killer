from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Request
from fastapi.responses import Response
from twilio.twiml.voice_response import Gather, VoiceResponse

from src import db
from src.log import get_logger

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
        "You've reached Clubstack. We are New York's only dancefloor hotline. "
        "We motivate you to shake that ass. "
        "Press 1 to find a dancefloor, press 2 to hear the dancefloor.",
        voice="Polly.Emma-Neural",
        language="en-GB",
    )
    resp.append(gather)
    resp.say("No input received. Goodbye.", voice="Polly.Emma-Neural", language="en-GB")
    return Response(content=str(resp), media_type="application/xml")


@router.post("/gather")
async def gather_handler(request: Request) -> Response:
    """Handle digit input."""
    form = await request.form()
    digit = form.get("Digits", "")

    resp = VoiceResponse()

    if digit in ("1", "2"):
        script = _get_approved_script()
        resp.say(script, voice="Polly.Emma-Neural", language="en-GB")
    else:
        resp.say("Invalid input. Goodbye.", voice="Polly.Emma-Neural", language="en-GB")

    resp.hangup()
    return Response(content=str(resp), media_type="application/xml")


def _get_approved_script() -> str:
    """Return the approved weekly script, or a placeholder if none exists."""
    today = date.today()
    week_start = today - timedelta(days=today.weekday())  # Monday
    approved = db.get_latest_approved_script(week_start)
    if approved and approved.script_text:
        return approved.script_text

    return (
        "There's no approved script for this week yet. "
        "Check back soon for the latest dancefloor picks."
    )
