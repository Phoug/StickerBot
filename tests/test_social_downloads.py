"""Link routing and the chat bot's single-pass video delivery."""
import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot.handlers import media
from app.bot.localization import translator_for
from app.bot.services import video_service
from backend.routers import studio
from backend.services.media import downloader
from tests.support import auth


SOCIAL_URLS = [
    "https://www.twitch.tv/videos/123",
    "https://dai.ly/xyz",
    "https://www.pinterest.com/pin/123/",
    "https://pin.it/xyz",
    "https://www.bilibili.com/video/BV123/",
    "https://b23.tv/xyz",
    "https://bsky.app/profile/test.example/post/123",
    "https://streamable.com/xyz",
    "https://coub.com/view/xyz",
    "https://vk.com/video-1_2",
    "https://vkvideo.ru/video-1_2",
    "https://vk.ru/video-1_2",
]


@pytest.mark.parametrize("url", SOCIAL_URLS)
def test_public_video_links_reach_the_studio_downloader(client, monkeypatch, url: str) -> None:
    api, _, _ = client
    calls = []

    def download(link: str, user_id: int) -> dict:
        calls.append((link, user_id))
        return {"id": "source", "kind": "video", "duration": 1}

    async def photo(*args, **kwargs):
        pytest.fail("A supported video publication must not be treated as a photo")

    monkeypatch.setattr(studio, "download_source", download)
    monkeypatch.setattr(studio, "fetch_public", photo)
    response = api.post("/api/studio/link", json={"url": url}, headers=auth())
    assert response.status_code == 201
    assert response.json()["kind"] == "video"
    assert calls == [(url, 7)]


def test_download_uses_sanitized_publication_title(tmp_path: Path, monkeypatch) -> None:
    def extract(url: str, options: dict, *, download: bool) -> dict:
        assert download
        (tmp_path / "video.mp4").write_bytes(b"video")
        return {"title": "A / public: video", "extractor_key": "VK"}

    monkeypatch.setattr(downloader, "extract", extract)
    path, filename, mime = downloader.download_to_file(
        "https://vk.com/video-1_2", target_dir=tmp_path,
    )
    assert path.read_bytes() == b"video"
    assert filename == "A _ public_ video.mp4"
    assert mime == "video/mp4"


def test_bot_downloads_without_a_separate_metadata_request(monkeypatch) -> None:
    backend = SimpleNamespace(download_url_to_file=AsyncMock(), get_json=AsyncMock())
    status = SimpleNamespace(delete=AsyncMock(), edit_text=AsyncMock())
    sent = []

    async def download(url: str, folder: str, tr) -> tuple[str, Path, int]:
        path = Path(folder) / "video.mp4"
        path.write_bytes(b"public video")
        return "Title <tag>.mp4", path, 12

    async def deliver(**kwargs) -> None:
        sent.append(kwargs)
        assert Path(kwargs["document"].path).read_bytes() == b"public video"

    backend.download_url_to_file.side_effect = download
    message = SimpleNamespace(answer=AsyncMock(return_value=status), answer_document=deliver)
    monkeypatch.setattr(video_service, "backend_client", backend)
    asyncio.run(video_service.process_video_download(
        message, "https://vk.com/video-1_2", translator_for("ru"),
    ))
    backend.download_url_to_file.assert_awaited_once()
    backend.get_json.assert_not_awaited()
    assert "Title &lt;tag&gt;" in sent[0]["caption"]
    status.delete.assert_awaited_once()
    assert not Path(sent[0]["document"].path).exists()


def test_bot_accepts_a_telegram_text_link(monkeypatch) -> None:
    download = AsyncMock()
    monkeypatch.setattr(media, "process_video_download", download)
    message = SimpleNamespace(
        text="Посмотри видео", entities=[SimpleNamespace(type="text_link", url=SOCIAL_URLS[-1])],
    )
    tr = translator_for("ru")
    asyncio.run(media.url_handler(message, tr))
    download.assert_awaited_once_with(message, SOCIAL_URLS[-1], tr)


def test_unicode_download_title_fits_the_filesystem(tmp_path: Path, monkeypatch) -> None:
    def extract(url: str, options: dict, *, download: bool) -> dict:
        (tmp_path / "video.mp4").write_bytes(b"video")
        return {"title": "Видео 🎬 " * 50}

    monkeypatch.setattr(downloader, "extract", extract)
    _, filename, _ = downloader.download_to_file("https://vk.com/video-1_2", target_dir=tmp_path)
    destination = tmp_path / filename
    destination.write_bytes(b"downloaded")
    assert destination.read_bytes() == b"downloaded"
    assert len(filename.encode("utf-8")) < 255
