"""Shared wall-clock budgets and bounded FFmpeg threads."""
import os
import subprocess
import time
from contextlib import contextmanager
from contextvars import ContextVar

_deadline = ContextVar("media_deadline", default=None)


@contextmanager
def job_deadline(seconds):
    current = _deadline.get()
    token = _deadline.set(min(current, time.monotonic() + seconds) if current else time.monotonic() + seconds)
    try:
        yield
    finally:
        _deadline.reset(token)


def remaining_timeout(default):
    deadline = _deadline.get()
    remaining = min(default, deadline - time.monotonic()) if deadline else default
    if remaining <= 0:
        raise subprocess.TimeoutExpired("media job", default)
    return remaining


def run_command(command, *, timeout=120, **kwargs):
    command = list(command)
    if os.path.basename(str(command[0])) == "ffmpeg":
        threads = str(max(1, int(os.getenv("FFMPEG_THREADS", "2"))))
        command[1:1] = ["-threads", threads, "-filter_threads", threads, "-filter_complex_threads", threads]
        command[-1:-1] = ["-threads", threads]
    return subprocess.run(command, timeout=remaining_timeout(timeout), **kwargs)
