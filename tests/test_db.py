"""Tests for the SQLite hotline message store."""
import pytest

from src import db


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    path = tmp_path / "hotline.db"
    monkeypatch.setattr(db.settings, "sqlite_path", str(path))
    return path


def test_upsert_and_get_roundtrip(sqlite_db):
    db.upsert_hotline_message("main", "Tonight at Basement", updated_by="pete")

    row = db.get_hotline_message("main")
    assert row is not None
    assert row["slot"] == "main"
    assert row["body"] == "Tonight at Basement"
    assert row["updated_by"] == "pete"
    assert row["updated_at"]


def test_upsert_updates_existing_slot(sqlite_db):
    db.upsert_hotline_message("party", "First message", updated_by="pete")
    db.upsert_hotline_message("party", "Second message", updated_by="sam")

    row = db.get_hotline_message("party")
    assert row["body"] == "Second message"
    assert row["updated_by"] == "sam"


def test_get_returns_none_for_unset_slot(sqlite_db):
    assert db.get_hotline_message("main") is None


def test_upsert_rejects_invalid_slot(sqlite_db):
    with pytest.raises(ValueError, match="Invalid hotline slot"):
        db.upsert_hotline_message("bogus", "nope")


def test_get_all_hotline_messages(sqlite_db):
    db.upsert_hotline_message("main", "Main message")
    db.upsert_hotline_message("party", "Party message")

    rows = {r["slot"]: r for r in db.get_all_hotline_messages()}
    assert set(rows) == {"main", "party"}
    assert rows["main"]["body"] == "Main message"
    assert rows["party"]["body"] == "Party message"


def test_db_file_created_lazily(tmp_path, monkeypatch):
    path = tmp_path / "nested" / "dir" / "hotline.db"
    monkeypatch.setattr(db.settings, "sqlite_path", str(path))

    db.upsert_hotline_message("main", "hello")
    assert path.exists()
