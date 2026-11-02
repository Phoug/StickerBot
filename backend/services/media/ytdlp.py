"""Bound yt-dlp time and terminate its process tree when the deadline expires."""
import json
import logging
import os
import signal
import subprocess
import sys
from pathlib import Path

from backend.config import MAX_SOURCE_SIZE, MEDIA_JOB_TIMEOUT
from backend.services.media.network import validate_public_url
from backend.services.media.commands import remaining_timeout

logger = logging.getLogger(__name__)


def extract(url, options, *, download=False, max_duration=600):
    validate_public_url(url)
    # Keep credentials and user proxy configuration out of the downloader.
    allowed_env = {"PATH", "SYSTEMROOT", "WINDIR", "LANG", "LC_ALL", "TMPDIR", "TEMP", "TMP", "SSL_CERT_FILE", "SSL_CERT_DIR"}
    env = {key: value for key, value in os.environ.items() if key in allowed_env}
    env.update(PYTHON_DOTENV_DISABLED="1", PYTHONDONTWRITEBYTECODE="1", PYTHONUNBUFFERED="1")
    job = {"url": url, "options": options, "download": download,
           "max_bytes": MAX_SOURCE_SIZE, "max_duration": max_duration}
    process = subprocess.Popen(
        [sys.executable, "-m", "backend.services.media.ytdlp_worker"],
        cwd=Path(__file__).resolve().parents[3], env=env,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        text=True, start_new_session=os.name == "posix",
    )
    try:
        stdout, _ = process.communicate(json.dumps(job), timeout=remaining_timeout(MEDIA_JOB_TIMEOUT))
    except subprocess.TimeoutExpired:
        try:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
        except ProcessLookupError:
            pass
        process.communicate()
        logger.warning("Video download deadline expired", extra={"event": "download_timeout"})
        raise TimeoutError("Превышено время загрузки видео") from None
    try:
        result = json.loads(stdout)
    except (ValueError, TypeError):
        logger.warning("Video downloader exited without a response (status %s)", process.returncode,
                       extra={"event": "download_failed"})
        raise RuntimeError("Загрузчик видео завершился с ошибкой") from None
    if process.returncode or not result.get("ok"):
        logger.warning("Video downloader failed (%s)", result.get("reason", "unknown"), extra={"event": "download_failed"})
        raise RuntimeError(result.get("error", "Не удалось загрузить видео"))
    return result["info"]
