from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta

from supabase import create_client

from src.config import settings
from src.log import get_logger
from src.models import Event, Recommendation, ScrapedEvent, TasteEntry, WeeklyScript
from src.normalize import normalize_artist, normalize_venue

logger = get_logger(__name__)

_client = None


def get_client():
    global _client
    if _client is None:
        _client = create_client(settings.supabase_url, settings.supabase_key)
    return _client


def ensure_party_voice_table_exists() -> None:
    """Ensure the party_voice_note table exists in Supabase.
    
    If table doesn't exist, logs instructions for manual creation.
    """
    try:
        # Try to read from the table - if it doesn't exist, this will fail
        get_client().table("party_voice_note").select("*").limit(1).execute()
        logger.debug("party_voice_table_exists")
    except Exception as e:
        # Table doesn't exist - log the SQL needed for manual creation
        error_msg = str(e).lower()
        if "could not find" in error_msg or "relation" in error_msg or "does not exist" in error_msg or "not found" in error_msg:
            logger.warning("party_voice_table_missing", 
                         instructions="Create table in Supabase dashboard with: CREATE TABLE party_voice_note (id BIGINT PRIMARY KEY DEFAULT 1, media_url TEXT NOT NULL, updated_by TEXT, updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(), created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(), CONSTRAINT party_voice_note_single_row CHECK (id = 1));")
        else:
            # Some other error, re-raise it
            raise


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


# --- Weekly scripts ---


def save_weekly_script(script: WeeklyScript) -> str:
    """Insert a draft weekly script. Returns the script id."""
    row = {
        "week_start": script.week_start.isoformat(),
        "status": script.status,
        "script_text": script.script_text,
        "source_event_ids": script.source_event_ids,
    }
    result = get_client().table("weekly_scripts").insert(row).execute()
    return result.data[0]["id"]


def get_latest_approved_script(week_start: date) -> WeeklyScript | None:
    """Get the latest approved (not yet published) script for a given week."""
    result = (
        get_client()
        .table("weekly_scripts")
        .select("*")
        .eq("week_start", week_start.isoformat())
        .eq("status", "approved")
        .order("approved_at", desc=True)
        .limit(1)
        .execute()
    )
    if not result.data:
        return None
    row = result.data[0]
    row["week_start"] = _parse_date(row.get("week_start"))
    return WeeklyScript(**row)


def get_published_script(week_start: date) -> WeeklyScript | None:
    """Get the published (live on IVR) script for a given week."""
    result = (
        get_client()
        .table("weekly_scripts")
        .select("*")
        .eq("week_start", week_start.isoformat())
        .eq("status", "published")
        .order("approved_at", desc=True)
        .limit(1)
        .execute()
    )
    if not result.data:
        return None
    row = result.data[0]
    row["week_start"] = _parse_date(row.get("week_start"))
    return WeeklyScript(**row)


def publish_weekly_script(script_id: str) -> None:
    """Mark an approved script as published (live on IVR)."""
    result = (
        get_client()
        .table("weekly_scripts")
        .select("*")
        .eq("id", script_id)
        .execute()
    )
    if not result.data:
        return

    week_start = result.data[0]["week_start"]

    # Supersede any previously published scripts for this week
    (
        get_client()
        .table("weekly_scripts")
        .update({"status": "superseded"})
        .eq("week_start", week_start)
        .eq("status", "published")
        .execute()
    )

    # Publish this one
    (
        get_client()
        .table("weekly_scripts")
        .update({"status": "published"})
        .eq("id", script_id)
        .execute()
    )


def get_draft_script_by_message_id(message_id: int) -> WeeklyScript | None:
    """Find a draft script by its Telegram message ID (for reply detection)."""
    result = (
        get_client()
        .table("weekly_scripts")
        .select("*")
        .eq("telegram_message_id", message_id)
        .eq("status", "draft")
        .execute()
    )
    if not result.data:
        return None
    row = result.data[0]
    row["week_start"] = _parse_date(row.get("week_start"))
    return WeeklyScript(**row)


