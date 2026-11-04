"""Custom Pack addresses stay valid, available and owner-scoped."""
import pytest
from fastapi import HTTPException

from backend.routers import stickers, studio
from tests.support import auth


def test_name_configuration_and_auth(client):
    api, _, _ = client
    assert api.get("/api/packs/name-availability").status_code == 401
    result = api.get("/api/packs/name-availability", headers=auth()).json()
    assert result == {
        "name": None, "suffix": "_by_test_studio_bot",
        "max_length": 45, "available": None,
    }


@pytest.mark.parametrize("name", ["1first", "_first", "hello__world", "hello_", "привет", "a-b", "a b", "a" * 46])
def test_custom_name_rejects_telegram_incompatible_values(client, name):
    api, _, _ = client
    assert api.get("/api/packs/name-availability", params={"short_name": name}, headers=auth()).status_code == 422
    assert api.post("/api/packs", json={"title": "Pack", "short_name": name}, headers=auth()).status_code == 422


def test_custom_name_is_reserved_case_insensitively_and_blank_generates(client):
    api, fake, _ = client
    name = "Photos_2026"
    check = api.get("/api/packs/name-availability", params={"short_name": name}, headers=auth()).json()
    assert check["available"] is True
    response = api.post("/api/packs", json={"title": "Pack", "short_name": name}, headers=auth())
    assert response.status_code == 201
    assert response.json()["name"] == name + "_by_test_studio_bot"
    assert fake.created == 0
    assert api.get("/api/packs/name-availability", params={"short_name": name.lower()}, headers=auth(8)).json()["available"] is False
    assert api.post("/api/packs", json={"title": "Pack", "short_name": name.lower()}, headers=auth(8)).status_code == 409
    assert api.post("/api/packs", json={"title": "Pack", "short_name": "  "}, headers=auth()).json()["name"].startswith("s")


def test_creation_rechecks_name_after_live_check(client):
    api, fake, _ = client
    query = {"short_name": "cats"}
    assert api.get("/api/packs/name-availability", params=query, headers=auth()).json()["available"] is True
    fake.sets["cats_by_test_studio_bot"] = {"stickers": []}
    assert api.get("/api/packs/name-availability", params=query, headers=auth()).json()["available"] is False
    assert api.post("/api/packs", json={"title": "Pack", **query}, headers=auth()).status_code == 409


def test_telegram_failures_never_mean_name_is_free(client, monkeypatch):
    api, fake, _ = client
    original = fake.call

    async def unavailable(method, **payload):
        if method == "getStickerSet":
            raise HTTPException(502, "Telegram temporarily unavailable")
        return await original(method, **payload)

    monkeypatch.setattr(fake, "call", unavailable)
    assert api.get("/api/packs/name-availability", params={"short_name": "cats"}, headers=auth()).status_code == 502
    assert api.post("/api/packs", json={"title": "Pack", "short_name": "cats"}, headers=auth()).status_code == 502


def test_custom_address_also_applies_to_imported_copy(client):
    api, fake, _ = client
    fake.sets["Original"] = {"sticker_type": "regular", "stickers": [fake.sticker({
        "sticker": "original", "format": "static", "emoji_list": ["🙂"],
    })]}
    response = api.post("/api/packs", json={
        "title": "Copy", "short_name": "my_copy", "source": "https://t.me/addstickers/Original",
    }, headers=auth())
    assert response.status_code == 201
    pack = response.json()
    assert pack["name"] == "my_copy_by_test_studio_bot"
    assert api.post(f"/api/packs/{pack['id']}/import", headers=auth()).status_code == 200


def test_draft_publication_never_adds_to_an_occupied_address(client):
    api, fake, folder = client
    pack = api.post("/api/packs", json={"title": "Pack", "short_name": "cats"}, headers=auth()).json()
    foreign = fake.sticker({"sticker": "foreign", "format": "static", "emoji_list": ["🙂"]})
    fake.sets[pack["name"]] = {"stickers": [foreign]}
    path = folder / "sticker.webp"
    path.write_bytes(b"new sticker")
    media = studio.register(path, 7, "render_photo", 0)
    response = api.post(f"/api/studio/packs/{pack['id']}/publish", json={
        "render_id": media["id"], "emoji": "🙂",
    }, headers=auth())
    assert response.status_code == 409
    assert fake.sets[pack["name"]]["stickers"] == [foreign]
    assert fake.added == 0


def test_empty_draft_cannot_delete_an_occupied_remote_address(client):
    api, fake, _ = client
    pack = api.post("/api/packs", json={"title": "Pack", "short_name": "cats"}, headers=auth()).json()
    foreign = {"stickers": [fake.sticker({"sticker": "foreign", "format": "static", "emoji_list": ["🙂"]})]}
    fake.sets[pack["name"]] = foreign
    assert api.delete(f"/api/packs/{pack['id']}", headers=auth()).status_code == 204
    assert fake.deleted == []
    assert fake.sets[pack["name"]] == foreign


def test_initial_import_cannot_add_to_an_occupied_address(client):
    api, fake, _ = client
    source = fake.sticker({"sticker": "source", "format": "static", "emoji_list": ["🙂"]})
    fake.sets["Original"] = {"sticker_type": "regular", "stickers": [source]}
    pack = api.post("/api/packs", json={
        "title": "Copy", "short_name": "cats", "source": "Original",
    }, headers=auth()).json()
    foreign = fake.sticker({"sticker": "foreign", "format": "static", "emoji_list": ["🙂"]})
    fake.sets[pack["name"]] = {"stickers": [foreign]}
    assert api.post(f"/api/packs/{pack['id']}/import", headers=auth()).status_code == 409
    assert fake.sets[pack["name"]]["stickers"] == [foreign]


def test_custom_publication_recovers_a_lost_create_response(client, monkeypatch):
    api, fake, folder = client
    pack = api.post("/api/packs", json={"title": "Pack", "short_name": "cats"}, headers=auth()).json()
    path = folder / "sticker.webp"
    path.write_bytes(b"new sticker")
    media = studio.register(path, 7, "render_photo", 0)
    original = fake.call
    lost = False

    async def lose_response(method, **payload):
        nonlocal lost
        result = await original(method, **payload)
        if method == "createNewStickerSet" and not lost:
            lost = True
            raise HTTPException(502, "Lost create response")
        return result

    monkeypatch.setattr(fake, "call", lose_response)
    route = f"/api/studio/packs/{pack['id']}/publish"
    payload = {"render_id": media["id"], "emoji": "🙂"}
    assert api.post(route, json=payload, headers=auth()).status_code == 502
    assert api.post(route, json=payload, headers=auth()).status_code == 200
    assert fake.created == 1 and fake.added == 0


def test_custom_import_recovers_a_lost_initial_create_response(client, monkeypatch):
    api, fake, _ = client
    source = fake.sticker({"sticker": "source", "format": "static", "emoji_list": ["🙂"]})
    fake.sets["Original"] = {"sticker_type": "regular", "stickers": [source]}
    pack = api.post("/api/packs", json={
        "title": "Copy", "short_name": "cats", "source": "Original",
    }, headers=auth()).json()
    original = fake.call
    lost = False

    async def lose_response(method, **payload):
        nonlocal lost
        result = await original(method, **payload)
        if method == "createNewStickerSet" and not lost:
            lost = True
            raise HTTPException(502, "Lost create response")
        return result

    monkeypatch.setattr(fake, "call", lose_response)
    route = f"/api/packs/{pack['id']}/import"
    assert api.post(route, headers=auth()).status_code == 502
    assert api.post(route, headers=auth()).status_code == 200
    assert fake.created == 1 and fake.added == 0
