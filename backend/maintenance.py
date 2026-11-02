"""Credential-free filesystem coordination shared by API startup and recovery."""
from contextlib import contextmanager
import os
from pathlib import Path

DATABASE_NAME = "stickerbot.sqlite3"


@contextmanager
def exclusive_access(data_dir):
    """Fail closed when another API process or maintenance operation owns the data."""
    folder = Path(data_dir)
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / ".api.lock").open("a+b") as lock:
        if lock.tell() == 0:
            lock.write(b"\0")
            lock.flush()
        lock.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError("Data directory is already in use. Stop the API before recovery; run only one API worker.") from exc
        try:
            yield
        finally:
            if os.name == "nt":
                import msvcrt
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
