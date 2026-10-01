"""Tests for the two-option hotline IVR routes."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.bot.twilio_ivr import (
    EMPTY_SLOT_MESSAGE,
    GREETING,
    empty_nav,
    gather_handler,
    voice_entry,
)


def _body(response) -> str:
    body = response.body
    return body if isinstance(body, str) else body.decode()


def _make_request(digits: str = "", query_params: dict | None = None) -> MagicMock:
    request = MagicMock()
    request.form = AsyncMock(return_value={"Digits": digits})
    request.query_params = query_params or {}
    return request


@pytest.mark.asyncio
async def test_voice_greeting() -> None:
    """Greeting should use the exact two-option copy and gather one digit."""
    response = await voice_entry(_make_request())
    body = _body(response)

    assert GREETING in body
    assert "dangerous illicit techno party" in body
    assert "Polly.Emma-Neural" in body
    assert "en-GB" in body
    assert '<Gather action="/twilio/gather"' in body
    assert 'numDigits="1"' in body
    assert "No input received. Goodbye." in body


@pytest.mark.asyncio
@patch("src.bot.twilio_ivr.db")
async def test_gather_digit_1_plays_main_message(mock_db: MagicMock) -> None:
    mock_db.get_hotline_message.return_value = {
        "slot": "main",
        "body": "Come to the big dancefloor on Saturday.",
        "updated_by": "pete",
        "updated_at": "2026-10-01T00:00:00",
    }

    response = await gather_handler(_make_request("1"))
    body = _body(response)

    mock_db.get_hotline_message.assert_called_once_with("main")
    assert "<Say" in body
    assert "Come to the big dancefloor on Saturday." in body
    assert "<Hangup" in body


@pytest.mark.asyncio
@patch("src.bot.twilio_ivr.db")
async def test_gather_digit_2_plays_party_message(mock_db: MagicMock) -> None:
    mock_db.get_hotline_message.return_value = {
        "slot": "party",
        "body": "The party is at an undisclosed warehouse.",
        "updated_by": "pete",
        "updated_at": "2026-10-01T00:00:00",
    }

    response = await gather_handler(_make_request("2"))
    body = _body(response)

    mock_db.get_hotline_message.assert_called_once_with("party")
    assert "The party is at an undisclosed warehouse." in body
    assert "<Hangup" in body


@pytest.mark.asyncio
@pytest.mark.parametrize("digit", ["1", "2"])
@patch("src.bot.twilio_ivr.db")
async def test_gather_empty_slot_redirects_to_empty_nav(mock_db: MagicMock, digit: str) -> None:
    mock_db.get_hotline_message.return_value = None

    response = await gather_handler(_make_request(digit))
    body = _body(response)

    assert '<Redirect method="POST">/twilio/empty_nav</Redirect>' in body
    assert "<Say" not in body


@pytest.mark.asyncio
@pytest.mark.parametrize("digit", ["3", "5", "9", "0", "*", "#"])
async def test_gather_invalid_digit(digit: str) -> None:
    request = _make_request(digit)
    with patch("src.bot.twilio_ivr.db"):
        response = await gather_handler(request)
    body = _body(response)

    assert "Invalid input. Goodbye." in body
    assert "<Hangup" in body


@pytest.mark.asyncio
async def test_empty_nav_entry_prompts_and_gathers() -> None:
    """First entry (no step param) should say the message and gather."""
    response = await empty_nav(_make_request())
    body = _body(response)

    assert EMPTY_SLOT_MESSAGE in body
    assert "press 0 to return to the main menu" in body
    assert '<Gather action="/twilio/empty_nav?step=nav"' in body
    assert 'numDigits="1"' in body
    assert "<Hangup" in body  # timeout hangs up


@pytest.mark.asyncio
async def test_empty_nav_zero_returns_to_main_menu() -> None:
    request = _make_request("0", query_params={"step": "nav"})
    response = await empty_nav(request)
    body = _body(response)

    assert '<Redirect method="POST">/twilio/voice</Redirect>' in body


@pytest.mark.asyncio
@pytest.mark.parametrize("digits", ["1", "9", "*", ""])
async def test_empty_nav_other_or_timeout_hangs_up(digits: str) -> None:
    request = _make_request(digits, query_params={"step": "nav"})
    response = await empty_nav(request)
    body = _body(response)

    assert "<Hangup" in body
    assert "<Redirect" not in body
    assert "<Gather" not in body
