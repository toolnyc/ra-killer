from __future__ import annotations

from src.models import Event, Recommendation


def event_to_tts_script(event: Event, rec: Recommendation | None = None) -> str:
    """Convert an event + recommendation to a TTS-friendly script."""
    artists = " and ".join(event.artists) if event.artists else "lineup to be announced"
    venue = event.venue_name or "venue to be announced"
    date_str = event.event_date.strftime("%A, %B %d")

    time_str = ""
    if event.start_time:
        time_str = f" starting at {event.start_time.strftime('%I:%M %p').lstrip('0')}"

    price_str = ""
    if event.cost_display:
        price_str = f" Tickets are {event.cost_display}."

    attending_str = ""
    if event.attending_count and event.attending_count > 50:
        attending_str = f" {event.attending_count} people attending."

    reasoning_str = ""
    if rec and rec.reasoning:
        reasoning_str = f" {rec.reasoning}"

    script = (
        f"{event.title}. "
        f"Featuring {artists} at {venue} on {date_str}{time_str}."
        f"{price_str}{attending_str}{reasoning_str}"
    )

    return script


def build_week_tts_script(events_and_recs: list[tuple[Event, Recommendation]]) -> str:
    """Build a full TTS script for the week's recommended events."""
    if not events_and_recs:
        return "No recommended events this week. Check back later."

    lines = [
        f"Here are your top {len(events_and_recs)} recommended events for this week.",
        "",
    ]

    for i, (event, rec) in enumerate(events_and_recs, 1):
        lines.append(f"Number {i}.")
        lines.append(event_to_tts_script(event, rec))
        lines.append("")  # pause between events

    lines.append("That's all for this week. Have a great time out there!")
    return " ".join(lines)
