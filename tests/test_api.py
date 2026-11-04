import hashlib
from urllib.parse import urlencode
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from backend import storage
from backend.routers import studio, stickers
from backend.services.media import sticker_preview

from tests.support import auth, FakeTelegram

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


def test_delete_is_owner_scoped_and_removes_telegram_copy(client):
    api, fake, folder = client
    original = {"sticker_type": "regular", "stickers": [{"file_id": "original", "file_unique_id": "original", "emoji": "🙂"}]}
    fake.sets["Original"] = original
    pack = create(api, source="https://t.me/addstickers/Original").json()
    assert api.post(f"/api/packs/{pack['id']}/import", json={}, headers=auth()).status_code == 200
    media_path = folder / "published.webm"
    media_path.write_bytes(b"fixture")
    media = studio.register(media_path, 7, "render", 2)
    with storage.database() as db:
        db.execute("UPDATE media SET published_pack=? WHERE id=?", (pack["id"], media["id"]))
    route = f"/api/packs/{pack['id']}"
    assert api.delete(route).status_code == 401
    assert api.delete(route, headers=auth(8)).status_code == 404
    assert fake.deleted == []
    assert api.delete(route, headers=auth()).status_code == 204
    assert fake.deleted == [pack["name"]]
    assert fake.sets["Original"] == original
    assert api.get(route, headers=auth()).status_code == 404
    assert api.get("/api/packs", headers=auth()).json() == {"packs": []}
    assert api.get("/api/studio/media/"+media["id"], headers=auth()).status_code == 404


def test_delete_draft_and_retry_after_telegram_failure(client):
    api, fake, _ = client
    pack = create(api).json()
    route = f"/api/packs/{pack['id']}"
    fake.fail_delete = True
    # A draft has no confirmed Telegram set, so deleting it is purely local.
    assert api.delete(route, headers=auth()).status_code == 204
    pack = create(api).json()
    stickers.update_pack(pack["id"], status="ready")
    route = f"/api/packs/{pack['id']}"
    assert api.delete(route, headers=auth()).status_code == 502
    assert api.get("/api/packs", headers=auth()).json()["packs"][0]["id"] == pack["id"]
    fake.fail_delete = False
    # A missing Telegram set is normal after a lost delete response.
    assert api.delete(route, headers=auth()).status_code == 204
    assert api.delete(route, headers=auth()).status_code == 404


def seeded_pack(api, fake):
    pack = create(api).json()
    fake.sets[pack["name"]] = {"sticker_type": "regular", "stickers": [
        {"file_id": f"file-{i}", "file_unique_id": f"id-{i}", "emoji": "🙂",
         "thumbnail": {"file_id": f"thumb-{i}"}} for i in range(4)
    ]}
    stickers.update_pack(pack["id"], status="ready", count=4)
    return pack


def test_sticker_preview_and_cover_access_are_owner_scoped(client):
    api, fake, _ = client
    pack = seeded_pack(api, fake)
    root = f"/api/packs/{pack['id']}"
    assert api.get(root+"/cover", headers=auth()).content == b"test-image-bytes"
    assert api.get(root+"/stickers/id-1/file", headers=auth()).status_code == 200
    assert api.get(root+"/stickers/id-1/file", headers=auth(8)).status_code == 404
    assert api.get(root+"/cover", headers=auth(8)).status_code == 404
    assert api.get(root+"/stickers/foreign/file", headers=auth()).status_code == 404
    result = api.get(root, headers=auth()).json()
    assert [s["id"] for s in result["stickers"]] == ["id-0", "id-1", "id-2", "id-3"]


def test_delete_one_sticker_keeps_pack_and_other_stickers(client):
    api, fake, _ = client
    pack = seeded_pack(api, fake)
    root = f"/api/packs/{pack['id']}"
    assert api.delete(root+"/stickers/id-1", headers=auth(8)).status_code == 404
    assert api.delete(root+"/stickers/foreign", headers=auth()).status_code == 404
    assert fake.removed_stickers == []
    response = api.delete(root+"/stickers/id-1", headers=auth())
    assert response.status_code == 200
    assert response.json()["count"] == 3
    assert [s["id"] for s in response.json()["stickers"]] == ["id-0", "id-2", "id-3"]
    assert api.get(root, headers=auth()).status_code == 200


