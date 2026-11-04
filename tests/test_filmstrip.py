"""Timeline Previews use private server-side frames rather than mobile decoders."""
from io import BytesIO
from pathlib import Path
import subprocess

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from backend import storage
from backend.routers import studio
from tests.support import FakeTelegram, auth


@pytest.fixture
def timeline(
    client: tuple[TestClient, FakeTelegram, Path],
) -> tuple[TestClient, str]:
    api, _, folder = client
    source = folder / "colors.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
        "color=red:size=120x80:rate=10:duration=1", "-f", "lavfi", "-i",
        "color=blue:size=120x80:rate=10:duration=1", "-filter_complex",
        "[0:v][1:v]concat=n=2:v=1:a=0", "-c:v", "libx264", "-pix_fmt",
        "yuv420p", str(source),
    ], check=True)
    media = studio.register(source, 7, "source", 2)
    return api, f"/api/studio/media/{media['id']}/filmstrip"


def test_filmstrip_samples_the_visible_window_and_pads_the_last_frame(
    timeline: tuple[TestClient, str],
) -> None:
    api, root = timeline
    for start, span, color in [(0, 1, "red"), (1, 1, "blue"), (1.95, 0.05, "blue")]:
        response = api.get(root, params={"start": start, "span": span}, headers=auth())
        assert response.status_code == 200, response.text
        assert response.headers["content-type"] == "image/jpeg"
        assert response.headers["cache-control"] == "private, no-store"
        with Image.open(BytesIO(response.content)) as sprite:
            assert sprite.size == (768, 64)
            for index in range(8):
                red, green, blue = sprite.getpixel((index * 96 + 48, 32))
                assert green < 30
                if color == "red":
                    assert red > 200 and blue < 30
                else:
                    assert blue > 200 and red < 30


def test_filmstrip_cache_still_checks_owner_and_expiry(
    timeline: tuple[TestClient, str], monkeypatch: pytest.MonkeyPatch,
) -> None:
    api, root = timeline
    calls = []
    original = studio.make_filmstrip

    def render(source: str | Path, start: float, span: float) -> bytes:
        calls.append((start, span))
        return original(source, start, span)

    monkeypatch.setattr(studio, "make_filmstrip", render)
    assert api.get(root).status_code == 401
    assert api.get(root, headers=auth(8)).status_code == 404
    first = api.get(root, headers=auth())
    assert first.status_code == 200
    assert api.get(root, headers=auth()).content == first.content
    assert calls == [(0, 2)]
    with storage.database() as db:
        db.execute("UPDATE media SET created_at=0")
    assert api.get(root, headers=auth()).status_code == 404
    assert calls == [(0, 2)]


@pytest.mark.parametrize("query", [
    "start=-1", "start=nan", "start=inf", "start=2", "start=1.999", "span=0",
    "span=0.001", "span=nan", "span=inf", "span=601",
])
def test_filmstrip_rejects_invalid_windows(
    timeline: tuple[TestClient, str], query: str,
) -> None:
    api, root = timeline
    assert api.get(root + "?" + query, headers=auth()).status_code == 422


def test_failed_filmstrip_can_retry_and_releases_capacity(
    timeline: tuple[TestClient, str], monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.services.media.sticker_converter import StickerConversionError

    api, root = timeline
    original = studio.make_filmstrip
    active = studio._processing.active

    def fail(source: str | Path, start: float, span: float) -> bytes:
        raise StickerConversionError("Could not decode")

    monkeypatch.setattr(studio, "make_filmstrip", fail)
    response = api.get(root, headers=auth())
    assert response.status_code == 422
    assert studio._processing.active == active
    monkeypatch.setattr(studio, "make_filmstrip", original)
    assert api.get(root, headers=auth()).status_code == 200