def approve_weekly_script(script_id: str) -> None:
    """Mark a script as approved and supersede any previous approved scripts for the same week."""
    # Get the script to find its week_start
    result = (
        get_client()
        .table("weekly_scripts")
        .select("*")
        .eq("id", script_id)
        .execute()
    )
    if not result.data:
        return

    week_start = result.data[0]["week_start"]

    # Supersede existing approved scripts for this week
    (
        get_client()
        .table("weekly_scripts")
        .update({"status": "superseded"})
        .eq("week_start", week_start)
        .eq("status", "approved")
        .execute()
    )

    # Approve this one
    (
        get_client()
        .table("weekly_scripts")
        .update({"status": "approved", "approved_at": datetime.utcnow().isoformat()})
        .eq("id", script_id)
        .execute()
    )


def update_weekly_script_text(script_id: str, new_text: str) -> None:
    """Update the script text (for edits via Telegram reply)."""
    (
        get_client()
        .table("weekly_scripts")
        .update({"script_text": new_text})
        .eq("id", script_id)
        .execute()
    )


def update_weekly_script_message_id(script_id: str, message_id: int) -> None:
    """Link a weekly script to its Telegram message."""
    (
        get_client()
        .table("weekly_scripts")
        .update({"telegram_message_id": message_id})
        .eq("id", script_id)
        .execute()
    )


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


def delete_old_raw_events(days: int = 7) -> int:
    """Delete raw_events with event_date older than N days ago."""
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    result = (
        get_client()
        .table("raw_events")
        .delete()
        .lt("event_date", cutoff)
        .execute()
    )
    return len(result.data)


def delete_old_recommendations(days: int = 30) -> int:
    """Delete recommendations older than N days."""
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
    result = (
        get_client()
        .table("recommendations")
        .delete()
        .lt("created_at", cutoff)
        .execute()
    )
    return len(result.data)


def delete_old_logs(days: int = 30) -> int:
    """Delete old scrape_logs and alert_log entries. Returns total deleted."""
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
    r1 = (
        get_client()
        .table("scrape_logs")
        .delete()
        .lt("created_at", cutoff)
        .execute()
    )
    r2 = (
        get_client()
        .table("alert_log")
        .delete()
        .lt("created_at", cutoff)
        .execute()
    )
    return len(r1.data) + len(r2.data)


# --- Party voice note ---

PARTY_VOICE_BUCKET = "party-voice-notes"
PARTY_VOICE_FILENAME = "party_voice_note.ogg"


def upsert_party_voice_note(media_url: str, updated_by: str | None = None) -> None:
    """Set or update the active party voice note."""
    try:
        get_client().table("party_voice_note").upsert({
            "id": 1,
            "media_url": media_url,
            "updated_by": updated_by,
            "updated_at": datetime.utcnow().isoformat()
        }).execute()
    except Exception as e:
        error_msg = str(e).lower()
        if "could not find" in error_msg or "relation" in error_msg:
            logger.warning("party_voice_table_missing_on_upsert", media_url=media_url)
            raise
        raise


def get_party_voice_note() -> dict | None:
    """Get the current party voice note."""
    try:
        result = (
            get_client()
            .table("party_voice_note")
            .select("*")
            .eq("id", 1)
            .execute()
        )
        rows = result.data
        return rows[0] if rows else None
    except Exception as e:
        error_msg = str(e).lower()
        if "could not find" in error_msg or "relation" in error_msg:
            logger.debug("party_voice_table_missing_on_get")
            return None
        raise


def delete_party_voice_note() -> None:
    """Remove the active party voice note."""
    try:
        get_client().table("party_voice_note").delete().eq("id", 1).execute()
    except Exception as e:
        error_msg = str(e).lower()
        if "could not find" in error_msg or "relation" in error_msg:
            logger.debug("party_voice_table_missing_on_delete")
            return
        raise