def test_reorder_validates_membership_and_is_idempotent(client):
    api, fake, _ = client
    pack = seeded_pack(api, fake)
    route = f"/api/packs/{pack['id']}/order"
    desired = ["id-3", "id-1", "id-0", "id-2"]
    assert api.put(route, json={"sticker_ids": desired}, headers=auth(8)).status_code == 404
    for invalid in (["id-0"], ["id-0"]*4, ["id-0", "id-1", "id-2", "foreign"]):
        assert api.put(route, json={"sticker_ids": invalid}, headers=auth()).status_code == 409
    response = api.put(route, json={"sticker_ids": desired}, headers=auth())
    assert response.status_code == 200
    assert [s["id"] for s in response.json()["stickers"]] == desired
    moves = len(fake.moves)
    assert api.put(route, json={"sticker_ids": desired}, headers=auth()).status_code == 200
    assert len(fake.moves) == moves


def test_partial_reorder_failure_can_be_retried(client):
    api, fake, _ = client
    pack = seeded_pack(api, fake)
    root = f"/api/packs/{pack['id']}"
    desired = ["id-3", "id-2", "id-1", "id-0"]
    fake.fail_move_at = 1
    assert api.put(root+"/order", json={"sticker_ids": desired}, headers=auth()).status_code == 502
    assert [s["id"] for s in api.get(root, headers=auth()).json()["stickers"]] == ["id-3", "id-0", "id-1", "id-2"]
    fake.fail_move_at = None
    response = api.put(root+"/order", json={"sticker_ids": desired}, headers=auth())
    assert [s["id"] for s in response.json()["stickers"]] == desired


@pytest.mark.parametrize("emoji", ["🥹", "❤️", "👨‍👩‍👧‍👦", "🇧🇾", "👍🏽", "1️⃣"])
def test_custom_emoji_reaches_telegram(client, emoji):
    api, fake, folder = client
    pack = create(api).json()
    path = folder / "custom.webm"
    path.write_bytes(b"custom-sticker")
    media = studio.register(path, 7, "render", 1)
    result = api.post(f"/api/studio/packs/{pack['id']}/publish",
                      json={"render_id": media["id"], "emoji": emoji}, headers=auth())
    assert result.status_code == 200
    assert fake.sets[pack["name"]]["stickers"][0]["emoji"] == emoji


@pytest.mark.parametrize("emoji", ["text", " ", "😂🔥", "123", "🔥hello"])
def test_invalid_emoji_is_rejected_before_upload(client, emoji):
    api, fake, _ = client
    pack = create(api).json()
    result = api.post(f"/api/studio/packs/{pack['id']}/publish",
                      json={"render_id": "unused", "emoji": emoji}, headers=auth())
    assert result.status_code == 422
    assert fake.created == 0


@pytest.mark.parametrize("user_id", [True, False, 0, -1])
def test_invalid_user_ids_are_rejected(client, user_id):
    api, _, _ = client
    assert api.get("/api/packs", headers=auth(user_id)).status_code == 401


def test_non_ascii_hash_is_unauthorized(client):
    api, _, _ = client
    assert api.get("/api/packs", headers={"X-Telegram-Init-Data": urlencode({"hash": "я"*64})}).status_code == 401


