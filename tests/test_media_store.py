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


def test_editor_preview_retains_uploaded_original_and_expires_both(client) -> None:
    _, _, folder = client
    source = folder / "upload"
    source.write_bytes(b"full-resolution original")
    preview = folder / "source.mp4"
    preview.write_bytes(b"lightweight preview")
    registered = media_store.register(preview, 7, "source", 1, original=source)
    owned = media_store.owned_media(registered["id"], 7)
    original = owned["render_path"]
    assert original.read_bytes() == b"full-resolution original"
    assert Path(owned["path"]).read_bytes() == b"lightweight preview"
    with storage.database() as db:
        db.execute("UPDATE media SET created_at=0 WHERE id=?", (registered["id"],))
    media_store.cleanup_expired()
    assert not original.exists()
    assert not Path(owned["path"]).exists()
