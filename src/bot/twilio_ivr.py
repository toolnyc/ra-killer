from __future__ import annotations

import asyncio
from datetime import date, timedelta

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import Response
from twilio.twiml.voice_response import Gather, VoiceResponse

from src import db
from src.config import settings
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


@router.get("/party_audio")
async def party_audio(request: Request) -> Response:
    """Proxy and transcode party voice note to MP3 for Twilio compatibility."""
    try:
        voice_note = db.get_party_voice_note()
        storage_url = voice_note["media_url"] if voice_note else db.get_party_voice_storage_url()
        async with httpx.AsyncClient() as client:
            upstream = await client.get(storage_url, timeout=10.0)
            upstream.raise_for_status()
        ogg_data = upstream.content

        # Transcode OGG/Opus → MP3 via ffmpeg (Twilio reliably plays MP3 on PSTN)
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-i", "pipe:0", "-f", "mp3", "-ab", "64k", "pipe:1",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        mp3_data, _ = await asyncio.wait_for(proc.communicate(input=ogg_data), timeout=15.0)

        return Response(
            content=mp3_data,
            media_type="audio/mpeg",
            headers={"Cache-Control": "no-cache"},
        )
    except Exception:
        logger.exception("party_audio_proxy_failed")
        return Response(status_code=404)


@router.post("/party_instructions")
async def party_instructions(request: Request) -> Response:
    """Play back party voice instructions, or fallback if none available."""
    has_voice = False
    try:
        voice_note = db.get_party_voice_note()
        has_voice = bool(voice_note and voice_note.get("media_url"))
    except Exception:
        logger.exception("party_instructions_db_error")

    if not has_voice:
        try:
            has_voice = db.party_voice_exists_in_storage()
        except Exception:
            logger.exception("party_instructions_storage_lookup_error")

    audio_url = f"{settings.base_url}/twilio/party_audio" if has_voice else ""

    resp = VoiceResponse()

    if audio_url:
        resp.play(audio_url)

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
