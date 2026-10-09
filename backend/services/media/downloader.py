import re
import tempfile
from pathlib import Path
from typing import Any

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError


class DownloadFailed(Exception):
    pass


EXTRACTOR_ALIASES: dict[str, str] = {
    "tiktok": "tiktok",
    "youtube": "youtube",
    "twitter": "x",
    "instagram": "instagram",
    "vimeo": "vimeo",
    "facebook": "facebook",
    "reddit": "reddit",
    "twitch": "twitch",
}
BASE_YDL_OPTIONS: dict[str, Any] = {
    "quiet": True,
    "no_warnings": True,
    "noplaylist": True,
    "retries": 3,
    "fragment_retries": 3,
    "file_access_retries": 3,
    "extractor_retries": 3,
    "socket_timeout": 30,
    "continuedl": True,
    "concurrent_fragment_downloads": 8,
    "http_chunk_size": 10 * 1024 * 1024,
    "restrictfilenames": False,
    "windowsfilenames": True,
}
MIME_TYPES: dict[str, str] = {
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mkv": "video/x-matroska",
    ".mov": "video/quicktime",
    ".avi": "video/x-msvideo",
    ".m4a": "audio/mp4",
    ".mp3": "audio/mpeg",
    ".opus": "audio/opus",
    ".ogg": "audio/ogg",
}


def _source_name(info: dict) -> str:
    key = str(info.get("extractor_key") or info.get("extractor") or "").lower()
    for source, name in EXTRACTOR_ALIASES.items():
        if source in key:
            return name
    return key or "video"


def _sanitize_filename(name: str) -> str:
    name = name.strip()
    name = re.sub(r'[<>:"/\\|?*\x00-\x1F]', "_", name)
    name = re.sub(r"\s+", " ", name)
    name = name.rstrip(". ")
    return name[:180] or "video"


def _build_format_selector(format_id: str | None) -> str:
    if not format_id:
        return "bv*+ba/b"
    return f"{format_id}+ba/{format_id}/b"


def _ydl_opts(format_selector: str, output_template: str) -> dict[str, Any]:
    return {
        **BASE_YDL_OPTIONS,
        "format": format_selector,
        "outtmpl": output_template,
        "merge_output_format": "mp4",
        "postprocessors": [{"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"}],
    }


def _find_output_file(tmpdir_path: Path) -> Path:
    output_files = [item for item in tmpdir_path.iterdir() if item.is_file()]
    if not output_files:
        raise DownloadFailed("yt-dlp did not create an output file")
    mp4_files = [item for item in output_files if item.suffix.lower() == ".mp4"]
    if mp4_files:
        return max(mp4_files, key=lambda item: item.stat().st_size)
    return max(output_files, key=lambda item: item.stat().st_size)


def download_to_file(
    url: str,
    format_id: str | None = None,
    name: str | None = None,
    target_dir: str | Path | None = None,
) -> tuple[Path, str, str]:
    created_temp_dir = target_dir is None
    temp_dir = Path(tempfile.mkdtemp(prefix="video_dl_")) if created_temp_dir else Path(target_dir)
    temp_dir.mkdir(parents=True, exist_ok=True)
    output_template = str(temp_dir / "video.%(ext)s")
    try:
        options = _ydl_opts(_build_format_selector(format_id), output_template)
        with YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)
        if not info:
            raise DownloadFailed("yt-dlp returned empty metadata")
        output_path = _find_output_file(temp_dir)
        extension = output_path.suffix.lstrip(".").lower()
        base_name = _sanitize_filename(name) if name else _source_name(info)
        filename = f"{base_name}.{extension}"
        mime_type = MIME_TYPES.get(output_path.suffix.lower(), "application/octet-stream")
        return output_path, filename, mime_type
    except DownloadFailed:
        if created_temp_dir:
            from backend.services.file_service import cleanup_files
            cleanup_files(temp_dir)
        raise
    except DownloadError as exc:
        if created_temp_dir:
            from backend.services.file_service import cleanup_files
            cleanup_files(temp_dir)
        raise DownloadFailed(str(exc)) from exc
    except Exception as exc:
        if created_temp_dir:
            from backend.services.file_service import cleanup_files
            cleanup_files(temp_dir)
        raise DownloadFailed(f"Unexpected error: {exc}") from exc
