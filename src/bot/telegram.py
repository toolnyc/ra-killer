from __future__ import annotations

import functools
from datetime import date, timedelta
from typing import Callable

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from src import db
from src.config import settings
from src.log import get_logger
from src.models import Event, Recommendation, TasteEntry
from src.recommend.ranker import run_recommendation_pipeline, run_training_pipeline

logger = get_logger("telegram")


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
    app.add_handler(CommandHandler("upcoming", cmd_upcoming))
    app.add_handler(CommandHandler("taste", cmd_taste))
    app.add_handler(CommandHandler("add_artist", cmd_add_artist))
    app.add_handler(CommandHandler("add_venue", cmd_add_venue))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("train", cmd_train))
    app.add_handler(CallbackQueryHandler(handle_feedback))


@_command_error_handler
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Welcome to ra-killer! NYC event recommendations.\n\n"
        "Commands:\n"
        "/upcoming - Top upcoming events\n"
        "/taste - View your taste profile\n"
        "/add_artist <name> - Add a favorite artist\n"
        "/add_venue <name> - Add a favorite venue\n"
        "/train [N] - Score N past events for taste training\n"
        "/status - System status"
    )


@_command_error_handler
async def cmd_upcoming(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    events = db.get_upcoming_events()
    if not events:
        await update.message.reply_text("No upcoming events found.")
        return

    # Show top 10 by date
    for event in events[:10]:
        text = _format_event(event)
        await update.message.reply_text(text, parse_mode="HTML", disable_web_page_preview=True)


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

    lines = []
    for cat in ("artist", "venue"):
        items = by_cat.get(cat, [])
        if items:
            lines.append(f"\n<b>{cat.title()}s:</b>")
            for item in sorted(items, key=lambda x: -x.weight):
                sign = "+" if item.weight > 0 else ""
                lines.append(f"  {item.name} ({sign}{item.weight:.1f})")

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


@_command_error_handler
async def cmd_train(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Score past events for taste training with Going/Pass feedback."""
    top_n = 10
    if context.args:
        try:
            top_n = int(context.args[0])
            top_n = max(1, min(top_n, 50))
        except ValueError:
            await update.message.reply_text("Usage: /train [number] (e.g. /train 15)")
            return

    status_msg = await update.message.reply_text(f"Scoring {top_n} past events...")

    recs = await run_training_pipeline(top_n=top_n)
    if not recs:
        await status_msg.edit_text("No past events to score (all may already be rated).")
        return

    events_map = {e.id: e for e in db.get_past_events()}

    sent = 0
    for rec in recs:
        event = events_map.get(rec.event_id)
        if not event:
            continue

        text, keyboard = _format_recommendation(rec, event)
        msg = await update.message.chat.send_message(
            text=text,
            parse_mode="HTML",
            reply_markup=keyboard,
            disable_web_page_preview=True,
        )
        db.update_recommendation_message_id(rec.id, msg.message_id)
        sent += 1

    await status_msg.edit_text(f"Sent {sent} past events for training. Tap Going/Pass to refine your taste!")


async def handle_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline keyboard feedback (Going/Pass)."""
    query = update.callback_query

    data = query.data  # format: "approve:rec_id" or "reject:rec_id"
    if ":" not in data:
        await query.answer()
        return

    action, rec_id = data.split(":", 1)
    if action not in ("approve", "reject"):
        await query.answer()
        return

    # Check if already processed (idempotency guard for duplicate callbacks)
    rec_data = db.get_recommendation_by_message_id(query.message.message_id)
    if rec_data and rec_data.get("feedback"):
        await query.answer("Already recorded!")
        # Ensure buttons are removed even on duplicate
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass  # Already removed by the first callback
        return

    label = "Going!" if action == "approve" else "Pass"

    # Remove buttons immediately to prevent double-clicks
    await query.answer(label)
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass  # Race: another callback already removed it

    # Persist feedback and update taste weights
    try:
        db.update_recommendation_feedback(rec_id, action)

        if rec_data and rec_data.get("events"):
            ev = rec_data["events"]
            delta = 0.1 if action == "approve" else -0.1

            for artist in ev.get("artists") or []:
                db.update_taste_weight("artist", artist, delta)

            if ev.get("venue_name"):
                db.update_taste_weight("venue", ev["venue_name"], delta)
    except Exception:
        logger.exception("feedback_processing_failed", rec_id=rec_id, action=action)

    await query.message.reply_text(f"Marked as: {label}")


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


def _format_recommendation(rec: Recommendation, event: Event) -> tuple[str, InlineKeyboardMarkup]:
    """Format a recommendation with inline keyboard."""
    text = _format_event(event)
    text += f"\n\nScore: {rec.score:.0f}/100"
    if rec.reasoning:
        text += f"\n{rec.reasoning}"

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Going", callback_data=f"approve:{rec.id}"),
                InlineKeyboardButton("Pass", callback_data=f"reject:{rec.id}"),
            ]
        ]
    )

    return text, keyboard


async def send_daily_recommendations(top_n: int = 10) -> None:
    """Run recommendation pipeline and send results to Telegram."""
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        logger.warning("telegram_not_configured")
        return

    recs = await run_recommendation_pipeline(top_n=top_n)
    if not recs:
        logger.info("no_recommendations_to_send")
        return

    app = get_app()
    bot = app.bot

    events_map = {e.id: e for e in db.get_upcoming_events()}

    for rec in recs:
        event = events_map.get(rec.event_id)
        if not event:
            continue

        text, keyboard = _format_recommendation(rec, event)
        msg = await bot.send_message(
            chat_id=settings.telegram_chat_id,
            text=text,
            parse_mode="HTML",
            reply_markup=keyboard,
            disable_web_page_preview=True,
        )

        # Store message ID for feedback tracking
        db.update_recommendation_message_id(rec.id, msg.message_id)

    logger.info("daily_recs_sent", count=len(recs))


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
