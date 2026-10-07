from __future__ import annotations

import functools
from typing import Callable

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from src import db
from src.config import settings
from src.log import get_logger

logger = get_logger("telegram")

# Comfortable margin under Twilio <Say> limits
HOTLINE_MESSAGE_MAX_CHARS = 1500


def _command_error_handler(func: Callable) -> Callable:
    """Decorator that catches exceptions in command handlers, logs them, and replies."""

    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        try:
            return await func(update, context)
        except Exception:
            logger.exception("command_error", command=func.__name__)
            if update.message:
                await update.message.reply_text(
                    "Something went wrong. Please try again later."
                )

    return wrapper

_app: Application | None = None


def get_app() -> Application:
    global _app
    if _app is None:
        _app = Application.builder().token(settings.telegram_bot_token).build()
        _register_handlers(_app)
    return _app


def _register_handlers(app: Application) -> None:
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("set_main", cmd_set_main))
    app.add_handler(CommandHandler("set_party", cmd_set_party))
    app.add_handler(CommandHandler("preview_messages", cmd_preview_messages))


@_command_error_handler
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Welcome to Clubstack! NYC dancefloor hotline.\n\n"
        "Commands:\n"
        "/set_main <text> - Set the press-1 hotline message\n"
        "/set_party <text> - Set the press-2 hotline message\n"
        "/preview_messages - Show current hotline messages"
    )


def _set_hotline_message(slot: str, slot_label: str):
    """Build a command handler that stores a hotline message for a slot."""

    @_command_error_handler
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not context.args:
            await update.message.reply_text(f"Usage: /set_{slot} <text>")
            return
        body = " ".join(context.args)
        if len(body) > HOTLINE_MESSAGE_MAX_CHARS:
            await update.message.reply_text(
                f"Message too long ({len(body)} chars). Max is {HOTLINE_MESSAGE_MAX_CHARS}."
            )
            return
        username = update.message.from_user.username or str(update.message.from_user.id)
        db.upsert_hotline_message(slot, body, updated_by=username)
        await update.message.reply_text(
            f"{slot_label} message updated. Callers pressing it will now hear:\n\n{body}"
        )
        logger.info("hotline_message_updated", slot=slot, updated_by=username)

    return handler


cmd_set_main = _set_hotline_message("main", "Main (press 1)")
cmd_set_party = _set_hotline_message("party", "Party (press 2)")


@_command_error_handler
async def cmd_preview_messages(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    messages = {row["slot"]: row for row in db.get_all_hotline_messages()}
    labels = {"main": "Main (press 1)", "party": "Party (press 2)"}

    parts = []
    for slot in ("main", "party"):
        row = messages.get(slot)
        if row:
            parts.append(
                f"<b>{labels[slot]}:</b>\n{row['body']}\n"
                f"<i>updated {row.get('updated_at', 'unknown')} "
                f"by {row.get('updated_by') or 'unknown'}</i>"
            )
        else:
            parts.append(f"<b>{labels[slot]}:</b>\n<i>(not set)</i>")

    await update.message.reply_text("\n\n".join(parts), parse_mode="HTML")
