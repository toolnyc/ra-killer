from __future__ import annotations

import functools
from datetime import date, timedelta
from typing import Callable

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from src import db
from src.config import settings
from src.log import get_logger
from src.models import Event, TasteEntry

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
    app.add_handler(CommandHandler("taste", cmd_taste))
    app.add_handler(CommandHandler("add_artist", cmd_add_artist))
    app.add_handler(CommandHandler("add_venue", cmd_add_venue))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("set_main", cmd_set_main))
    app.add_handler(CommandHandler("set_party", cmd_set_party))
    app.add_handler(CommandHandler("preview_messages", cmd_preview_messages))


@_command_error_handler
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Welcome to Clubstack! NYC event aggregator + hotline.\n\n"
        "Commands:\n"
        "/set_main <text> - Set the press-1 hotline message\n"
        "/set_party <text> - Set the press-2 hotline message\n"
        "/preview_messages - Show current hotline messages\n"
        "/taste - View your taste profile\n"
        "/add_artist <name> - Add a favorite artist\n"
        "/add_venue <name> - Add a favorite venue\n"
        "/status - System status"
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


@_command_error_handler
async def cmd_taste(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    entries = db.get_taste_profile()
    if not entries:
        await update.message.reply_text(
            "No taste profile set. Use /add_artist and /add_venue to get started."
        )
        return

    by_cat: dict[str, list[TasteEntry]] = {}
    for e in entries:
        by_cat.setdefault(e.category, []).append(e)

    max_per_cat = 20
    lines = []
    for cat in ("artist", "venue", "genre", "vibe"):
        items = by_cat.get(cat, [])
        if items:
            sorted_items = sorted(items, key=lambda x: -x.weight)
            shown = sorted_items[:max_per_cat]
            remaining = len(sorted_items) - len(shown)
            lines.append(f"\n<b>{cat.title()}s:</b>")
            for item in shown:
                sign = "+" if item.weight > 0 else ""
                lines.append(f"  {item.name} ({sign}{item.weight:.1f})")
            if remaining > 0:
                lines.append(f"  <i>...and {remaining} more</i>")

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


@_command_error_handler
async def cmd_add_artist(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Usage: /add_artist Honey Dijon")
        return
    name = " ".join(context.args)
    db.upsert_taste_entry(TasteEntry(category="artist", name=name, weight=2.0, source="manual"))
    await update.message.reply_text(f"Added artist: {name}")


@_command_error_handler
async def cmd_add_venue(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Usage: /add_venue Nowadays")
        return
    name = " ".join(context.args)
    db.upsert_taste_entry(TasteEntry(category="venue", name=name, weight=2.0, source="manual"))
    await update.message.reply_text(f"Added venue: {name}")


@_command_error_handler
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Recent scrape logs
    result = (
        db.get_client()
        .table("scrape_logs")
        .select("*")
        .order("created_at", desc=True)
        .limit(12)
        .execute()
    )
    lines = ["<b>Recent Scrapes:</b>"]
    for row in result.data:
        status_emoji = "ok" if row["status"] == "success" else "ERR"
        lines.append(
            f"  [{status_emoji}] {row['source']}: {row['event_count']} events "
            f"({row['duration_seconds']:.1f}s)"
        )

    event_count = len(db.get_upcoming_events())
    lines.append(f"\n<b>Upcoming events:</b> {event_count}")

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


def _format_event(event: Event) -> str:
    """Format an event for Telegram display."""
    artists = ", ".join(event.artists) if event.artists else "TBA"
    time_str = event.start_time.strftime("%I:%M %p").lstrip("0") if event.start_time else "TBA"

    lines = [
        f"<b>{event.title}</b>",
        f"Date: {event.event_date.strftime('%a %b %d')}",
        f"Time: {time_str}",
        f"Venue: {event.venue_name or 'TBA'}",
        f"Artists: {artists}",
    ]
    if event.cost_display:
        lines.append(f"Price: {event.cost_display}")
    if event.attending_count:
        lines.append(f"Attending: {event.attending_count}")

    # Source links
    link_parts = []
    for source, url in (event.source_urls or {}).items():
        link_parts.append(f'<a href="{url}">{source}</a>')
    if link_parts:
        lines.append("Links: " + " | ".join(link_parts))

    return "\n".join(lines)


async def send_weekend_preview() -> None:
    """Send a weekend event preview (Tuesday evening push)."""
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        return

    # Get weekend events (Friday-Sunday)
    today = date.today()
    days_until_friday = (4 - today.weekday()) % 7
    if days_until_friday == 0:
        days_until_friday = 7

    friday = today + timedelta(days=days_until_friday)
    sunday = friday + timedelta(days=2)

    all_events = db.get_upcoming_events(from_date=friday)
    weekend = [e for e in all_events if e.event_date <= sunday]

    if not weekend:
        return

    app = get_app()
    bot = app.bot

    header = f"Weekend Preview ({friday.strftime('%b %d')} - {sunday.strftime('%b %d')})\n"
    header += f"{len(weekend)} events this weekend\n"
    header += "=" * 30

    await bot.send_message(
        chat_id=settings.telegram_chat_id,
        text=header,
    )

    for event in weekend[:15]:
        text = _format_event(event)
        await bot.send_message(
            chat_id=settings.telegram_chat_id,
            text=text,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
