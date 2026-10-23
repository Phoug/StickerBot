import hashlib
import hmac
import json
import time
from pathlib import Path
from urllib.parse import urlencode

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from backend.config import BOT_TOKEN
from backend.main import app
from backend import storage
from backend.routers import studio, stickers

def auth(user_id=7):
    data = {"auth_date": str(int(time.time())), "user": json.dumps({"id": user_id, "first_name": "Test"})}
    check = "\n".join(f"{key}={value}" for key, value in sorted(data.items()))
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    data["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return {"X-Telegram-Init-Data": urlencode(data)}

class FakeTelegram:
    def __init__(self):
        self.sets = {}
        self.fail_add = False
        self.created = 0
        self.added = 0

    async def call(self, method, **payload):
        if method == "getMe":
            return {"username": "test_studio_bot"}
        if method == "getStickerSet":
            if payload["name"] not in self.sets:
                raise HTTPException(502, "Telegram: Bad Request: STICKERSET_INVALID")
            return self.sets[payload["name"]]
        if method == "createNewStickerSet":
            self.created += 1
            self.sets[payload["name"]] = {"sticker_type": "regular", "stickers": [self.sticker(s) for s in payload["stickers"]]}
            return True
        if method == "addStickerToSet":
            if self.fail_add:
                self.fail_add = False
                raise HTTPException(502, "Temporary import error")
            self.added += 1
            target = self.sets[payload["name"]]["stickers"]
            sticker = self.sticker(payload["sticker"])
            if sticker["file_id"] not in {s["file_id"] for s in target}:
                target.append(sticker)
            return True
        raise AssertionError(method)

    def sticker(self, input_sticker):
        file_id = input_sticker["sticker"]
        return {"file_id": file_id, "file_unique_id": file_id, "emoji": input_sticker["emoji_list"][0],
                "is_video": input_sticker["format"] == "video", "is_animated": input_sticker["format"] == "animated"}

    async def upload(self, user_id, path):
        file_id = hashlib.sha256(path.read_bytes()).hexdigest()
        return {"file_id": file_id, "file_unique_id": file_id}

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    monkeypatch.setattr(studio, "DATA_DIR", tmp_path)
    fake = FakeTelegram()
    monkeypatch.setattr(stickers, "telegram", fake)
    monkeypatch.setattr(studio, "telegram", fake)
    with TestClient(app) as client:
        yield client, fake, tmp_path

def create(client, **body):
    return client.post("/api/packs", json={"title": "Реакции", **body}, headers=auth())

def test_auth_and_pack_owner_isolation(client):
    api, fake, _ = client
    assert api.get("/api/packs").status_code == 401
    assert api.get("/api/packs", headers={"X-Telegram-Init-Data": "hash=wrong&auth_date=1"}).status_code == 401
    response = create(api)
    assert response.status_code == 201
    pack = response.json()
    assert pack["status"] == "draft"
    assert fake.created == 0
    assert api.get("/api/packs/"+pack["id"], headers=auth(8)).status_code == 404
    assert api.get("/api/packs", headers=auth(8)).json() == {"packs": []}
    assert len(api.get("/api/packs", headers=auth()).json()["packs"]) == 1

def test_import_resumes_without_duplicates(client):
    api, fake, _ = client
    fake.sets["Original"] = {"sticker_type": "regular", "stickers": [
        {"file_id": str(i), "file_unique_id": str(i), "emoji": "😂", "is_video": i % 2 == 0, "is_animated": False}
        for i in range(55)]}
    original = list(fake.sets["Original"]["stickers"])
    pack = create(api, source="https://t.me/addstickers/Original").json()
    fake.fail_add = True
    assert api.post(f"/api/packs/{pack['id']}/import", json={}, headers=auth()).status_code == 502
    assert len(fake.sets[pack["name"]]["stickers"]) == 50
    response = api.post(f"/api/packs/{pack['id']}/import", json={}, headers=auth())
    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["count"] == 55
    assert fake.created == 1
    assert len(fake.sets[pack["name"]]["stickers"]) == 55
    assert fake.sets["Original"]["stickers"] == original
    assert api.post(f"/api/packs/{pack['id']}/import", json={}, headers=auth()).status_code == 200
    assert fake.added == 5

def test_publish_is_owner_scoped_and_idempotent(client):
    api, fake, folder = client
    pack = create(api).json()
    path = folder / "fixture.webm"
    path.write_bytes(b"rendered test sticker")
    media = studio.register(path, 7, "render", 2)
    route = f"/api/studio/packs/{pack['id']}/publish"
    payload = {"render_id": media["id"], "emoji": "😂"}
    assert api.post(route, json=payload, headers=auth(8)).status_code == 404
    assert api.post(route, json=payload, headers=auth()).status_code == 200
    assert api.post(route, json=payload, headers=auth()).status_code == 200
    assert fake.created == 1 and fake.added == 0
    assert len(fake.sets[pack["name"]]["stickers"]) == 1

def test_media_access_expiry_and_url_validation(client):
    api, _, folder = client
    path = folder / "input.mp4"
    path.write_bytes(b"video")
    media = studio.register(path, 7, "source", 2)
    route = "/api/studio/media/"+media["id"]
    assert api.get(route, headers=auth()).content == b"video"
    assert api.get(route, headers=auth(8)).status_code == 404
    with storage.database() as db:
        db.execute("UPDATE media SET created_at=0 WHERE id=?", (media["id"],))
    assert api.get(route, headers=auth()).status_code == 404
    studio.cleanup_expired()
    with storage.database() as db:
        assert db.execute("SELECT COUNT(*) FROM media").fetchone()[0] == 0
    for url in ("https://127.0.0.1/video", "http://youtube.com/a", "https://youtube.com.evil.test/a", "file:///tmp/a"):
        assert api.post("/api/studio/link", json={"url": url}, headers=auth()).status_code == 422

def test_invalid_import_and_editor_settings(client):
    api, _, _ = client
    assert create(api, source="https://evil.test/addstickers/Test").status_code == 422
    assert create(api, title="   ").status_code == 422
    assert create(api, source="https://t.me/addemoji/Test").status_code == 422
    assert api.post("/api/studio/render", json={"source_id":"x", "start":0,"end":2,"shape":"triangle"}, headers=auth()).status_code == 422
    assert api.post("/api/studio/render", json={"source_id":"x", "start":0,"end":2,"zoom":10}, headers=auth()).status_code == 422
