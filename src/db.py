from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta

from supabase import create_client

from src.config import settings
from src.models import Event, Recommendation, ScrapedEvent, TasteEntry
from src.normalize import normalize_artist, normalize_venue

_client = None


def get_client():
    global _client
    if _client is None:
        _client = create_client(settings.supabase_url, settings.supabase_key)
    return _client


def _serialize_event(e: ScrapedEvent) -> dict:
    """Convert ScrapedEvent to a dict suitable for Supabase insert."""
    d = e.model_dump()
    d["event_date"] = d["event_date"].isoformat()
    if d["start_time"]:
        d["start_time"] = d["start_time"].isoformat()
    if d["end_time"]:
        d["end_time"] = d["end_time"].isoformat()
    d["source"] = d["source"].value if hasattr(d["source"], "value") else d["source"]
    d["extra"] = json.dumps(d["extra"]) if d["extra"] else None
    return d


def _serialize_canonical(e: Event) -> dict:
    d = e.model_dump(exclude={"id", "created_at", "updated_at"})
    d["event_date"] = d["event_date"].isoformat()
    if d["start_time"]:
        d["start_time"] = d["start_time"].isoformat()
    if d["end_time"]:
        d["end_time"] = d["end_time"].isoformat()
    d["source_urls"] = json.dumps(d["source_urls"]) if d["source_urls"] else "{}"
    return d


def _parse_time(v: str | None) -> time | None:
    if not v:
        return None
    try:
        return time.fromisoformat(v)
    except (ValueError, TypeError):
        return None


def _parse_date(v: str | None) -> date | None:
    if not v:
        return None
    try:
        return date.fromisoformat(v)
    except (ValueError, TypeError):
        return None


# --- Raw events ---


def upsert_raw_events(events: list[ScrapedEvent]) -> int:
    """Upsert scraped events into raw_events. Returns count upserted."""
    if not events:
        return 0
    rows = [_serialize_event(e) for e in events]
    # Deduplicate within the batch — Postgres ON CONFLICT can't handle
    # the same (source, source_id) appearing twice in one INSERT.
    seen: dict[tuple[str, str], dict] = {}
    for r in rows:
        seen[(r["source"], r["source_id"])] = r
    rows = list(seen.values())
    result = (
        get_client()
        .table("raw_events")
        .upsert(rows, on_conflict="source,source_id")
        .execute()
    )
    return len(result.data)


# --- Canonical events ---


def upsert_canonical_event(event: Event) -> str:
    """Upsert a canonical event. Returns the event id."""
    row = _serialize_canonical(event)
    if event.id:
        result = (
            get_client()
            .table("events")
            .upsert({**row, "id": event.id}, on_conflict="id")
            .execute()
        )
    else:
        result = get_client().table("events").insert(row).execute()
    return result.data[0]["id"]


def get_upcoming_events(from_date: date | None = None) -> list[Event]:
    """Get all canonical events from from_date onwards."""
    if from_date is None:
        from_date = date.today()
    result = (
        get_client()
        .table("events")
        .select("*")
        .gte("event_date", from_date.isoformat())
        .order("event_date")
        .execute()
    )
    events = []
    for row in result.data:
        row["event_date"] = _parse_date(row.get("event_date"))
        row["start_time"] = _parse_time(row.get("start_time"))
        row["end_time"] = _parse_time(row.get("end_time"))
        if isinstance(row.get("source_urls"), str):
            row["source_urls"] = json.loads(row["source_urls"])
        events.append(Event(**row))
    return events


def get_past_events(days_back: int = 60) -> list[Event]:
    """Get canonical events from past N days (for training)."""
    today = date.today()
    since = today - timedelta(days=days_back)
    result = (
        get_client()
        .table("events")
        .select("*")
        .lt("event_date", today.isoformat())
        .gte("event_date", since.isoformat())
        .order("event_date", desc=True)
        .execute()
    )
    events = []
    for row in result.data:
        row["event_date"] = _parse_date(row.get("event_date"))
        row["start_time"] = _parse_time(row.get("start_time"))
        row["end_time"] = _parse_time(row.get("end_time"))
        if isinstance(row.get("source_urls"), str):
            row["source_urls"] = json.loads(row["source_urls"])
        events.append(Event(**row))
    return events


def get_canonical_events_by_date_venue(
    event_date: date, venue_name: str | None
) -> list[Event]:
    """Fetch canonical events for a given date + venue (for dedup)."""
    q = (
        get_client()
        .table("events")
        .select("*")
        .eq("event_date", event_date.isoformat())
    )
    if venue_name:
        q = q.eq("venue_name", venue_name)
    result = q.execute()
    events = []
    for row in result.data:
        row["event_date"] = _parse_date(row.get("event_date"))
        row["start_time"] = _parse_time(row.get("start_time"))
        row["end_time"] = _parse_time(row.get("end_time"))
        if isinstance(row.get("source_urls"), str):
            row["source_urls"] = json.loads(row["source_urls"])
        events.append(Event(**row))
    return events


