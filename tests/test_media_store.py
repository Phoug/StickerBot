import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from backend import storage
from backend.services import media_store


@pytest.mark.parametrize("retain_original", [False, True])
def test_failed_registration_removes_untracked_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, retain_original: bool,
) -> None:
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    storage.initialize()
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    original = tmp_path / "original.webm"
    original.write_bytes(b"original")
    original_database = media_store.database

    @contextmanager
    def failed_commit() -> Iterator[sqlite3.Connection]:
        with original_database() as db:
            yield db
            raise sqlite3.OperationalError("Injected commit failure")

    monkeypatch.setattr(media_store, "database", failed_commit)
    with pytest.raises(sqlite3.OperationalError, match="Injected"):
        media_store.register(
            source, 7, "source", 1,
            original=original if retain_original else None,
        )
    assert list((tmp_path / "media").iterdir()) == []
    with storage.database() as db:
        assert db.execute("SELECT count(*) FROM media").fetchone()[0] == 0
