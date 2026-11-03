import os
import re
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[3]
if os.getenv("PYTHON_DOTENV_DISABLED") != "1":
    load_dotenv(ROOT_DIR / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_BASE_URL = os.getenv("VIDEO_API_URL", "http://127.0.0.1:8000").rstrip("/")
WEBAPP_URL = os.getenv("WEBAPP_URL", "http://127.0.0.1:8000/app")
API_SECRET_TOKEN = os.getenv("API_SECRET_TOKEN")

MAX_TELEGRAM_DOWNLOAD_SIZE = 20 * 1024 * 1024
MAX_TELEGRAM_UPLOAD_SIZE = 50 * 1024 * 1024
HTTP_TIMEOUT = 300
CHUNK_SIZE = 1024 * 1024
URL_PATTERN = re.compile(r"https?://[^\s]+", re.IGNORECASE)

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is not set")
