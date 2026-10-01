from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import Response
from twilio.twiml.voice_response import Gather, VoiceResponse

from src import db
from src.log import get_logger

logger = get_logger("twilio")

router = APIRouter(prefix="/twilio")

VOICE = "Polly.Emma-Neural"
LANGUAGE = "en-GB"

GREETING = (
    "You've reached Clubstack. We are New York's only dancefloor hotline. "
    "We motivate you to shake that ass. "
    "Press 1 to find a dancefloor, press 2 to learn more about a dangerous "
    "illicit techno party."
)

EMPTY_SLOT_MESSAGE = (
    "Nothing is available at the moment, please call back later or press 0 "
    "to return to the main menu."
)

# Digit -> hotline_messages slot
SLOT_BY_DIGIT = {"1": "main", "2": "party"}


def _say(resp: VoiceResponse, text: str) -> None:
    resp.say(text, voice=VOICE, language=LANGUAGE)


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
    gather.say(GREETING, voice=VOICE, language=LANGUAGE)
    resp.append(gather)
    _say(resp, "No input received. Goodbye.")
    return Response(content=str(resp), media_type="application/xml")


@router.post("/gather")
async def gather_handler(request: Request) -> Response:
    """Handle digit input from the main menu."""
    form = await request.form()
    digit = form.get("Digits", "")

    resp = VoiceResponse()

    slot = SLOT_BY_DIGIT.get(digit)
    if slot:
        message = db.get_hotline_message(slot)
        if message and message.get("body"):
            _say(resp, message["body"])
            resp.hangup()
        else:
            resp.redirect("/twilio/empty_nav", method="POST")
    else:
        _say(resp, "Invalid input. Goodbye.")
        resp.hangup()

    return Response(content=str(resp), media_type="application/xml")


@router.post("/empty_nav")
async def empty_nav(request: Request) -> Response:
    """Empty-slot flow: prompt once, then 0 returns to the main menu.

    First entry (from /twilio/gather redirect) says the empty-slot message and
    gathers a digit. The gather callback (?step=nav) redirects on 0 and hangs
    up on anything else, including timeout.
    """
    resp = VoiceResponse()

    if request.query_params.get("step") != "nav":
        gather = Gather(
            num_digits=1,
            action="/twilio/empty_nav?step=nav",
            method="POST",
            timeout=5,
        )
        gather.say(EMPTY_SLOT_MESSAGE, voice=VOICE, language=LANGUAGE)
        resp.append(gather)
        resp.hangup()
    else:
        form = await request.form()
        digit = form.get("Digits", "")
        if digit == "0":
            resp.redirect("/twilio/voice", method="POST")
        else:
            resp.hangup()

    return Response(content=str(resp), media_type="application/xml")
