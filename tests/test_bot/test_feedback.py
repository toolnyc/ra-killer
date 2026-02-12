"""Tests for Telegram callback feedback handler (duplicate/idempotency)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.bot.telegram import handle_feedback


def _make_update(callback_data: str, message_id: int = 42) -> MagicMock:
    """Build a minimal mock Update with a callback query."""
    update = MagicMock()
    query = AsyncMock()
    query.data = callback_data
    query.message.message_id = message_id
    query.message.reply_text = AsyncMock()
    query.answer = AsyncMock()
    query.edit_message_reply_markup = AsyncMock()
    update.callback_query = query
    return update


@pytest.mark.asyncio
@patch("src.bot.telegram.db")
async def test_first_callback_processes_normally(mock_db: MagicMock) -> None:
    """First button press should record feedback and update taste."""
    mock_db.get_recommendation_by_message_id.return_value = {
        "feedback": None,
        "events": {"artists": ["DJ Test"], "venue_name": "Basement"},
    }

    update = _make_update("approve:rec-123")
    await handle_feedback(update, MagicMock())

    query = update.callback_query
    query.answer.assert_called_once_with("Going!")
    query.edit_message_reply_markup.assert_called_once_with(reply_markup=None)
    mock_db.update_recommendation_feedback.assert_called_once_with("rec-123", "approve")
    mock_db.update_taste_weight.assert_any_call("artist", "DJ Test", 0.1)
    mock_db.update_taste_weight.assert_any_call("venue", "Basement", 0.1)
    query.message.reply_text.assert_called_once_with("Marked as: Going!")


@pytest.mark.asyncio
@patch("src.bot.telegram.db")
async def test_duplicate_callback_is_rejected(mock_db: MagicMock) -> None:
    """Second button press (already has feedback) should be a no-op."""
    mock_db.get_recommendation_by_message_id.return_value = {
        "feedback": "approve",
        "events": {"artists": ["DJ Test"], "venue_name": "Basement"},
    }

    update = _make_update("approve:rec-123")
    await handle_feedback(update, MagicMock())

    query = update.callback_query
    query.answer.assert_called_once_with("Already recorded!")
    mock_db.update_recommendation_feedback.assert_not_called()
    mock_db.update_taste_weight.assert_not_called()
    query.message.reply_text.assert_not_called()


@pytest.mark.asyncio
@patch("src.bot.telegram.db")
async def test_reject_callback(mock_db: MagicMock) -> None:
    """Reject (Pass) should apply negative taste delta."""
    mock_db.get_recommendation_by_message_id.return_value = {
        "feedback": None,
        "events": {"artists": ["Artist A"], "venue_name": "Venue X"},
    }

    update = _make_update("reject:rec-456")
    await handle_feedback(update, MagicMock())

    mock_db.update_recommendation_feedback.assert_called_once_with("rec-456", "reject")
    mock_db.update_taste_weight.assert_any_call("artist", "Artist A", -0.1)
    mock_db.update_taste_weight.assert_any_call("venue", "Venue X", -0.1)
    update.callback_query.message.reply_text.assert_called_once_with("Marked as: Pass")


@pytest.mark.asyncio
@patch("src.bot.telegram.db")
async def test_invalid_callback_data_ignored(mock_db: MagicMock) -> None:
    """Callback with no colon separator should be silently ignored."""
    update = _make_update("garbage")
    await handle_feedback(update, MagicMock())

    mock_db.update_recommendation_feedback.assert_not_called()


@pytest.mark.asyncio
@patch("src.bot.telegram.db")
async def test_unknown_action_ignored(mock_db: MagicMock) -> None:
    """Callback with an unknown action should be ignored."""
    update = _make_update("delete:rec-789")
    await handle_feedback(update, MagicMock())

    mock_db.update_recommendation_feedback.assert_not_called()


@pytest.mark.asyncio
@patch("src.bot.telegram.db")
async def test_db_error_does_not_crash(mock_db: MagicMock) -> None:
    """DB failure during feedback should not raise to the caller."""
    mock_db.get_recommendation_by_message_id.return_value = {
        "feedback": None,
        "events": {"artists": ["X"], "venue_name": "Y"},
    }
    mock_db.update_recommendation_feedback.side_effect = Exception("DB down")

    update = _make_update("approve:rec-err")
    await handle_feedback(update, MagicMock())

    # Buttons should already be removed, confirmation still sent
    query = update.callback_query
    query.edit_message_reply_markup.assert_called_once_with(reply_markup=None)
    query.message.reply_text.assert_called_once_with("Marked as: Going!")
