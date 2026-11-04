"""Decode local photos, apply EXIF orientation, and keep alpha through editing."""
import warnings
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener

from backend.services.media.sticker_converter import StickerConversionError
from backend.services.media.studio_renderer import canvas_size


register_heif_opener(thumbnails=False, decode_threads=2)
PHOTO_FORMATS = {"JPEG", "PNG", "WEBP", "HEIF", "AVIF", "GIF", "BMP", "TIFF"}
PHOTO_FORMAT_HINT = "JPEG, PNG, WebP, HEIC/HEIF, AVIF, GIF, BMP или TIFF"


def is_photo(source: str | Path) -> bool:
    """Recognize photo bytes even when a gallery sends an unknown MIME type."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(source):
                return True
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise StickerConversionError("Фото должно быть не больше 40 мегапикселей") from exc
    except (UnidentifiedImageError, OSError, ValueError):
        return False


def normalize_photo(source: str | Path, output: str | Path) -> tuple[int, int]:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(source) as image:
                if image.format not in PHOTO_FORMATS:
                    raise StickerConversionError(f"Выберите фото {PHOTO_FORMAT_HINT}")
                if image.width * image.height > 40_000_000:
                    raise StickerConversionError("Фото должно быть не больше 40 мегапикселей")
                image = ImageOps.exif_transpose(image).convert("RGBA")
                image.thumbnail((2048, 2048), Image.Resampling.LANCZOS)
                image.save(output, "PNG", compress_level=1)
                return image.size
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise StickerConversionError(f"Не удалось открыть фото. Выберите {PHOTO_FORMAT_HINT}.") from exc


def render_photo(source, output, shape, zoom, x, y):
    with Image.open(source) as image:
        width, height = canvas_size(image.width, image.height, shape)
        factor = max(width / image.width, height / image.height) * zoom
        scaled = image.resize((round(image.width * factor), round(image.height * factor)), Image.Resampling.LANCZOS)
        left = round((scaled.width - width) * x)
        top = round((scaled.height - height) * y)
        result = scaled.crop((left, top, left + width, top + height))
        if shape in {"circle", "rounded"}:
            mask = Image.new("L", (width * 4, height * 4))
            draw = ImageDraw.Draw(mask)
            if shape == "circle":
                draw.ellipse((0, 0, width * 4 - 1, height * 4 - 1), fill=255)
            else:
                draw.rounded_rectangle((0, 0, width * 4 - 1, height * 4 - 1), radius=48 * 4, fill=255)
            # Multiplication preserves transparent pixels in the uploaded photo.
            from PIL import ImageChops
            result.putalpha(ImageChops.multiply(result.getchannel("A"), mask.resize(result.size, Image.Resampling.LANCZOS)))
        for quality in (95, 85, 70, 50):
            result.save(output, "WEBP", quality=quality, method=6)
            if output.stat().st_size <= 512 * 1024:
                return
        raise StickerConversionError("Не удалось уместить фото в 512 КБ")