def test_render_preview_is_private_mp4_and_cleans_up(client, monkeypatch, tmp_path):
    api, _, folder = client
    source = folder / "render.webm"
    source.write_bytes(b"webm")
    media = studio.register(source, 7, "render", 1)
    preview_folder = tmp_path / "preview"
    preview_folder.mkdir()
    output = preview_folder / "preview.mp4"
    output.write_bytes(b"mp4")
    monkeypatch.setattr(sticker_preview, "make_video_preview", lambda data: output)
    route = "/api/studio/media/"+media["id"]+"?preview=true"
    assert api.get(route, headers=auth(8)).status_code == 404
    response = api.get(route, headers=auth())
    assert response.status_code == 200
    assert response.headers["content-type"] == "video/mp4"
    assert response.content == b"mp4"
    assert not preview_folder.exists()


def test_photo_upload_render_publish_and_replace_in_imported_copy(client):
    from io import BytesIO
    from PIL import Image
    api, fake, _ = client
    image = BytesIO()
    Image.new("RGBA", (800, 400), (180, 70, 120, 200)).save(image, "PNG")
    raw = image.getvalue()
    original = {"file_id":"old", "file_unique_id":"old", "emoji":"🥹"}
    fake.sets["Original"] = {"sticker_type":"regular", "stickers":[original.copy()]}
    pack = create(api, source="https://t.me/addstickers/Original").json()
    assert api.post(f"/api/packs/{pack['id']}/import", headers=auth()).status_code == 200
    upload = api.post("/api/studio/upload", files={"video":("photo.png",raw,"image/png")}, headers=auth())
    assert upload.status_code == 201
    source = upload.json()
    assert source["kind"] == "photo"
    assert api.get("/api/studio/media/"+source["id"],headers=auth()).headers["content-type"] == "image/png"
    response = api.post("/api/studio/render", json={"source_id":source["id"],"start":0,"end":1,"shape":"original"},headers=auth())
    assert response.status_code == 201
    result = response.json()
    media = api.get("/api/studio/media/"+result["id"]+"?preview=true",headers=auth())
    assert media.headers["content-type"] == "image/webp"
    sticker = Image.open(BytesIO(media.content))
    assert sticker.size == (512,256)
    assert sticker.getpixel((256,128))[3] == 200
    route = f"/api/studio/packs/{pack['id']}/publish"
    payload = {"render_id":result["id"],"replace_id":"old","emoji":"🥹"}
    assert api.post(route,json=payload,headers=auth()).status_code == 200
    assert api.post(route,json=payload,headers=auth()).status_code == 200
    current = fake.sets[pack["name"]]["stickers"]
    assert len(current) == 1
    assert current[0]["file_id"] != "old" and not current[0]["is_video"]
    assert fake.sets["Original"]["stickers"] == [original]


def test_emoji_edit_is_validated_and_owner_scoped(client):
    api, fake, _ = client
    pack = seeded_pack(api,fake)
    route = f"/api/packs/{pack['id']}/stickers/id-1/emoji"
    assert api.put(route,json={"emoji":"🔥"},headers=auth(8)).status_code == 404
    assert api.put(route,json={"emoji":"hello"},headers=auth()).status_code == 422
    assert api.put(route,json={"emoji":"👨‍👩‍👧‍👦"},headers=auth()).status_code == 200
    assert fake.sets[pack["name"]]["stickers"][1]["emoji"] == "👨‍👩‍👧‍👦"


def test_existing_photo_edit_uses_original_and_checks_membership(client, monkeypatch):
    from io import BytesIO
    from PIL import Image
    api, fake, _ = client
    pack = seeded_pack(api,fake)
    data = BytesIO();Image.new("RGB",(600,300),"red").save(data,"WEBP")
    async def file(file_id):
        assert file_id == "file-1"
        return data.getvalue(),"image/webp"
    monkeypatch.setattr(fake,"file",file)
    route = f"/api/studio/packs/{pack['id']}/stickers/id-1/edit"
    assert api.post(route,headers=auth(8)).status_code == 404
    result = api.post(route,headers=auth())
    assert result.status_code == 201 and result.json()["kind"] == "photo"
    assert api.post(route.replace("id-1","unknown"),headers=auth()).status_code == 404
    fake.sets[pack["name"]]["stickers"][1]["is_animated"] = True
    assert api.post(route,headers=auth()).status_code == 422


