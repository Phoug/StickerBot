import math
import re
from pathlib import Path
from urllib.parse import unquote, urlparse

from app.bot.config import URL_PATTERN


def extract_url(text: str) -> str | None:
    match = URL_PATTERN.search(text)
    if not match:
        return None
    url = match.group(0).rstrip(".,!?;:)]}>")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return url


def parse_time(value: str) -> float:
    value = value.strip()
    try:
        if ":" not in value:
            result = float(value)
        else:
            parts = value.split(":")
            if len(parts) == 2:
                result = float(parts[0]) * 60 + float(parts[1])
            elif len(parts) == 3:
                result = float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
            else:
                raise ValueError
    except (TypeError, ValueError):
        raise ValueError from None
    if not math.isfinite(result) or result < 0:
        raise ValueError
    return result


def parse_sticker_args(text: str | None, tr) -> tuple[float, float | None]:
    if not text:
        return 0.0, None
    clean_text = text.strip()
    if not clean_text.startswith("/sticker"):
        return 0.0, None
    parts = clean_text.splitlines()[0].split()
    arguments = parts[1:]
    if len(arguments) > 2:
        raise ValueError(tr("usage_sticker"))
    start = parse_time(arguments[0]) if arguments else 0.0
    end = parse_time(arguments[1]) if len(arguments) == 2 else None
    if end is not None and end <= start:
        raise ValueError(tr("invalid_interval"))
    return start, end


def format_size(size: int) -> str:
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / 1024 / 1024:.1f} MB"


def get_content_disposition_filename(header: str | None) -> str | None:
    if not header:
        return None
    match = re.search(r"filename\*=UTF-8''([^;]+)", header, re.IGNORECASE)
    if match:
        return unquote(match.group(1).strip())
    match = re.search(r'filename="([^"]+)"', header, re.IGNORECASE)
    if match:
        return match.group(1)
    return None


def safe_filename(filename: str) -> str:
    return Path(filename).name or "video.mp4"
