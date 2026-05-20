"""Tests for party voice note Telegram commands."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.bot.telegram import (
    cmd_clear_party_voice,
    cmd_preview_party_voice,
    cmd_set_party_voice,
)


def _make_update_with_voice(reply_voice: bool = True, voice_duration: int = 30) -> MagicMock:
    """Build a mock Update with a voice message reply."""
    update = MagicMock()
    update.message = AsyncMock()
    update.message.from_user.username = "testuser"
    update.message.from_user.id = 12345
    update.message.reply_text = AsyncMock()
    update.message.reply_voice = AsyncMock()

    if reply_voice:
        voice = MagicMock()
        voice.file_id = "ABC123"
        voice.duration = voice_duration
        update.message.reply_to_message = MagicMock()
        update.message.reply_to_message.voice = voice
    else:
        update.message.reply_to_message = None

    return update


@pytest.mark.asyncio
@patch("src.bot.telegram.db")
async def test_set_party_voice_success(mock_db: MagicMock) -> None:
    """Successfully uploading a voice note should update database."""
    status_msg = AsyncMock()
    
    mock_db.upload_to_supabase_storage = AsyncMock(
        return_value="https://storage.example.com/audio.ogg"
    )
    mock_db.upsert_party_voice_note = MagicMock()

    update = _make_update_with_voice(voice_duration=30)
    update.message.reply_text = AsyncMock(return_value=status_msg)
    update.message.bot.get_file = AsyncMock()
    update.message.bot.get_file.return_value.download_as_bytearray = AsyncMock(
        return_value=b"fake audio data"
    )

    context = MagicMock()

    await cmd_set_party_voice(update, context)

    mock_db.upload_to_supabase_storage.assert_called_once()
    mock_db.upsert_party_voice_note.assert_called_once()
    # Check that the status message was edited with the success message
    status_msg.edit_text.assert_called_once_with(
        "Party voice note updated! Callers pressing 3 will now hear this recording."
    )


@pytest.mark.asyncio
@patch("src.bot.telegram.db")
async def test_set_party_voice_no_reply(mock_db: MagicMock) -> None:
    """Calling without replying to a voice message should show error."""
    update = _make_update_with_voice(reply_voice=False)
    context = MagicMock()

    await cmd_set_party_voice(update, context)

    update.message.reply_text.assert_called_once()
    args = update.message.reply_text.call_args[0]
    assert "Reply to a voice message" in args[0]


@pytest.mark.asyncio
@patch("src.bot.telegram.db")
async def test_set_party_voice_file_too_large(mock_db: MagicMock) -> None:
    """File larger than 5MB should be rejected."""
    update = _make_update_with_voice()
    update.message.bot.get_file = AsyncMock()
    # Return 6MB of data
    update.message.bot.get_file.return_value.download_as_bytearray = AsyncMock(
        return_value=b"x" * (6 * 1024 * 1024)
    )
    update.message.reply_text = AsyncMock()
    status_msg = AsyncMock()
    update.message.reply_text.return_value = status_msg

    context = MagicMock()

    await cmd_set_party_voice(update, context)

    status_msg.edit_text.assert_called()
    args = status_msg.edit_text.call_args[0]
    assert "File too large" in args[0]


@pytest.mark.asyncio
@patch("src.bot.telegram.db")
async def test_set_party_voice_too_long(mock_db: MagicMock) -> None:
    """Voice note longer than 60 seconds should be rejected."""
    update = _make_update_with_voice(voice_duration=120)
    update.message.reply_text = AsyncMock()
    status_msg = AsyncMock()
    update.message.reply_text.return_value = status_msg

    context = MagicMock()

    await cmd_set_party_voice(update, context)

    status_msg.edit_text.assert_called()
    args = status_msg.edit_text.call_args[0]
    assert "too long" in args[0].lower()


@pytest.mark.asyncio
@patch("src.bot.telegram.db")
async def test_set_party_voice_upload_error(mock_db: MagicMock) -> None:
    """Upload failure should be caught and reported."""
    mock_db.upload_to_supabase_storage = AsyncMock(
        side_effect=Exception("Upload failed")
    )

    update = _make_update_with_voice()
    update.message.bot.get_file = AsyncMock()
    update.message.bot.get_file.return_value.download_as_bytearray = AsyncMock(
        return_value=b"fake audio data"
    )
    update.message.reply_text = AsyncMock()

    context = MagicMock()

    await cmd_set_party_voice(update, context)

    update.message.reply_text.assert_any_call(
        "Failed to upload voice note. Please try again or contact admin."
    )


@pytest.mark.asyncio
@patch("src.bot.telegram.db")
async def test_clear_party_voice_success(mock_db: MagicMock) -> None:
    """Clearing voice note should delete from database."""
    mock_db.delete_party_voice_note = MagicMock()

    update = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()

    await cmd_clear_party_voice(update, context)

    mock_db.delete_party_voice_note.assert_called_once()
    update.message.reply_text.assert_called_once()
    args = update.message.reply_text.call_args[0]
    assert "Party voice note cleared" in args[0]


@pytest.mark.asyncio
@patch("src.bot.telegram.db")
async def test_clear_party_voice_error(mock_db: MagicMock) -> None:
    """Database error should be caught."""
    mock_db.delete_party_voice_note.side_effect = Exception("DB error")

    update = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()

    await cmd_clear_party_voice(update, context)

    update.message.reply_text.assert_called_once()
    args = update.message.reply_text.call_args[0]
    assert "Failed" in args[0]


@pytest.mark.asyncio
@patch("src.bot.telegram.db")
async def test_preview_party_voice_exists(mock_db: MagicMock) -> None:
    """Preview with existing voice note should send it."""
    mock_db.get_party_voice_note.return_value = {
        "media_url": "https://storage.example.com/audio.ogg",
        "updated_at": "2025-05-20T12:00:00",
        "updated_by": "testuser",
    }
    mock_db.download_from_supabase_storage = AsyncMock(return_value=b"audio data")

    update = MagicMock()
    update.message.reply_voice = AsyncMock()
    context = MagicMock()

    await cmd_preview_party_voice(update, context)

    mock_db.download_from_supabase_storage.assert_called_once()
    update.message.reply_voice.assert_called_once()


@pytest.mark.asyncio
@patch("src.bot.telegram.db")
async def test_preview_party_voice_not_set(mock_db: MagicMock) -> None:
    """Preview with no voice note should show message."""
    mock_db.get_party_voice_note.return_value = None

    update = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()

    await cmd_preview_party_voice(update, context)

    update.message.reply_text.assert_called_once()
    args = update.message.reply_text.call_args[0]
    assert "No party voice note" in args[0]


@pytest.mark.asyncio
@patch("src.bot.telegram.db")
async def test_preview_party_voice_error(mock_db: MagicMock) -> None:
    """Download error should be caught."""
    mock_db.get_party_voice_note.return_value = {
        "media_url": "https://storage.example.com/audio.ogg"
    }
    mock_db.download_from_supabase_storage = AsyncMock(
        side_effect=Exception("Download failed")
    )

    update = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()

    await cmd_preview_party_voice(update, context)

    update.message.reply_text.assert_called()
    args = update.message.reply_text.call_args[0]
    assert "Failed" in args[0]
