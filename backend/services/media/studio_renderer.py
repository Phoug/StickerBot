import json
import math
import subprocess
from pathlib import Path
from backend.services.media.commands import run_command
from backend.services.media.sticker_converter import StickerConversionError, _convert_with_quality_search

def probe(path, details=False):
    try:
        result = run_command(
            ["ffprobe", "-v", "error", "-protocol_whitelist", "file,pipe", "-format_whitelist", "mov,matroska,webm,avi,mpeg,mpegvideo,ogg,asf,flv", "-select_streams", "v:0", "-show_entries",
             "stream=width,height,codec_name,pix_fmt,sample_aspect_ratio:stream_side_data=rotation:format=duration", "-of", "json", str(path)],
            capture_output=True, check=True, timeout=20)
        info = json.loads(result.stdout)
        stream = info["streams"][0]
        duration = float(info["format"]["duration"])
        width, height = int(stream["width"]), int(stream["height"])
        if not math.isfinite(duration) or not 0.05 <= duration <= 600 or not 1 <= width <= 4096 or not 1 <= height <= 4096:
            raise ValueError()
        return (duration, width, height, stream) if details else (duration, width, height)
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, IndexError) as exc:
        raise StickerConversionError("Нужно видео до 10 минут с разрешением не более 4096×4096") from exc

def normalize(source, output):
    _, width, height, stream = probe(source, details=True)
    compatible = (stream.get("codec_name")=="h264" and stream.get("pix_fmt")=="yuv420p"
                  and stream.get("sample_aspect_ratio","1:1") in {"1:1","N/A"}
                  and max(width,height)<=1280 and width%2==0 and height%2==0
                  and not any(item.get("rotation",0) for item in stream.get("side_data_list",[])))
    if compatible:
        try:
            run_command(["ffmpeg","-y","-v","error","-protocol_whitelist","file,pipe",
                            "-format_whitelist","mov,matroska,webm,avi,mpeg,mpegvideo,ogg,asf,flv",
                            "-i",str(source),"-map","0:v:0","-an","-c:v","copy","-movflags","+faststart",str(output)],
                           capture_output=True,check=True,timeout=60)
            if output.stat().st_size <= 50*1024*1024:
                return probe(output)[0]
        except (OSError, subprocess.SubprocessError):
            pass
    try:
        run_command(
            ["ffmpeg", "-y", "-v", "error", "-protocol_whitelist", "file,pipe", "-format_whitelist", "mov,matroska,webm,avi,mpeg,mpegvideo,ogg,asf,flv", "-i", str(source), "-map", "0:v:0", "-an",
             "-vf", "scale=w='min(1280,iw)':h='min(1280,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2,setsar=1",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "25", "-pix_fmt", "yuv420p",
             "-movflags", "+faststart", "-fs", "52428801", str(output)],
            capture_output=True, check=True, timeout=180)
    except (OSError, subprocess.SubprocessError) as exc:
        raise StickerConversionError("Не удалось подготовить видео для редактора") from exc
    if output.stat().st_size > 50 * 1024 * 1024:
        raise StickerConversionError("Подготовленное видео превышает 50 МБ")
    return probe(output)[0]

def canvas_size(width, height, shape):
    if shape == "original":
        factor = 512 / max(width, height)
        return max(2, round(width * factor / 2) * 2), max(2, round(height * factor / 2) * 2)
    return 512, 512


def render(source, output, start, end, shape, zoom, x, y):
    duration, width, height = probe(source)
    if not 0 <= start < end <= duration + 0.01 or not 0.05 <= end - start <= 3.001:
        raise StickerConversionError("Выберите фрагмент продолжительностью до 3 секунд")
    out_w, out_h = canvas_size(width, height, shape)
    factor = max(out_w / width, out_h / height) * zoom
    scaled_w = math.ceil(width * factor / 2) * 2
    scaled_h = math.ceil(height * factor / 2) * 2
    left = round((scaled_w - out_w) * x / 2) * 2
    top = round((scaled_h - out_h) * y / 2) * 2
    filters = f"scale={scaled_w}:{scaled_h},crop={out_w}:{out_h}:{left}:{top},setsar=1,format=yuva420p"
    if shape in {"circle", "rounded"}:
        distance = "(X-255.5)*(X-255.5)+(Y-255.5)*(Y-255.5)" if shape == "circle" else "pow(max(abs(X-255.5)-207.5,0),2)+pow(max(abs(Y-255.5)-207.5,0),2)"
        radius = 256 if shape == "circle" else 48
        filters += f",geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='if(lte({distance},{radius * radius}),alpha(X,Y),0)'"
    # Telegram video stickers are VP9; the native decoder drops their alpha.
    decoder = "libvpx-vp9" if Path(source).name.endswith(".original.webm") else None
    _convert_with_quality_search(str(source), str(output), start, end - start, filters, decoder)