def test_cached_thumbnail_still_checks_owner_and_pack_membership(client, monkeypatch):
    api,fake,_ = client
    pack=seeded_pack(api,fake)
    calls=[]
    async def file(file_id):
        calls.append(file_id)
        return b"immutable-photo","image/webp"
    monkeypatch.setattr(fake,"file",file)
    root=f"/api/packs/{pack['id']}"
    for _ in range(2):
        assert api.get(root+"/thumbnail/thumb-1",headers=auth()).content == b"immutable-photo"
    assert calls == ["thumb-1"]
    assert api.get(root+"/thumbnail/thumb-1",headers=auth(8)).status_code == 404
    assert api.get(root+"/thumbnail/foreign",headers=auth()).status_code == 404


def test_bad_photo_has_useful_validation_error(client):
    api,_,_=client
    response=api.post("/api/studio/upload",files={"video":("bad.png",b"not an image","image/png")},headers=auth())
    assert response.status_code == 422
    assert "JPEG" in response.json()["detail"]


def test_video_edit_retains_private_original_until_expiry(client, monkeypatch):
    api,fake,folder = client
    pack=seeded_pack(api,fake)
    fake.sets[pack["name"]]["stickers"][1]["is_video"] = True
    preview_folder=folder/"temporary-preview"
    preview_folder.mkdir()
    preview=preview_folder/"preview.mp4";preview.write_bytes(b"browser-preview")
    monkeypatch.setattr(sticker_preview,"make_video_preview",lambda data: preview)
    monkeypatch.setattr(studio,"probe",lambda path: (1,512,288))
    response=api.post(f"/api/studio/packs/{pack['id']}/stickers/id-1/edit",headers=auth())
    assert response.status_code == 201
    media=studio.owned_media(response.json()["id"],7)
    from pathlib import Path
    original=Path(media["path"]).with_suffix(".original.webm")
    assert original.read_bytes() == b"test-image-bytes"
    seen=[]
    def render(path, output, *args):
        seen.append(path)
        output.write_bytes(b"rendered")
    monkeypatch.setattr(studio,"render",render)
    assert api.post("/api/studio/render",json={"source_id":media["id"],"start":0,"end":1},headers=auth()).status_code == 201
    assert seen == [original]
    with storage.database() as db:
        db.execute("UPDATE media SET created_at=0 WHERE id=?",(media["id"],))
    studio.cleanup_expired()
    assert not original.exists() and not Path(media["path"]).exists()


def test_viewer_and_editor_share_preview_and_reopening_editor_reuses_source(client, monkeypatch):
    api, fake, folder = client
    pack = seeded_pack(api, fake)
    fake.sets[pack['name']]['stickers'][1]['is_video'] = True
    calls = []
    def preview(data):
        calls.append(1)
        temp = folder/'shared-preview';temp.mkdir()
        output = temp/'preview.mp4';output.write_bytes(b'mp4-preview')
        return output
    monkeypatch.setattr(sticker_preview, 'make_video_preview', preview)
    monkeypatch.setattr(studio,'probe',lambda path: (1,512,288))
    root=f'/api/packs/{pack["id"]}/stickers/id-1'
    assert api.get(root+'/file',headers=auth()).content==b'mp4-preview'
    route=f'/api/studio/packs/{pack["id"]}/stickers/id-1/edit'
    first=api.post(route,headers=auth());assert first.status_code==201
    second=api.post(route,headers=auth());assert second.json()['id']==first.json()['id']
    assert len(calls)==1
    assert api.post(route,headers=auth(8)).status_code==404


