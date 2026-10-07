"""Hotline message persistence (SQLite).

The event/dedup/recommendation pipeline is dormant; the only live data is the
`hotline_messages` table read by the Twilio IVR and written via Telegram.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from src.config import settings
from src.log import get_logger

logger = get_logger("db")

HOTLINE_SLOTS = ("main", "party")

_DDL = """
CREATE TABLE IF NOT EXISTS hotline_messages (
    slot TEXT PRIMARY KEY,
    body TEXT NOT NULL,
    updated_by TEXT,
    updated_at TEXT NOT NULL
)
"""


def _connect() -> sqlite3.Connection:
    path = Path(settings.sqlite_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute(_DDL)
    return conn


def upsert_hotline_message(slot: str, body: str, updated_by: str | None = None) -> None:
    """Set the message for a hotline slot ('main' or 'party')."""
    if slot not in HOTLINE_SLOTS:
        raise ValueError(f"Invalid hotline slot: {slot}")
    now = datetime.now(timezone.utc).isoformat()
    conn = _connect()
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO hotline_messages (slot, body, updated_by, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(slot) DO UPDATE SET
                    body = excluded.body,
                    updated_by = excluded.updated_by,
                    updated_at = excluded.updated_at
                """,
                (slot, body, updated_by, now),
            )
    finally:
        conn.close()
    logger.info("hotline_message_upserted", slot=slot, updated_by=updated_by)


def get_hotline_message(slot: str) -> dict | None:
    """Get the message row for a hotline slot, or None if unset."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT slot, body, updated_by, updated_at FROM hotline_messages WHERE slot = ?",
            (slot,),
        ).fetchone()
    finally:
        conn.close()
    return dict(row) if row else None


def get_all_hotline_messages() -> list[dict]:
    """Get all hotline message rows."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT slot, body, updated_by, updated_at FROM hotline_messages"
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]
