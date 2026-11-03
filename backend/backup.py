"""Consistent SQLite snapshots and non-destructive recovery, without .env access."""
import argparse
import json
import os
import sqlite3
import tempfile
import signal
import threading
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from backend.maintenance import DATABASE_NAME, exclusive_access


def checked_database(path):
    connection = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True, timeout=10)
    try:
        if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ValueError("SQLite integrity check failed")
        for table in ("packs", "media"):
            connection.execute(f"SELECT id, user_id FROM {table} LIMIT 1")
    except Exception:
        connection.close()
        raise
    return connection


def snapshot(source, destination):
    """Publish a verified snapshot atomically; never overwrite an existing file."""
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if source == destination or destination.exists():
        raise FileExistsError("Destination must be a new backup file")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".sqlite-backup-", dir=destination.parent) as folder:
        temporary = Path(folder) / DATABASE_NAME
        with closing(checked_database(source)) as live, closing(sqlite3.connect(temporary)) as copy:
            live.backup(copy, pages=256, sleep=0.05)
        os.chmod(temporary, 0o600)
        with closing(checked_database(temporary)):
            pass
        with temporary.open("rb") as data:
            os.fsync(data.fileno())
        # An exclusive hard link avoids an exists()/replace() overwrite race.
        os.link(temporary, destination)
    return destination


def restore(source, data_dir):
    """Recover into an empty directory, retaining every existing database."""
    folder = Path(data_dir).resolve()
    with exclusive_access(folder):
        target = folder / DATABASE_NAME
        if any(path.exists() for path in (target, Path(str(target) + "-wal"), Path(str(target) + "-shm"))):
            raise FileExistsError("Restore requires an empty data directory; the existing database is preserved")
        return snapshot(source, target)


def backup_once(data_dir, backup_dir, retention=48):
    if retention < 2:
        raise ValueError("Keep at least two backup generations")
    backup_dir = Path(backup_dir)
    name = "stickerbot-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".sqlite3"
    output = snapshot(Path(data_dir) / DATABASE_NAME, backup_dir / name)
    state = backup_dir / ".last-success.json"
    temporary = state.with_suffix(".tmp")
    temporary.write_text(json.dumps({"created_at": time.time(), "file": name}))
    os.chmod(temporary, 0o600)
    temporary.replace(state)
    # Only this tool's timestamped generations are eligible for retention.
    generations = sorted(backup_dir.glob("stickerbot-????????T????????????Z.sqlite3"), reverse=True)
    for old in generations[retention:]:
        old.unlink()
    return output


def backup_healthy(backup_dir, max_age):
    try:
        state = json.loads((Path(backup_dir) / ".last-success.json").read_text())
        age = time.time() - state["created_at"]
        name = state["file"]
        return Path(name).name == name and (Path(backup_dir) / name).is_file() and 0 <= age <= max_age
    except (OSError, ValueError, KeyError, TypeError):
        return False


def schedule(data_dir, backup_dir, interval, retention):
    if interval <= 0 or retention < 2:
        raise ValueError("Backup interval must be positive; retention must be at least two")
    stop = threading.Event()
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *_: stop.set())
    while not stop.is_set():
        try:
            output = backup_once(data_dir, backup_dir, retention)
            print(json.dumps({"ok": True, "event": "backup_completed", "file": output.name}), flush=True)
        except (OSError, ValueError, sqlite3.Error) as exc:
            print(json.dumps({"ok": False, "event": "backup_failed", "error": type(exc).__name__}), flush=True)
        stop.wait(interval)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create", help="Back up a running SQLite database, including committed WAL data")
    create.add_argument("--data-dir", type=Path, default=Path(os.getenv("DATA_DIR", "data")))
    create.add_argument("--output", type=Path, required=True)
    check = commands.add_parser("verify", help="Check integrity and expected registry tables")
    check.add_argument("backup", type=Path)
    recover = commands.add_parser("restore", help="Restore into a new, empty data directory")
    recover.add_argument("backup", type=Path)
    recover.add_argument("--data-dir", type=Path, required=True)
    daemon = commands.add_parser("daemon", help="Create verified snapshots periodically; handle SIGTERM gracefully")
    daemon.add_argument("--data-dir", type=Path, default=Path(os.getenv("DATA_DIR", "data")))
    daemon.add_argument("--backup-dir", type=Path, default=Path(os.getenv("BACKUP_DIR", "backups")))
    daemon.add_argument("--interval", type=int, default=int(os.getenv("BACKUP_INTERVAL_SECONDS", "3600")))
    daemon.add_argument("--retention", type=int, default=int(os.getenv("BACKUP_RETENTION_COUNT", "48")))
    health = commands.add_parser("health", help="Check the most recent successful scheduled snapshot")
    health.add_argument("--backup-dir", type=Path, default=Path(os.getenv("BACKUP_DIR", "backups")))
    health.add_argument("--max-age", type=int, default=int(os.getenv("BACKUP_INTERVAL_SECONDS", "3600")) * 2)
    args = parser.parse_args(argv)
    if args.command == "health":
        parser.exit(0 if backup_healthy(args.backup_dir, args.max_age) else 1)
    try:
        if args.command == "daemon":
            schedule(args.data_dir, args.backup_dir, args.interval, args.retention)
            return
        elif args.command == "create":
            output = snapshot(args.data_dir / DATABASE_NAME, args.output)
        elif args.command == "restore":
            output = restore(args.backup, args.data_dir)
        else:
            with closing(checked_database(args.backup)):
                pass
            output = args.backup
    except (OSError, ValueError, RuntimeError, sqlite3.Error) as exc:
        parser.exit(1, f"{exc}\n")
    print(json.dumps({"ok": True, "command": args.command, "path": str(output),
                      "completed_at": datetime.now(timezone.utc).isoformat()}))


if __name__ == "__main__":
    main()
