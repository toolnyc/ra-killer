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
    MessageHandler,
    filters,
)

from src import db
from src.config import settings
from src.log import get_logger
from src.models import Event, Recommendation, TasteEntry, WeeklyScript
from src.recommend.ranker import run_recommendation_pipeline, run_training_pipeline
from src.recommend.script_writer import apply_script_edits, generate_weekly_script

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
    app.add_handler(CommandHandler("script", cmd_script))
    app.add_handler(CommandHandler("write", cmd_write))
    app.add_handler(CommandHandler("push", cmd_push))
    app.add_handler(CallbackQueryHandler(handle_feedback))
    app.add_handler(MessageHandler(filters.REPLY & ~filters.COMMAND, handle_reply))


@_command_error_handler
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Welcome to Clubstack! NYC event recommendations.\n\n"
        "Commands:\n"
        "/upcoming - Top upcoming events\n"
        "/taste - View your taste profile\n"
        "/add_artist <name> - Add a favorite artist\n"
        "/add_venue <name> - Add a favorite venue\n"
        "/train [N] - Score N past events for taste training\n"
        "/script - Generate/view weekly IVR script\n"
        "/write <text> - Hand-write an IVR script\n"
        "/push - Push approved script to the hotline\n"
        "/status - System status"
    )


@_command_error_handler
async def cmd_upcoming(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    week_cutoff = date.today() + timedelta(days=7)

    # Try taste-ranked recommendations first
    recs = db.get_week_recommendations()

    if not recs:
        # No recs in DB — run the pipeline on-demand
        status_msg = await update.message.reply_text("Scoring upcoming events...")
        pipeline_recs = await run_recommendation_pipeline(top_n=10)
        recs = db.get_week_recommendations() if pipeline_recs else []
        try:
            await status_msg.delete()
        except Exception:
            pass

    # Build map of upcoming events within 7-day window
    all_events = db.get_upcoming_events()
    events_map = {e.id: e for e in all_events if e.event_date <= week_cutoff}

    sent = 0
    for r in recs:
        event = events_map.pop(r.get("event_id"), None)
        if not event:
            continue
        rec = Recommendation(
            id=r["id"],
            event_id=r["event_id"],
            score=r.get("score", 0),
            reasoning=r.get("reasoning", ""),
        )
        text, keyboard = _format_recommendation(rec, event)
        await update.message.reply_text(
            text, parse_mode="HTML", reply_markup=keyboard, disable_web_page_preview=True
        )
        sent += 1
        if sent >= 10:
            break

    # Fill remaining slots with unscored events (still within 7 days)
    if sent < 10:
        for event in list(events_map.values())[:10 - sent]:
            text = _format_event(event)
            await update.message.reply_text(text, parse_mode="HTML", disable_web_page_preview=True)
            sent += 1

    if sent == 0:
        await update.message.reply_text("No upcoming events found.")


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
    """Handle inline keyboard feedback (Going/Pass and script approve/regen)."""
    query = update.callback_query

    data = query.data
    if ":" not in data:
        await query.answer()
        return

    action, target_id = data.split(":", 1)

    # --- Script callbacks ---
    if action == "script_approve":
        await query.answer("Approved!")
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        try:
            db.approve_weekly_script(target_id)
            await query.message.reply_text(
                "Script approved! Use /push to make it live on the hotline."
            )
        except Exception:
            logger.exception("script_approve_failed", script_id=target_id)
            await query.message.reply_text("Failed to approve script.")
        return

    if action == "script_regen":
        await query.answer("Regenerating...")
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        await send_weekly_script_draft(chat_id=query.message.chat_id)
        return

    # --- Recommendation feedback ---
    rec_id = target_id
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


@_command_error_handler
async def cmd_script(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Generate a weekly IVR script draft, or show the current approved one."""
    if context.args and context.args[0].lower() == "current":
        from src.recommend.script_writer import _monday_of_week

        week_start = _monday_of_week(date.today())
        # Show published (live) script first, fall back to approved
        script = db.get_published_script(week_start)
        label = "Live"
        if not script:
            script = db.get_latest_approved_script(week_start)
            label = "Approved (not yet pushed)"
        if script:
            await update.message.reply_text(
                f"<b>{label} script (week of {script.week_start}):</b>\n\n{script.script_text}",
                parse_mode="HTML",
            )
        else:
            await update.message.reply_text("No script for this week. Use /script to generate one.")
        return

    status_msg = await update.message.reply_text("Generating weekly script draft...")
    await send_weekly_script_draft(chat_id=update.message.chat_id, status_msg=status_msg)


@_command_error_handler
async def cmd_write(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Hand-write an IVR script and save as draft."""
    from src.recommend.script_writer import _monday_of_week

    if not context.args:
        await update.message.reply_text("Usage: /write Hey, you've reached Clubstack...")
        return

    script_text = " ".join(context.args)
    week_start = _monday_of_week(date.today())
    script = WeeklyScript(
        week_start=week_start,
        status="draft",
        script_text=script_text,
        source_event_ids=[],
    )
    script_id = db.save_weekly_script(script)

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Approve", callback_data=f"script_approve:{script_id}"),
                InlineKeyboardButton("Regenerate", callback_data=f"script_regen:{script_id}"),
            ]
        ]
    )

    text = f"<b>Manual Script Draft</b> (week of {week_start})\n\n{script_text}"
    if len(text) > 4096:
        text = text[:4090] + "..."

    msg = await update.message.reply_text(
        text, parse_mode="HTML", reply_markup=keyboard
    )
    db.update_weekly_script_message_id(script_id, msg.message_id)


