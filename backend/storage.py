"""Persistent, owner-scoped registry; source videos expire automatically."""
import sqlite3
from contextlib import contextmanager
from fastapi import HTTPException
from backend.config import DATA_DIR

@contextmanager
def database():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATA_DIR / "stickerbot.sqlite3", timeout=30)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()

def initialize():
    with database() as db:
        db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS packs (
                id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, name TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL, source_name TEXT, status TEXT NOT NULL DEFAULT 'draft',
                count INTEGER NOT NULL DEFAULT 0, error TEXT, created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS media (
                id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, path TEXT NOT NULL,
                kind TEXT NOT NULL, created_at REAL NOT NULL, duration REAL NOT NULL,
                published_pack TEXT
            );
        """)

def owned_pack(pack_id, user_id):
    with database() as db:
        row = db.execute("SELECT * FROM packs WHERE id=? AND user_id=?", (pack_id, user_id)).fetchone()
    if row is None:
        raise HTTPException(404, "Набор не найден")
    return dict(row)
