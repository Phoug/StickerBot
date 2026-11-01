"""Browser-compatible preview; never changes the sticker stored in Telegram."""
import subprocess
import tempfile
from pathlib import Path

from backend.services.file_service import cleanup_files
from backend.services.media.sticker_converter import StickerConversionError


def make_video_preview(data: bytes) -> Path:
    folder = Path(tempfile.mkdtemp(prefix="sticker_preview_"))
    try:
        source, output = folder / "input.webm", folder / "preview.mp4"
        source.write_bytes(data)
        subprocess.run([
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
