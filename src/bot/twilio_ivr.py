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
        "Press 1 to find a dancefloor, press 2 to hear the dancefloor, "
        "press 3 for information on a dangerous illicit techno party.",
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
        script = _get_published_script()
        resp.say(script, voice="Polly.Emma-Neural", language="en-GB")
        resp.hangup()
    elif digit == "3":
        resp.redirect("/twilio/party_instructions")
    else:
        resp.say("Invalid input. Goodbye.", voice="Polly.Emma-Neural", language="en-GB")
        resp.hangup()

    return Response(content=str(resp), media_type="application/xml")


def _get_published_script() -> str:
    """Return the published weekly script, or a placeholder if none exists."""
    today = date.today()
    week_start = today - timedelta(days=today.weekday())  # Monday
    published = db.get_published_script(week_start)
    if published and published.script_text:
        return published.script_text

    return "No recommendations this week. Call back next week."


@router.post("/party_instructions")
async def party_instructions(request: Request) -> Response:
    """Play back party voice instructions, or fallback if none available."""
    media_url = ""
    try:
        voice_note = db.get_party_voice_note()
        if voice_note and voice_note.get("media_url"):
            media_url = voice_note["media_url"]
    except Exception:
        logger.exception("party_instructions_db_error")

    if not media_url:
        try:
            if db.party_voice_exists_in_storage():
                media_url = db.get_party_voice_storage_url()
        except Exception:
            logger.exception("party_instructions_storage_lookup_error")

    resp = VoiceResponse()

    if media_url:
        try:
            resp.play(media_url)
        except Exception:
            logger.exception("party_instructions_play_error", url=media_url)

        resp.pause(length=1)
        resp.say(
            "Press star to return to the main menu, or hang up.",
            voice="Polly.Emma-Neural",
            language="en-GB",
        )
        gather = Gather(
            num_digits=1,
            action="/twilio/party_nav",
            method="POST",
            timeout=5,
        )
        gather.pause(length=5)
        resp.append(gather)
        resp.hangup()
    else:
        resp.say(
            "No party instructions available. Returning to main menu.",
            voice="Polly.Emma-Neural",
            language="en-GB",
        )
        resp.redirect("/twilio/gather")

    return Response(content=str(resp), media_type="application/xml")


@router.post("/party_nav")
async def party_navigation(request: Request) -> Response:
    """Handle navigation after party instructions playback."""
    form = await request.form()
    digits = form.get("Digits", "")

    resp = VoiceResponse()

    if digits == "*":
        resp.redirect("/twilio/gather")
    else:
        resp.hangup()

    return Response(content=str(resp), media_type="application/xml")
