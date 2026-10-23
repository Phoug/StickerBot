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
MAX_SOURCE_SIZE = 50 * 1024 * 1024
SOURCE_TTL = 3600
if not BOT_TOKEN or not API_SECRET_TOKEN:
    raise RuntimeError("BOT_TOKEN and API_SECRET_TOKEN must be configured")
