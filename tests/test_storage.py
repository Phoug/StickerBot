import sqlite3
from pathlib import Path

import pytest

from backend import storage


def test_schema_v1_migrates_without_losing_published_media(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    with sqlite3.connect(tmp_path / "stickerbot.sqlite3") as db:
        db.executescript("""
            CREATE TABLE media (
                id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, path TEXT NOT NULL,
                kind TEXT NOT NULL, created_at REAL NOT NULL, duration REAL NOT NULL,
                published_pack TEXT
            );
            INSERT INTO media VALUES ('render', 7, '/source.webp', 'render_photo', 1, 0, 'pack');
            PRAGMA user_version=1;
        """)
    storage.initialize()
    storage.initialize()
    with storage.database() as db:
        row = db.execute("SELECT * FROM media WHERE id='render'").fetchone()
        assert row["published_pack"] == "pack"
        assert row["published_replace_id"] is None
        assert db.execute("PRAGMA user_version").fetchone()[0] == 2


def test_newer_schema_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    with sqlite3.connect(tmp_path / "stickerbot.sqlite3") as db:
        db.execute("PRAGMA user_version=999")
    with pytest.raises(RuntimeError, match="newer"):
        storage.initialize()
