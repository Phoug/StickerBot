import os
import sqlite3
import subprocess
import sys
from contextlib import closing

import pytest

from backend.backup import backup_healthy, backup_once, checked_database, restore, snapshot
from backend.maintenance import DATABASE_NAME, exclusive_access


def live_registry(folder):
    folder.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(folder / DATABASE_NAME)
    db.executescript("PRAGMA journal_mode=WAL; CREATE TABLE packs(id TEXT, user_id INTEGER); CREATE TABLE media(id TEXT, user_id INTEGER);")
    db.execute("INSERT INTO packs VALUES ('saved-pack', 7)")
    db.commit()
    return db


def test_live_backup_includes_committed_wal_and_recovers_into_empty_directory(tmp_path):
    source, output, recovered = tmp_path / "live", tmp_path / "backups/registry.sqlite3", tmp_path / "recovered"
    with closing(live_registry(source)):
        assert (source / (DATABASE_NAME + "-wal")).exists()
        snapshot(source / DATABASE_NAME, output)
    assert output.stat().st_mode & 0o777 == 0o600
    with closing(checked_database(output)) as db:
        assert db.execute("SELECT * FROM packs").fetchall() == [("saved-pack", 7)]
    restore(output, recovered)
    with closing(checked_database(recovered / DATABASE_NAME)) as db:
        assert db.execute("SELECT COUNT(*) FROM packs").fetchone()[0] == 1
    with pytest.raises(FileExistsError):
        snapshot(source / DATABASE_NAME, output)
    with pytest.raises(FileExistsError):
        restore(output, recovered)


def test_restore_and_second_api_are_rejected_while_data_directory_is_owned(tmp_path):
    with closing(live_registry(tmp_path / "source")):
        pass
    output = snapshot(tmp_path / "source" / DATABASE_NAME, tmp_path / "backup.sqlite3")
    with exclusive_access(tmp_path / "target"):
        with pytest.raises(RuntimeError, match="already in use"):
            restore(output, tmp_path / "target")
        with pytest.raises(RuntimeError, match="only one API worker"):
            with exclusive_access(tmp_path / "target"):
                pytest.fail("Two API instances acquired the same directory")
    assert not (tmp_path / "target" / DATABASE_NAME).exists()


def test_invalid_database_does_not_publish_partial_backup(tmp_path):
    broken = tmp_path / "broken.sqlite3"
    broken.write_bytes(b"not sqlite")
    with pytest.raises(sqlite3.DatabaseError):
        snapshot(broken, tmp_path / "backup.sqlite3")
    assert not (tmp_path / "backup.sqlite3").exists()
    assert not list(tmp_path.glob(".sqlite-backup-*"))


def test_backup_cli_does_not_require_bot_credentials_or_dotenv(tmp_path):
    with closing(live_registry(tmp_path / "source")):
        pass
    env = {k: v for k, v in os.environ.items() if k not in {"BOT_TOKEN", "API_SECRET_TOKEN", "PYTHON_DOTENV_DISABLED"}}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run([sys.executable, "-m", "backend.backup", "create", "--data-dir", str(tmp_path / "source"),
                             "--output", str(tmp_path / "backup.sqlite3")], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert '"ok": true' in result.stdout


def test_scheduled_snapshots_rotate_only_own_generations_and_report_freshness(tmp_path):
    with closing(live_registry(tmp_path / "source")):
        pass
    backups = tmp_path / "backups"
    backups.mkdir()
    unrelated = backups / "manual-copy.sqlite3"
    unrelated.write_bytes(b"keep this operator file")
    for _ in range(3):
        backup_once(tmp_path / "source", backups, retention=2)
    assert len(list(backups.glob("stickerbot-*.sqlite3"))) == 2
    assert unrelated.read_bytes() == b"keep this operator file"
    assert backup_healthy(backups, max_age=60)
    assert not backup_healthy(backups, max_age=-1)
