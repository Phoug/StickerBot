"""Persistent, owner-scoped registry; source videos expire automatically."""
import sqlite3
import os
from contextlib import contextmanager
from fastapi import HTTPException
from backend.config import DATA_DIR
from backend.maintenance import DATABASE_NAME

SCHEMA_VERSION = 2

@contextmanager
def database():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATA_DIR / DATABASE_NAME, timeout=30)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()

def initialize():
    with database() as db:
        if db.execute("PRAGMA user_version").fetchone()[0] > SCHEMA_VERSION:
            raise RuntimeError("Database schema is newer than this application; restore compatible code")
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
        columns = {row["name"] for row in db.execute("PRAGMA table_info(media)")}
        if "published_replace_id" not in columns:
            db.execute("ALTER TABLE media ADD COLUMN published_replace_id TEXT")
        db.execute(f"PRAGMA user_version={SCHEMA_VERSION}")

def owned_pack(pack_id, user_id):
    with database() as db:
        row = db.execute("SELECT * FROM packs WHERE id=? AND user_id=?", (pack_id, user_id)).fetchone()
    if row is None:
        raise HTTPException(404, "Набор не найден")
    return dict(row)


def check_ready():
    """Probe an existing registry without silently creating a missing database."""
    if not os.access(DATA_DIR, os.W_OK) or not os.access(DATA_DIR / DATABASE_NAME, os.W_OK):
        raise OSError("Data directory is not writable")
    connection = sqlite3.connect((DATA_DIR / DATABASE_NAME).resolve().as_uri() + "?mode=rw", uri=True, timeout=1)
    try:
        for table in ("packs", "media"):
            connection.execute(f"SELECT id FROM {table} LIMIT 1")
    finally:
        connection.close()
