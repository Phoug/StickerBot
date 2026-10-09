import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

API_SECRET_TOKEN = os.getenv("API_SECRET_TOKEN")
BOT_TOKEN = os.getenv("BOT_TOKEN")
TELEGRAM_API_ID_RAW = os.getenv("TELEGRAM_API_ID")
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH")
TELETHON_SESSIONS_DIR = Path(
    os.getenv(
        "TELETHON_SESSIONS_DIR",
        str(Path(__file__).resolve().parent / "telegram_sessions"),
    )
)
MINI_APP_AUTH_MAX_AGE = int(os.getenv("MINI_APP_AUTH_MAX_AGE", "3600"))
LOGIN_CODE_TTL = int(os.getenv("LOGIN_CODE_TTL", "600"))
LOGIN_CODE_COOLDOWN = int(os.getenv("LOGIN_CODE_COOLDOWN", "60"))
MAX_STICKER_SETS = int(os.getenv("MAX_STICKER_SETS", "2000"))

if not API_SECRET_TOKEN:
    raise RuntimeError("API_SECRET_TOKEN environment variable is not set")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is not set")

if not TELEGRAM_API_ID_RAW:
    raise RuntimeError("TELEGRAM_API_ID environment variable is not set")

if not TELEGRAM_API_HASH:
    raise RuntimeError("TELEGRAM_API_HASH environment variable is not set")

try:
    TELEGRAM_API_ID = int(TELEGRAM_API_ID_RAW)
except ValueError as exc:
    raise RuntimeError("TELEGRAM_API_ID must be an integer") from exc

TELETHON_SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
