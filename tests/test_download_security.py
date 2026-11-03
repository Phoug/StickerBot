import json
import io
import signal
import socket
import subprocess

import pytest

from backend.services.media import ytdlp
from backend.services.media.network import public_network
from backend.services.media import ytdlp_worker


def test_worker_response_stays_valid_json_when_downloader_prints_progress(monkeypatch, capsys):
    def noisy_download(job):
        print("[download] 100% of video.mp4")
        return {"id": "video"}

    monkeypatch.setattr(ytdlp_worker, "execute", noisy_download)
    monkeypatch.setattr(ytdlp_worker.sys, "stdin", io.StringIO('{"download": true}'))
    assert ytdlp_worker.main() == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"ok": True, "info": {"id": "video"}}
    assert "[download]" in captured.err


@pytest.mark.parametrize("url", ["http://127.0.0.1/a", "https://[::1]/a", "https://169.254.169.254/a",
                                 "https://[::ffff:127.0.0.1]/a", "https://localhost/a", "file:///tmp/a",
                                 "https://user:password@example.com/a", "https://example.com:8080/a"])
def test_legacy_download_rejects_nonpublic_urls_before_spawning(url, monkeypatch):
    monkeypatch.setattr(ytdlp.subprocess, "Popen", lambda *a, **kw: pytest.fail("Worker must not start"))
    with pytest.raises(ValueError):
        ytdlp.extract(url, {})


def test_worker_rejects_private_dns_and_direct_connections(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.1", 443))])
    with public_network():
        with pytest.raises(OSError, match="Private"):
            socket.getaddrinfo("public-name.example", 443)
        with socket.socket() as connection:
            with pytest.raises(OSError, match="Private"):
                connection.connect(("127.0.0.1", 8000))


def test_worker_checks_dns_each_time_including_rebinding(monkeypatch):
    answers = iter(["93.184.216.34", "192.168.1.2"])
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (next(answers), 443))])
    with public_network():
        assert socket.getaddrinfo("example.com", 443)[0][4][0] == "93.184.216.34"
        with pytest.raises(OSError):
            socket.getaddrinfo("example.com", 443)


def test_downloader_process_does_not_receive_credentials_or_proxies(monkeypatch):
    captured = {}
    class Process:
        returncode = 0
        def communicate(self, value, timeout):
            captured["job"] = json.loads(value)
            return json.dumps({"ok": True, "info": {"id": "safe"}}), None
    def spawn(*args, **kwargs):
        captured.update(kwargs)
        return Process()
    monkeypatch.setenv("BOT_TOKEN", "not-for-downloader")
    monkeypatch.setenv("API_SECRET_TOKEN", "also-private")
    monkeypatch.setenv("HTTPS_PROXY", "http://private-proxy:8888")
    monkeypatch.setattr(ytdlp.subprocess, "Popen", spawn)
    assert ytdlp.extract("https://example.com/video", {}) == {"id": "safe"}
    assert not {"BOT_TOKEN", "API_SECRET_TOKEN", "HTTPS_PROXY"} & captured["env"].keys()
    assert captured["env"]["PYTHON_DOTENV_DISABLED"] == "1"


def test_download_timeout_kills_and_reaps_the_entire_process_group(monkeypatch):
    killed = []
    class Process:
        pid = 54321
        calls = 0
        def communicate(self, *args, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise subprocess.TimeoutExpired("downloader", 1)
            return "", None
    process = Process()
    monkeypatch.setattr(ytdlp.subprocess, "Popen", lambda *a, **kw: process)
    monkeypatch.setattr(ytdlp.os, "killpg", lambda *args: killed.append(args))
    with pytest.raises(TimeoutError):
        ytdlp.extract("https://example.com/video", {})
    assert killed == [(54321, signal.SIGKILL)]
    assert process.calls == 2
