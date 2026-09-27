"""Integration tests for schema creation against a real sqlite3 file.

See docs/superpowers/specs/2026-09-27-project-foundation-design.md §5.
"""

from src.storage import db


def test_connect_creates_all_five_tables(tmp_path):
    conn = db.connect(tmp_path / "test.db")
    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {"experiments", "inputs", "calls", "judge_logs", "decisions"} <= tables
    conn.close()


def test_connect_enables_wal_mode(tmp_path):
    conn = db.connect(tmp_path / "test.db")
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal"
    conn.close()


def test_connect_is_idempotent(tmp_path):
    db_path = tmp_path / "test.db"
    db.connect(db_path).close()
    conn2 = db.connect(db_path)  # must not raise on second call
    conn2.close()
