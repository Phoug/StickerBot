import pytest
from PIL import Image

from backend.services.media.photo_renderer import normalize_photo, render_photo
from backend.services.media.sticker_converter import StickerConversionError


def test_exif_orientation_is_applied_before_editing(tmp_path):
    source = tmp_path / "camera.jpg"
    exif = Image.Exif()
    exif[274] = 6
    Image.new("RGB", (800, 400), "orange").save(source, exif=exif)
    output = tmp_path / "source.png"
    assert normalize_photo(source, output) == (400, 800)
    with Image.open(output) as photo:
        assert photo.size == (400, 800)
        assert photo.getexif().get(274) is None


@pytest.mark.parametrize("shape", ["original", "square", "circle", "rounded"])
def test_photo_shapes_preserve_alpha_and_telegram_dimensions(tmp_path, shape):
    source = tmp_path / "source.png"
    Image.new("RGBA", (400, 800), (200, 70, 20, 160)).save(source)
    output = tmp_path / "sticker.webp"
    render_photo(source, output, shape, 1.5, .25, .75)
    with Image.open(output) as sticker:
        assert sticker.size == ((256, 512) if shape == "original" else (512, 512))
        assert sticker.getpixel((sticker.width//2, sticker.height//2))[3] == 160
        assert sticker.getpixel((0, 0))[3] == (0 if shape in {"circle", "rounded"} else 160)
    assert output.stat().st_size <= 512 * 1024


def test_large_photo_is_rejected_before_decoding_all_pixels(tmp_path):
    source = tmp_path / "large.png"
    Image.new("1", (6400, 6400)).save(source)
    with pytest.raises(StickerConversionError, match="40 мегапикселей"):
        normalize_photo(source, tmp_path / "output.png")
