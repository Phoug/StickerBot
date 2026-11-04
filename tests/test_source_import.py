"""Content-based import works for galleries and public direct media links."""
from io import BytesIO
from pathlib import Path
import subprocess

import pytest
from PIL import Image

from backend.routers import studio
from tests.support import auth


@pytest.mark.parametrize("mime", ["application/octet-stream", "video/mp4", ""])
def test_photo_upload_recognizes_bytes_without_image_mime(client, mime):
    api, _, _ = client
    data = BytesIO()
    Image.new("RGB", (80, 40), "red").save(data, "PNG")
    response = api.post(
        "/api/studio/upload", files={"video": ("camera", data.getvalue(), mime)},
        headers=auth(),
    )
    assert response.status_code == 201
    assert response.json()["kind"] == "photo"
    assert (response.json()["width"], response.json()["height"]) == (80, 40)


def test_direct_video_link_imports_and_renders_original(client, monkeypatch):
    api, _, folder = client
    original = folder / "camera.mov"
    subprocess.run([
        "ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
        "color=red:size=120x80:rate=15", "-t", "0.5", "-c:v", "libx264",
        "-pix_fmt", "yuv420p", str(original),
    ], check=True)
    data = original.read_bytes()

    async def fetch(url: str, **kwargs: object) -> tuple[bytes, str]:
        assert not kwargs.get("image")
        return data, url

    monkeypatch.setattr(studio, "fetch_public", fetch)
    response = api.post(
        "/api/studio/link", json={"url": "https://cdn.example.com/camera.mov"},
        headers=auth(),
    )
    assert response.status_code == 201
    source = response.json()
    assert source["kind"] == "video"
    owned = studio.owned_media(source["id"], 7)
    assert Path(owned["render_path"]).read_bytes() == data
    result = api.post("/api/studio/render", json={
        "source_id": source["id"], "start": 0, "end": 0.4,
    }, headers=auth())
    assert result.status_code == 201


def test_repeat_upload_reuses_preparation_but_checks_owner_and_expiry(client, monkeypatch):
    from backend import storage

    api, _, _ = client
    calls = []
    original_prepare = studio.prepare

    def prepare(*args):
        calls.append(args[2])
        return original_prepare(*args)

    monkeypatch.setattr(studio, "prepare", prepare)
    data = BytesIO()
    Image.new("RGB", (40, 20), "blue").save(data, "PNG")

    def upload(user_id: int) -> dict:
        response = api.post("/api/studio/upload", files={
            "video": ("camera", data.getvalue(), "application/octet-stream"),
        }, headers=auth(user_id))
        assert response.status_code == 201
        return response.json()

    first = upload(7)
    assert upload(7)["id"] == first["id"]
    assert upload(8)["id"] != first["id"]
    assert calls == [7, 8]
    with storage.database() as db:
        db.execute("UPDATE media SET created_at=0 WHERE id=?", (first["id"],))
    assert upload(7)["id"] != first["id"]
    assert calls == [7, 8, 7]
