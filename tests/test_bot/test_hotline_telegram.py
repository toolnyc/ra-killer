"""Tests for hotline message Telegram commands."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.bot.telegram import (
    HOTLINE_MESSAGE_MAX_CHARS,
    cmd_preview_messages,
    cmd_set_main,
    cmd_set_party,
)


def _make_update(args: list[str] | None = None) -> tuple[MagicMock, MagicMock]:
    update = MagicMock()
    update.message.reply_text = AsyncMock()
    update.message.from_user.username = "testuser"
    update.message.from_user.id = 12345
    context = MagicMock()
    context.args = args or []
    return update, context


@pytest.mark.asyncio
@patch("src.bot.telegram.db")
async def test_set_main_stores_and_echoes(mock_db: MagicMock) -> None:
    update, context = _make_update(["Come", "dance", "Saturday"])

    await cmd_set_main(update, context)

    mock_db.upsert_hotline_message.assert_called_once_with(
        "main", "Come dance Saturday", updated_by="testuser"
    )
    text = update.message.reply_text.call_args[0][0]
    assert "Come dance Saturday" in text


@pytest.mark.asyncio
@patch("src.bot.telegram.db")
async def test_set_party_stores_and_echoes(mock_db: MagicMock) -> None:
    update, context = _make_update(["Secret", "warehouse", "party"])

    await cmd_set_party(update, context)

    mock_db.upsert_hotline_message.assert_called_once_with(
        "party", "Secret warehouse party", updated_by="testuser"
    )
    text = update.message.reply_text.call_args[0][0]
    assert "Secret warehouse party" in text


@pytest.mark.asyncio
@patch("src.bot.telegram.db")
async def test_set_main_no_args_shows_usage(mock_db: MagicMock) -> None:
    update, context = _make_update([])

    await cmd_set_main(update, context)

    mock_db.upsert_hotline_message.assert_not_called()
    text = update.message.reply_text.call_args[0][0]
    assert "Usage: /set_main" in text


@pytest.mark.asyncio
@patch("src.bot.telegram.db")
async def test_set_party_no_args_shows_usage(mock_db: MagicMock) -> None:
    update, context = _make_update([])

    await cmd_set_party(update, context)

    mock_db.upsert_hotline_message.assert_not_called()
    text = update.message.reply_text.call_args[0][0]
    assert "Usage: /set_party" in text


@pytest.mark.asyncio
@patch("src.bot.telegram.db")
async def test_set_main_too_long_rejected(mock_db: MagicMock) -> None:
    update, context = _make_update(["x" * (HOTLINE_MESSAGE_MAX_CHARS + 1)])

    await cmd_set_main(update, context)

    mock_db.upsert_hotline_message.assert_not_called()
    text = update.message.reply_text.call_args[0][0]
    assert "too long" in text


@pytest.mark.asyncio
@patch("src.bot.telegram.db")
async def test_preview_messages_shows_both_slots(mock_db: MagicMock) -> None:
    mock_db.get_all_hotline_messages.return_value = [
        {
            "slot": "main",
            "body": "Main text",
            "updated_by": "pete",
            "updated_at": "2026-10-01T00:00:00",
        }
    ]
    update, context = _make_update()

    await cmd_preview_messages(update, context)

    kwargs = update.message.reply_text.call_args
    text = kwargs[0][0]
    assert "Main text" in text
    assert "pete" in text
    assert "2026-10-01T00:00:00" in text
    assert "(not set)" in text  # party slot empty


@pytest.mark.asyncio
@patch("src.bot.telegram.db")
async def test_preview_messages_empty(mock_db: MagicMock) -> None:
    mock_db.get_all_hotline_messages.return_value = []
    update, context = _make_update()

    await cmd_preview_messages(update, context)

    text = update.message.reply_text.call_args[0][0]
    assert text.count("(not set)") == 2


def test_removed_commands_are_gone() -> None:
    """Old recommendation/voice-note handlers must not exist."""
    import src.bot.telegram as tg

    for name in (
        "cmd_upcoming",
        "cmd_train",
        "cmd_script",
        "cmd_write",
        "cmd_push",
        "cmd_set_party_voice",
        "cmd_clear_party_voice",
        "cmd_preview_party_voice",
        "handle_feedback",
        "handle_reply",
        "send_daily_recommendations",
        "send_weekly_script_draft",
    ):
        assert not hasattr(tg, name), name
