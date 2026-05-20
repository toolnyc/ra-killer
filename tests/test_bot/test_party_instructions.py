"""Tests for party instructions IVR feature."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.bot.twilio_ivr import party_instructions, party_navigation
from src.config import settings
from src.models import WeeklyScript

PROXY_URL = f"{settings.base_url}/twilio/party_audio"


@pytest.mark.asyncio
@patch("src.bot.twilio_ivr.db")
async def test_party_instructions_with_voice_note(mock_db: MagicMock) -> None:
    """Playing voice note should include <Play> with media URL."""
    mock_db.get_party_voice_note.return_value = {
        "id": 1,
        "media_url": "https://example.com/audio/test.ogg",
        "updated_at": "2025-05-20T12:00:00",
        "updated_by": "testuser",
    }

    request = MagicMock()
    request.form = AsyncMock(return_value={})

    response = await party_instructions(request)
    
    body = response.body if isinstance(response.body, str) else response.body.decode()

    assert f"<Play>{PROXY_URL}</Play>" in body
    assert "Press star to return to the main menu" in body
    assert "<Gather" in body


@pytest.mark.asyncio
@patch("src.bot.twilio_ivr.db")
async def test_party_instructions_no_voice_note(mock_db: MagicMock) -> None:
    """With no voice note, should show fallback message and redirect."""
    mock_db.get_party_voice_note.return_value = None
    mock_db.party_voice_exists_in_storage.return_value = False

    request = MagicMock()
    request.form = AsyncMock(return_value={})

    response = await party_instructions(request)
    
    body = response.body if isinstance(response.body, str) else response.body.decode()

    assert "No party instructions available" in body
    assert "<Redirect>/twilio/gather</Redirect>" in body


@pytest.mark.asyncio
@patch("src.bot.twilio_ivr.db")
async def test_party_instructions_empty_url(mock_db: MagicMock) -> None:
    """With empty media_url, should show fallback message."""
    mock_db.get_party_voice_note.return_value = {
        "id": 1,
        "media_url": None,
        "updated_at": "2025-05-20T12:00:00",
        "updated_by": "testuser",
    }
    mock_db.party_voice_exists_in_storage.return_value = False

    request = MagicMock()
    request.form = AsyncMock(return_value={})

    response = await party_instructions(request)
    
    body = response.body if isinstance(response.body, str) else response.body.decode()

    assert "No party instructions available" in body


@pytest.mark.asyncio
@patch("src.bot.twilio_ivr.db")
async def test_party_instructions_db_error(mock_db: MagicMock) -> None:
    """Database error should fall back to storage lookup."""
    mock_db.get_party_voice_note.side_effect = Exception("DB down")
    mock_db.party_voice_exists_in_storage.return_value = False

    request = MagicMock()
    request.form = AsyncMock(return_value={})

    response = await party_instructions(request)
    
    body = response.body if isinstance(response.body, str) else response.body.decode()

    assert "No party instructions available" in body


@pytest.mark.asyncio
@patch("src.bot.twilio_ivr.db")
async def test_party_instructions_storage_fallback(mock_db: MagicMock) -> None:
    """When DB has no record, storage fallback URL should be used."""
    mock_db.get_party_voice_note.return_value = None
    mock_db.party_voice_exists_in_storage.return_value = True
    mock_db.get_party_voice_storage_url.return_value = "https://example.com/audio/fallback.ogg"

    request = MagicMock()
    request.form = AsyncMock(return_value={})

    response = await party_instructions(request)

    body = response.body if isinstance(response.body, str) else response.body.decode()

    assert f"<Play>{PROXY_URL}</Play>" in body


@pytest.mark.asyncio
async def test_party_nav_star_key() -> None:
    """Pressing * should redirect to main menu."""
    request = MagicMock()
    request.form = AsyncMock(return_value={"Digits": "*"})

    response = await party_navigation(request)
    
    body = response.body if isinstance(response.body, str) else response.body.decode()

    assert "<Redirect>/twilio/gather</Redirect>" in body


@pytest.mark.asyncio
async def test_party_nav_other_input() -> None:
    """Any other input should hangup."""
    for digit in ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "#"]:
        request = MagicMock()
        request.form = AsyncMock(return_value={"Digits": digit})

        response = await party_navigation(request)
        
        body = response.body if isinstance(response.body, str) else response.body.decode()

        assert "<Hangup" in body


@pytest.mark.asyncio
async def test_party_nav_timeout() -> None:
    """Timeout (no digits) should hangup."""
    request = MagicMock()
    request.form = AsyncMock(return_value={"Digits": ""})

    response = await party_navigation(request)
    
    body = response.body if isinstance(response.body, str) else response.body.decode()

    assert "<Hangup" in body