def test_repeat_video_link_reuses_owned_source_and_skips_tiktok_photo_probe(client, monkeypatch):
    api,_,folder=client
    calls=[]
    def download(url,user_id):
        calls.append(user_id)
        path=folder/(str(user_id)+".mp4");path.write_bytes(b"fixture")
        return {**studio.register(path,user_id,"source",3),"kind":"video"}
    async def forbidden(url):raise AssertionError("A video URL must not probe photo HTML")
    monkeypatch.setattr(studio,"resolve_tiktok",forbidden)
    monkeypatch.setattr(studio,"download_source",download)
    payload={"url":"https://www.tiktok.com/@test/video/123"}
    first=api.post('/api/studio/link',json=payload,headers=auth()).json()
    second=api.post('/api/studio/link',json=payload,headers=auth()).json()
    assert first['id']==second['id'] and calls==[7]
    other=api.post('/api/studio/link',json=payload,headers=auth(8)).json()
    assert other['id']!=first['id'] and calls==[7,8]


def test_replacement_rejects_file_already_used_by_another_sticker(
    client: tuple[TestClient, FakeTelegram, Path],
) -> None:
    api, fake, folder = client
    pack = seeded_pack(api, fake)
    source = folder / "replacement.webp"
    source.write_bytes(b"already present")
    media = studio.register(source, 7, "render_photo", 0)
    existing_id = hashlib.sha256(b"already present").hexdigest()
    fake.sets[pack["name"]]["stickers"][1].update(
        file_id=existing_id, file_unique_id=existing_id,
    )
    old_id = fake.sets[pack["name"]]["stickers"][0]["file_unique_id"]
    response = api.post(
        f"/api/studio/packs/{pack['id']}/publish",
        json={"render_id": media["id"], "replace_id": old_id, "emoji": "🙂"},
        headers=auth(),
    )
    assert response.status_code == 409
    assert fake.sets[pack["name"]]["stickers"][0]["file_unique_id"] == old_id
    assert studio.owned_media(media["id"], 7)["published_pack"] is None


def test_replacement_recovers_lost_success_response(
    client: tuple[TestClient, FakeTelegram, Path], monkeypatch: pytest.MonkeyPatch,
) -> None:
    api, fake, folder = client
    pack = seeded_pack(api, fake)
    source = folder / "replacement.webp"
    source.write_bytes(b"new replacement")
    media = studio.register(source, 7, "render_photo", 0)
    old_id = fake.sets[pack["name"]]["stickers"][0]["file_unique_id"]
    original_call = fake.call
    lost = False

    async def call(method: str, **payload: object) -> object:
        nonlocal lost
        result = await original_call(method, **payload)
        if method == "replaceStickerInSet" and not lost:
            lost = True
            raise HTTPException(502, "Response lost after replacement")
        return result

    monkeypatch.setattr(fake, "call", call)
    route = f"/api/studio/packs/{pack['id']}/publish"
    payload = {"render_id": media["id"], "replace_id": old_id, "emoji": "🙂"}
    assert api.post(route, json=payload, headers=auth()).status_code == 502
    assert api.post(route, json=payload, headers=auth()).status_code == 200
    assert api.post(route, json=payload, headers=auth()).status_code == 200
    assert all(s["file_unique_id"] != old_id for s in fake.sets[pack["name"]]["stickers"])


def test_completed_publication_cannot_be_reused_for_another_target(
    client: tuple[TestClient, FakeTelegram, Path],
) -> None:
    api, fake, folder = client
    pack = seeded_pack(api, fake)
    source = folder / "replacement.webp"
    source.write_bytes(b"new replacement")
    media = studio.register(source, 7, "render_photo", 0)
    stickers_in_pack = fake.sets[pack["name"]]["stickers"]
    first_id, other_id = [s["file_unique_id"] for s in stickers_in_pack[:2]]
    route = f"/api/studio/packs/{pack['id']}/publish"
    payload = {"render_id": media["id"], "replace_id": first_id, "emoji": "🙂"}
    assert api.post(route, json=payload, headers=auth()).status_code == 200
    response = api.post(route, json={**payload, "replace_id": other_id}, headers=auth())
    assert response.status_code == 409
    assert any(s["file_unique_id"] == other_id for s in stickers_in_pack)