# --- Taste profile ---


def get_taste_profile() -> list[TasteEntry]:
    result = get_client().table("taste_profile").select("*").execute()
    return [TasteEntry(**row) for row in result.data]


def upsert_taste_entry(entry: TasteEntry) -> None:
    row = entry.model_dump(exclude={"id"})
    if entry.category == "artist":
        row["name"] = normalize_artist(row["name"])
    elif entry.category == "venue":
        row["name"] = normalize_venue(row["name"])
    get_client().table("taste_profile").upsert(
        row, on_conflict="category,name"
    ).execute()


def update_taste_weight(category: str, name: str, delta: float) -> None:
    """Adjust a taste entry's weight by delta, clamped to [-1, 3]."""
    if category == "artist":
        name = normalize_artist(name)
    elif category == "venue":
        name = normalize_venue(name)
    entries = (
        get_client()
        .table("taste_profile")
        .select("*")
        .eq("category", category)
        .eq("name", name)
        .execute()
    )
    if entries.data:
        current = entries.data[0]["weight"]
        new_weight = max(-1.0, min(3.0, current + delta))
        (
            get_client()
            .table("taste_profile")
            .update({"weight": new_weight})
            .eq("id", entries.data[0]["id"])
            .execute()
        )
    else:
        upsert_taste_entry(
            TasteEntry(
                category=category,
                name=name,
                weight=max(-1.0, min(3.0, delta)),
                source="learned",
            )
        )


# --- Recommendations ---


def save_recommendation(rec: Recommendation) -> str:
    row = rec.model_dump(exclude={"id", "created_at"})
    result = get_client().table("recommendations").insert(row).execute()
    return result.data[0]["id"]


def update_recommendation_feedback(rec_id: str, feedback: str) -> None:
    get_client().table("recommendations").update({"feedback": feedback}).eq(
        "id", rec_id
    ).execute()


def update_recommendation_message_id(rec_id: str, message_id: int) -> None:
    get_client().table("recommendations").update(
        {"telegram_message_id": message_id}
    ).eq("id", rec_id).execute()


def get_recommended_event_ids() -> set[str]:
    """Get event IDs that already have recommendations."""
    result = (
        get_client()
        .table("recommendations")
        .select("event_id")
        .execute()
    )
    return {row["event_id"] for row in result.data}


def get_recommendation_by_message_id(message_id: int) -> dict | None:
    result = (
        get_client()
        .table("recommendations")
        .select("*, events(*)")
        .eq("telegram_message_id", message_id)
        .execute()
    )
    return result.data[0] if result.data else None


def get_recent_recommendations(limit: int = 50) -> list[dict]:
    result = (
        get_client()
        .table("recommendations")
        .select("*, events(*)")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data


def get_week_recommendations() -> list[dict]:
    """Get recommendations for events this week (for Twilio IVR)."""
    today = date.today()
    week_end = today + timedelta(days=7)
    result = (
        get_client()
        .table("recommendations")
        .select("*, events(*)")
        .order("score", desc=True)
        .limit(100)
        .execute()
    )
    # Filter in Python — PostgREST embedded resource filters (events.event_date)
    # don't work as WHERE clauses on the join.
    recs = []
    for r in result.data:
        ev = r.get("events")
        if not ev:
            continue
        ev_date = ev.get("event_date", "")
        if today.isoformat() <= ev_date <= week_end.isoformat():
            recs.append(r)
    return recs[:20]


# --- Scrape logs ---


def log_scrape(
    source: str,
    status: str,
    event_count: int,
    duration_seconds: float,
    error: str | None = None,
) -> None:
    get_client().table("scrape_logs").insert(
        {
            "source": source,
            "status": status,
            "event_count": event_count,
            "duration_seconds": duration_seconds,
            "error": error,
        }
    ).execute()


# --- Alert log ---


def should_alert(source: str) -> bool:
    """Check if we should send an alert (rate limit: 1 per source per hour)."""
    result = (
        get_client()
        .table("alert_log")
        .select("created_at")
        .eq("source", source)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not result.data:
        return True
    last = datetime.fromisoformat(result.data[0]["created_at"].replace("Z", "+00:00"))
    return (datetime.now(last.tzinfo) - last).total_seconds() > 3600


def log_alert(source: str, message: str) -> None:
    get_client().table("alert_log").insert(
        {"source": source, "message": message}
    ).execute()


# --- Cleanup ---


def delete_past_events(before_date: date) -> int:
    """Delete events before a given date. Returns count deleted."""
    result = (
        get_client()
        .table("events")
        .delete()
        .lt("event_date", before_date.isoformat())
        .execute()
    )
    return len(result.data)