def get_party_voice_storage_url(filename: str = PARTY_VOICE_FILENAME) -> str:
    """Get the public URL for the canonical party voice note file."""
    return get_client().storage.from_(PARTY_VOICE_BUCKET).get_public_url(filename)


def _is_missing_bucket_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "bucket not found" in message or "the resource was not found" in message


def _is_bucket_exists_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "already exists" in message or "duplicate" in message


def party_voice_exists_in_storage(filename: str = PARTY_VOICE_FILENAME) -> bool:
    """Return whether the canonical party voice note file exists in storage."""
    files = get_client().storage.from_(PARTY_VOICE_BUCKET).list(
        "",
        {"search": filename, "limit": 1},
    )
    return any(f.get("name") == filename for f in files)


async def upload_to_supabase_storage(file_data: bytes, filename: str = PARTY_VOICE_FILENAME) -> str:
    """Upload audio file to Supabase Storage and return public URL.
    
    Args:
        file_data: Binary audio file content
        filename: Original filename (e.g., "party_voice_note.ogg")
    
    Returns:
        Public HTTPS URL to the uploaded file
        
    Raises:
        Exception: If upload fails after all retry attempts
    """
    import asyncio
    bucket = PARTY_VOICE_BUCKET
    path = filename
    
    # Upload file in thread pool to avoid blocking the event loop
    # (Supabase storage API calls are synchronous)
    def _upload() -> str:
        storage = get_client().storage
        
        # First attempt: try to upload directly
        try:
            storage.from_(bucket).upload(
                path=path,
                file=file_data,
                file_options={"content-type": "audio/ogg", "upsert": "true"},
            )
            logger.debug("party_voice_upload_success", bucket=bucket, path=path)
            return storage.from_(bucket).get_public_url(path)
        except Exception as exc:
            # If not a bucket error, fail immediately
            if not _is_missing_bucket_error(exc):
                logger.exception("party_voice_upload_failed", bucket=bucket, path=path, error_type="upload_error")
                raise
            
            logger.info("party_voice_bucket_missing", bucket=bucket)
        
        # Second attempt: create bucket and retry upload
        try:
            logger.info("party_voice_creating_bucket", bucket=bucket)
            storage.create_bucket(bucket, options={"public": True})
            logger.info("party_voice_bucket_created", bucket=bucket)
        except Exception as create_exc:
            # If bucket already exists, that's fine - proceed to retry upload
            if not _is_bucket_exists_error(create_exc):
                logger.exception("party_voice_bucket_create_failed", bucket=bucket, error_type="create_error")
                raise
            logger.info("party_voice_bucket_already_exists", bucket=bucket)
        
        # Third attempt: retry upload after bucket handling
        try:
            logger.info("party_voice_upload_retry", bucket=bucket, path=path)
            storage.from_(bucket).upload(
                path=path,
                file=file_data,
                file_options={"content-type": "audio/ogg", "upsert": "true"},
            )
            logger.info("party_voice_upload_retry_success", bucket=bucket, path=path)
            return storage.from_(bucket).get_public_url(path)
        except Exception as retry_exc:
            logger.exception("party_voice_upload_retry_failed", bucket=bucket, path=path, error_type="retry_upload_error")
            raise

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _upload)


async def delete_party_voice_from_storage(filename: str = PARTY_VOICE_FILENAME) -> None:
    """Delete the canonical party voice note from Supabase Storage if present."""
    import asyncio

    def _delete() -> None:
        if not party_voice_exists_in_storage(filename):
            return
        get_client().storage.from_(PARTY_VOICE_BUCKET).remove([filename])

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _delete)


async def download_from_supabase_storage(public_url: str) -> bytes:
    """Download file from Supabase Storage public URL.
    
    Args:
        public_url: Public HTTPS URL from Supabase Storage
    
    Returns:
        Binary file content
    
    Raises:
        HTTPError: If the download fails (4xx or 5xx response)
    """
    import httpx
    async with httpx.AsyncClient() as client:
        response = await client.get(public_url, timeout=30.0)
        response.raise_for_status()
        return response.content