@_command_error_handler
async def cmd_push(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Push the approved script to the IVR hotline (make it live)."""
    from src.recommend.script_writer import _monday_of_week

    week_start = _monday_of_week(date.today())
    script = db.get_latest_approved_script(week_start)
    if not script:
        await update.message.reply_text(
            "No approved script to push. Generate and approve one first with /script."
        )
        return

    db.publish_weekly_script(script.id)
    await update.message.reply_text(
        f"Script pushed! It's now live on the hotline (week of {script.week_start})."
    )
    logger.info("script_pushed_to_ivr", script_id=script.id, week_start=str(script.week_start))


async def send_weekly_script_draft(chat_id: str | int | None = None, status_msg=None) -> None:
    """Generate a draft script and send it to Telegram with Approve/Regenerate buttons."""
    if chat_id is None:
        chat_id = settings.telegram_chat_id
    if not settings.telegram_bot_token or not chat_id:
        logger.warning("telegram_not_configured")
        return

    script = await generate_weekly_script()
    script_id = db.save_weekly_script(script)
    script.id = script_id

    app = get_app()
    bot = app.bot

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Approve", callback_data=f"script_approve:{script_id}"),
                InlineKeyboardButton("Regenerate", callback_data=f"script_regen:{script_id}"),
            ]
        ]
    )

    text = f"<b>Weekly Script Draft</b> (week of {script.week_start})\n\n{script.script_text}"
    # Telegram message limit is 4096 chars
    if len(text) > 4096:
        text = text[:4090] + "..."

    msg = await bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode="HTML",
        reply_markup=keyboard,
    )

    db.update_weekly_script_message_id(script_id, msg.message_id)

    if status_msg:
        try:
            await status_msg.edit_text("Draft generated! Review below and reply to edit, or tap Approve.")
        except Exception:
            pass

    logger.info("weekly_script_draft_sent", script_id=script_id)


async def handle_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle replies to draft script messages — apply edits via Claude."""
    if not update.message or not update.message.reply_to_message:
        return

    reply_to_id = update.message.reply_to_message.message_id
    script = db.get_draft_script_by_message_id(reply_to_id)
    if not script:
        return  # Not a reply to a script draft

    instructions = update.message.text
    if not instructions:
        return

    status_msg = await update.message.reply_text("Applying edits...")

    try:
        new_text = await apply_script_edits(script.script_text, instructions)
        db.update_weekly_script_text(script.id, new_text)

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("Approve", callback_data=f"script_approve:{script.id}"),
                    InlineKeyboardButton("Regenerate", callback_data=f"script_regen:{script.id}"),
                ]
            ]
        )

        text = f"<b>Updated Script Draft</b>\n\n{new_text}"
        if len(text) > 4096:
            text = text[:4090] + "..."

        msg = await update.message.chat.send_message(
            text=text,
            parse_mode="HTML",
            reply_markup=keyboard,
        )
        db.update_weekly_script_message_id(script.id, msg.message_id)
        await status_msg.edit_text("Edits applied! Review the updated draft above.")
    except Exception:
        logger.exception("script_edit_failed")
        await status_msg.edit_text("Failed to apply edits. Try again.")


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
