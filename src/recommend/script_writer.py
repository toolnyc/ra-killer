from __future__ import annotations

import json
from datetime import date, timedelta

import anthropic

from src import db
from src.config import settings
from src.log import get_logger
from src.models import Event, WeeklyScript

logger = get_logger("script_writer")


def _monday_of_week(d: date) -> date:
    """Return the Monday of the week containing date d."""
    return d - timedelta(days=d.weekday())


def _gather_events_for_script() -> tuple[list[tuple[Event, str]], list[tuple[Event, str]]]:
    """Gather "Going" events and top-scored recs for this week.

    Returns (going_events, top_rec_events) where each item is (Event, reasoning).
    """
    recs = db.get_week_recommendations()

    going: list[tuple[Event, str]] = []
    top_recs: list[tuple[Event, str]] = []

    events_map = {e.id: e for e in db.get_upcoming_events()}

    for r in recs:
        ev = events_map.get(r.get("event_id"))
        if not ev:
            continue
        reasoning = r.get("reasoning", "")
        if r.get("feedback") == "approve":
            going.append((ev, reasoning))
        elif r.get("score", 0) >= 50:
            top_recs.append((ev, reasoning))

    return going, top_recs[:10]


def _build_event_block(events: list[tuple[Event, str]], label: str) -> str:
    """Format events into a text block for the Claude prompt.

    Each item is (Event, reasoning_text).
    """
    if not events:
        return f"## {label}\nNone this week.\n"

    lines = [f"## {label}"]
    for e, reasoning in events:
        artists = ", ".join(e.artists) if e.artists else "TBA"
        day = e.event_date.strftime("%A %b %d")
        time_str = e.start_time.strftime("%I:%M %p").lstrip("0") if e.start_time else ""
        venue = e.venue_name or "TBA"
        lines.append(f"- {e.title} | {artists} | {venue} | {day} {time_str}")
        if reasoning:
            lines.append(f"  Why: {reasoning}")
    return "\n".join(lines)


async def generate_weekly_script(
    going: list[tuple[Event, str]] | None = None,
    top_recs: list[tuple[Event, str]] | None = None,
) -> WeeklyScript:
    """Generate a DJ-style weekly script from going events + top recs.

    Each item is (Event, reasoning_text).
    If going/top_recs are not provided, gathers them from the DB.
    Returns a WeeklyScript (draft, not yet saved).
    """
    if going is None or top_recs is None:
        going, top_recs = _gather_events_for_script()

    all_events = going + top_recs
    source_ids = [e.id for e, _ in all_events if e.id]

    # No events at all — return a short "nothing this week" script
    if not all_events:
        week_start = _monday_of_week(date.today())
        return WeeklyScript(
            week_start=week_start,
            status="draft",
            script_text="No recommendations this week.",
            source_event_ids=[],
        )

    going_block = _build_event_block(going, "Confirmed Going")
    recs_block = _build_event_block(top_recs, "Top Recommendations")

    prompt = f"""You are the host of "Clubstack" — a weekly NYC nightlife hotline. Write a short voicemail script for callers.

{going_block}

{recs_block}

Guidelines:
- One-line intro, then get to the events
- For each event: who's playing, where, when, how much. One or two sentences max.
- Group by night (Thursday, Friday, Saturday, Sunday)
- Short sign-off
- Keep it natural for text-to-speech (spell out abbreviations, no weird punctuation)
- Aim for 200-300 words total
- Write ONLY the script text, no stage directions or metadata"""

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    try:
        response = client.messages.create(
            model=settings.claude_model,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        script_text = response.content[0].text.strip()
    except Exception as e:
        logger.error("script_generation_failed", error=str(e))
        script_text = "Script generation failed. Please try again with /script."

    week_start = _monday_of_week(date.today())

    return WeeklyScript(
        week_start=week_start,
        status="draft",
        script_text=script_text,
        source_event_ids=source_ids,
    )


async def apply_script_edits(current_text: str, instructions: str) -> str:
    """Apply user's edit instructions to the current script via Claude.

    Returns the updated script text.
    """
    prompt = f"""Here is the current weekly script for an NYC nightlife phone hotline:

---
{current_text}
---

The editor wants these changes:
{instructions}

Rewrite the script incorporating the requested changes. Keep the same overall tone and structure unless told otherwise. Return ONLY the updated script text, nothing else."""

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    try:
        response = client.messages.create(
            model=settings.claude_model,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()
    except Exception as e:
        logger.error("script_edit_failed", error=str(e))
        raise
