import json
import math
import subprocess
from pathlib import Path
from backend.services.media.sticker_converter import StickerConversionError, _convert_with_quality_search

def probe(path):
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-protocol_whitelist", "file,pipe", "-format_whitelist", "mov,matroska,webm,avi,mpeg,mpegvideo,ogg,asf,flv", "-select_streams", "v:0", "-show_entries",
             "stream=width,height:format=duration", "-of", "json", str(path)],
            capture_output=True, check=True, timeout=20)
        info = json.loads(result.stdout)
        stream = info["streams"][0]
        duration = float(info["format"]["duration"])
        width, height = int(stream["width"]), int(stream["height"])
        if not math.isfinite(duration) or not 0.05 <= duration <= 600 or not 1 <= width <= 4096 or not 1 <= height <= 4096:
            raise ValueError()
        return duration, width, height
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, IndexError) as exc:
        raise StickerConversionError("Нужно видео до 10 минут с разрешением не более 4096×4096") from exc

def normalize(source, output):
    probe(source)
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-protocol_whitelist", "file,pipe", "-format_whitelist", "mov,matroska,webm,avi,mpeg,mpegvideo,ogg,asf,flv", "-i", str(source), "-map", "0:v:0", "-an",
             "-vf", "scale=1280:1280:force_original_aspect_ratio=decrease:force_divisible_by=2,setsar=1",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "25", "-pix_fmt", "yuv420p",
             "-movflags", "+faststart", "-fs", "52428801", str(output)],
            capture_output=True, check=True, timeout=180)
    except (OSError, subprocess.SubprocessError) as exc:
        raise StickerConversionError("Не удалось подготовить видео для редактора") from exc
    if output.stat().st_size > 50 * 1024 * 1024:
        raise StickerConversionError("Подготовленное видео превышает 50 МБ")
    return probe(output)[0]

def render(source, output, start, end, shape, zoom, x, y):
    duration, width, height = probe(source)
    if not 0 <= start < end <= duration + 0.01 or end - start > 3.001:
        raise StickerConversionError("Выберите фрагмент продолжительностью до 3 секунд")
    factor = max(512 / width, 512 / height) * zoom
    scaled_w = math.ceil(width * factor / 2) * 2
    scaled_h = math.ceil(height * factor / 2) * 2
    left = round((scaled_w - 512) * x / 2) * 2
    top = round((scaled_h - 512) * y / 2) * 2
    filters = f"scale={scaled_w}:{scaled_h},crop=512:512:{left}:{top},setsar=1,format=yuva420p"
    if shape in {"circle", "rounded"}:
        distance = "(X-255.5)*(X-255.5)+(Y-255.5)*(Y-255.5)" if shape == "circle" else "pow(max(abs(X-255.5)-207.5,0),2)+pow(max(abs(Y-255.5)-207.5,0),2)"
        radius = 256 if shape == "circle" else 48
        filters += f",geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='if(lte({distance},{radius * radius}),255,0)'"
    _convert_with_quality_search(str(source), str(output), start, end - start, filters)
