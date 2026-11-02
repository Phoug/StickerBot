import os
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if os.getenv("PYTHON_DOTENV_DISABLED") != "1":
    load_dotenv(PROJECT_ROOT / ".env")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
API_SECRET_TOKEN = os.getenv("API_SECRET_TOKEN", "")
MINI_APP_AUTH_MAX_AGE = int(os.getenv("MINI_APP_AUTH_MAX_AGE", "86400"))
DATA_DIR = Path(os.getenv("DATA_DIR", str(PROJECT_ROOT / "data")))


def positive_int(name, default):
    value = int(os.getenv(name, str(default)))
    if value <= 0:
        raise RuntimeError(f"{name} must be positive")
    return value


MAX_SOURCE_SIZE = positive_int("MAX_SOURCE_SIZE_BYTES", 50 * 1024 * 1024)
MAX_REQUEST_SIZE = MAX_SOURCE_SIZE + 1024 * 1024  # Multipart headers and form fields.
SOURCE_TTL = positive_int("SOURCE_TTL_SECONDS", 3600)
MEDIA_CONCURRENCY = positive_int("MEDIA_CONCURRENCY", 2)
MEDIA_JOB_TIMEOUT = positive_int("MEDIA_JOB_TIMEOUT_SECONDS", 240)
CLEANUP_INTERVAL = positive_int("MEDIA_CLEANUP_INTERVAL_SECONDS", 300)
if not BOT_TOKEN or not API_SECRET_TOKEN:
    raise RuntimeError("BOT_TOKEN and API_SECRET_TOKEN must be configured")
