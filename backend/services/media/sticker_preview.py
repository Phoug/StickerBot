"""Browser-compatible preview; never changes the sticker stored in Telegram."""
import subprocess
import tempfile
from pathlib import Path
from backend.services.media.commands import run_command

from backend.services.file_service import cleanup_files
from backend.services.media.sticker_converter import StickerConversionError


def make_video_preview(data: bytes) -> Path:
    folder = Path(tempfile.mkdtemp(prefix="sticker_preview_"))
    try:
        source, output = folder / "input.webm", folder / "preview.mp4"
        source.write_bytes(data)
        run_command([
            "ffmpeg", "-y", "-v", "error", "-protocol_whitelist", "file,pipe",
            "-c:v", "libvpx-vp9", "-i", str(source), "-filter_complex",
            "[0:v]format=rgba,split[st][base];[base]lutrgb=r=31:g=31:b=31:a=255[bg];"
            "[bg][st]overlay=0:0:shortest=1,pad=ceil(iw/2)*2:ceil(ih/2)*2:color=0x1f1f1f,format=yuv420p[out]",
            "-map", "[out]", "-an", "-t", "3", "-c:v", "libx264", "-preset", "veryfast",
            "-crf", "24", "-movflags", "+faststart", str(output),
        ], capture_output=True, check=True, timeout=30)
        return output
    except (OSError, subprocess.SubprocessError) as exc:
        cleanup_files(folder)
        raise StickerConversionError("Не удалось создать MP4-предпросмотр") from exc


def _preview_bytes(data: bytes) -> tuple[bytes, str]:
    output = make_video_preview(data)
    try:
        return output.read_bytes(), "video/mp4"
    finally:
        cleanup_files(output.parent)


async def video_preview(
    user_id: int, media_id: str, data: bytes,
) -> tuple[bytes, str]:
    """Share preview work; its producer owns capacity even without waiters."""
    from fastapi import HTTPException
    from backend.services.processing import media_capacity, run_blocking
    from backend.services.media.preview_cache import cached_media

    async def produce() -> tuple[bytes, str]:
        async with media_capacity:
            try:
                return await run_blocking(_preview_bytes, data)
            except StickerConversionError as exc:
                raise HTTPException(
                    422, "Не удалось подготовить предпросмотр видео",
                ) from exc

    return await cached_media((user_id, media_id, "mp4"), produce)
