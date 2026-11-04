import os

# Must be set before any application import: never load a developer's private config.
os.environ["PYTHON_DOTENV_DISABLED"] = "1"
os.environ["BOT_TOKEN"] = "123456:TEST_ONLY_NOT_A_REAL_TOKEN"
os.environ["API_SECRET_TOKEN"] = "test-secret"

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import storage
from backend.main import app
from backend.routers import studio, stickers
from tests.support import FakeTelegram


@pytest.fixture
def client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[TestClient, FakeTelegram, Path]]:
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    from backend.services.media.preview_cache import _items
    _items.clear()
    studio._link_sources.clear()
    studio._edit_sources.clear()
    studio._upload_sources.clear()
    fake = FakeTelegram()
    monkeypatch.setattr(stickers, "telegram", fake)
    monkeypatch.setattr(studio, "telegram", fake)
    with TestClient(app) as client:
        yield client, fake, tmp_path
