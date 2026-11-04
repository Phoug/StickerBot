"""Private source streaming starts with ranges instead of a complete Blob."""
from urllib.parse import parse_qs, urlencode, urlsplit

from backend import storage
from backend.routers import studio
from tests.support import auth


def test_playback_ticket_streams_ranges_and_is_scoped(client):
    api, _, folder = client
    path = folder / "preview.mp4"
    path.write_bytes(b"0123456789")
    source = studio.register(path, 7, "source", 1)
    root = f"/api/studio/media/{source['id']}"
    assert api.post(root + "/playback", json={}).status_code == 401
    assert api.post(root + "/playback", json={}, headers=auth(8)).status_code == 404
    ticket = api.post(root + "/playback", json={}, headers=auth()).json()["url"]
    assert "initData" not in ticket and "TEST_ONLY" not in ticket
    response = api.get(ticket, headers={"Range": "bytes=2-5"})
    assert response.status_code == 206
    assert response.content == b"2345"
    assert response.headers["content-range"] == "bytes 2-5/10"
    assert response.headers["cache-control"] == "private, no-store"
    assert api.get(ticket.replace("user_id=7", "user_id=8")).status_code == 401
    path.write_bytes(b"another source")
    other = studio.register(path, 7, "source", 1)
    assert api.get(ticket.replace(source["id"], other["id"])).status_code == 401
    parts = urlsplit(ticket)
    query = parse_qs(parts.query)
    query["signature"] = ["я"]
    assert api.get(parts.path + "?" + urlencode(query, doseq=True)).status_code == 401
    with storage.database() as db:
        db.execute("UPDATE media SET created_at=0 WHERE id=?", (source["id"],))
    assert api.get(ticket).status_code == 404


def test_expired_or_forged_playback_ticket_fails(client, monkeypatch):
    api, _, folder = client
    path = folder / "preview.mp4"
    path.write_bytes(b"video")
    source = studio.register(path, 7, "source", 1)
    root = f"/api/studio/media/{source['id']}"
    ticket = api.post(root + "/playback", json={}, headers=auth()).json()["url"]
    assert api.get(ticket + "tampered").status_code == 401
    now = studio.time.time()
    monkeypatch.setattr(studio.time, "time", lambda: now + 3601)
    assert api.get(ticket).status_code == 401
