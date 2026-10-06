import os
import subprocess
import tempfile
from pathlib import Path


class StickerConversionError(Exception):
    pass


MAX_DURATION = 3.0
MAX_FILE_SIZE = 256 * 1024
MAX_OUTPUT_SIZE = 255 * 1024

FFMPEG_TIMEOUT = 120


def _run_command(command: list[str]) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            timeout=FFMPEG_TIMEOUT,
        )
    except FileNotFoundError as exc:
        raise StickerConversionError(
            "ffmpeg is not installed or is not available in PATH"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise StickerConversionError(
            "Video conversion timed out"
        ) from exc
    except subprocess.CalledProcessError as exc:
        error = exc.stderr.decode(
            "utf-8",
            errors="replace",
        ).strip()

        raise StickerConversionError(
            error or "ffmpeg conversion failed"
        ) from exc


def _probe_duration(input_path: str) -> float:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        input_path,
    ]

    try:
        result = _run_command(command)
        return float(result.stdout.decode().strip())
    except (ValueError, UnicodeDecodeError) as exc:
        raise StickerConversionError(
            "Unable to determine video duration"
        ) from exc


def _encode(
    input_path: str,
    output_path: str,
    start: float,
    duration: float,
    fps: int,
    crf: int,
    bitrate_kbit: int | None = None,
) -> None:
    filter_chain = (
        "scale=512:512:"
        "force_original_aspect_ratio=decrease:"
        "force_divisible_by=2,"
        f"fps={fps},"
        "format=yuva420p"
    )

    command = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{start:.3f}",
        "-i",
        input_path,
        "-t",
        f"{duration:.3f}",
        "-vf",
        filter_chain,
        "-an",
        "-c:v",
        "libvpx-vp9",
        "-pix_fmt",
        "yuva420p",
        "-auto-alt-ref",
        "0",
    ]

    if bitrate_kbit:
        command.extend([
            "-b:v",
            f"{bitrate_kbit}k",
            "-maxrate",
            f"{bitrate_kbit}k",
            "-bufsize",
            f"{bitrate_kbit * 2}k",
        ])
    else:
        command.extend([
            "-b:v",
            "0",
            "-crf",
            str(crf),
        ])

    command.extend([
        "-deadline",
        "realtime",
        "-cpu-used",
        "5",
        "-row-mt",
        "1",
        "-tile-columns",
        "2",
        "-frame-parallel",
        "1",
        "-metadata",
        "title=Telegram Video Sticker",
        output_path,
    ])

    _run_command(command)


def _convert_with_quality_search(
    input_path: str,
    output_path: str,
    start: float,
    duration: float,
) -> None:
    target_bitrate_kbit = int((MAX_OUTPUT_SIZE * 8) / (duration * 1000) * 0.85)

    attempts = [
        (32, 30, None),
        (40, 30, None),
        (48, 25, None),
        (52, 20, target_bitrate_kbit),
    ]

    last_size = 0

    for index, (crf, fps, b_rate) in enumerate(attempts):
        attempt_path = f"{output_path}.attempt{index}.webm"

        try:
            _encode(
                input_path=input_path,
                output_path=attempt_path,
                start=start,
                duration=duration,
                fps=fps,
                crf=crf,
                bitrate_kbit=b_rate,
            )

            size = os.path.getsize(attempt_path)
            last_size = size

            if size <= MAX_OUTPUT_SIZE:
                os.replace(attempt_path, output_path)
                return

        finally:
            if os.path.exists(attempt_path):
                os.remove(attempt_path)

    raise StickerConversionError(
        f"Unable to fit video sticker into "
        f"{MAX_FILE_SIZE // 1024} KB "
        f"(last result: {last_size // 1024} KB)"
    )


def convert_video_to_sticker(
    input_path: str,
    output_path: str | None = None,
    start: float = 0.0,
    end: float | None = None,
) -> tuple[str, float]:
    input_file = Path(input_path)

    if not input_file.is_file():
        raise StickerConversionError("Input video does not exist")

    if start < 0:
        raise StickerConversionError("Start time cannot be negative")

    source_duration = _probe_duration(str(input_file))

    if start >= source_duration:
        raise StickerConversionError("Start time is outside the source video")

    if end is None:
        end = min(source_duration, start + MAX_DURATION)

    if end <= start:
        raise StickerConversionError("End time must be greater than start time")

    duration = end - start

    if duration > MAX_DURATION:
        raise StickerConversionError("Sticker duration cannot exceed 3 seconds")

    if output_path is None:
        with tempfile.NamedTemporaryFile(suffix=".webm", prefix="telegram_sticker_", delete=False) as tmp:
            output_path = tmp.name

    output_path = str(Path(output_path))

    try:
        _convert_with_quality_search(
            input_path=str(input_file),
            output_path=output_path,
            start=start,
            duration=duration,
        )
    except Exception:
        if os.path.exists(output_path):
            os.remove(output_path)
        raise

    return output_path, duration


def validate_sticker_file(path: str) -> None:
    path_obj = Path(path)

    if not path_obj.is_file():
        raise StickerConversionError("Output file does not exist")

    if path_obj.stat().st_size > MAX_FILE_SIZE:
        raise StickerConversionError("Output file exceeds Telegram's 256 KB limit")

    if path_obj.suffix.lower() != ".webm":
        raise StickerConversionError("Output file is not WebM")