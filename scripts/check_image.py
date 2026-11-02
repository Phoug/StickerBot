"""Exercise a built API image with fake credentials and no external network."""
import argparse
import subprocess
import time
import uuid

PROBE = r'''
import os, subprocess, sys, tempfile, time, urllib.error, urllib.request
from pathlib import Path
from backend.services.media.studio_renderer import render
from backend.services.media.sticker_preview import make_video_preview
from backend.services.file_service import cleanup_files
import app.bot.bot
from backend.backup import backup_healthy

for route in ("/health", "/ready", "/app/"):
    with urllib.request.urlopen("http://127.0.0.1:8000" + route, timeout=5) as response:
        assert response.status == 200, route
try:
    urllib.request.urlopen("http://127.0.0.1:8000/api/packs", timeout=5)
except urllib.error.HTTPError as error:
    assert error.code == 401
else:
    raise AssertionError("Private API accepted a request without Telegram initData")
with tempfile.TemporaryDirectory() as folder:
    source, output = Path(folder)/"source.mp4", Path(folder)/"sticker.webm"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=green:s=320x240:r=25", "-t", "1", "-c:v", "libx264", "-threads", "2", str(source)], check=True)
    render(source, output, 0, .5, "circle", 1, .5, .5)
    assert 0 < output.stat().st_size <= 256*1024
    preview = make_video_preview(output.read_bytes())
    try:
        assert preview.stat().st_size > 0
    finally:
        cleanup_files(preview.parent)
environment = {key:value for key,value in os.environ.items() if key not in {"BOT_TOKEN", "API_SECRET_TOKEN"}}
subprocess.run([sys.executable,"-m","backend.backup","create","--output","/app/backups/manual.sqlite3"],env=environment,check=True)
subprocess.run([sys.executable,"-m","backend.backup","restore","/app/backups/manual.sqlite3","--data-dir","/tmp/recovery"],env=environment,check=True)
daemon = subprocess.Popen([sys.executable,"-m","backend.backup","daemon","--backup-dir","/app/backups/scheduled","--interval","1","--retention","2"],env=environment)
try:
    deadline = time.monotonic()+15
    while time.monotonic()<deadline:
        if len(list(Path("/app/backups/scheduled").glob("stickerbot-*.sqlite3")))==2:
            break
        time.sleep(.2)
    assert backup_healthy("/app/backups/scheduled",10)
finally:
    daemon.terminate()
    assert daemon.wait(timeout=5)==0
print("Image HTTP, storage, bot imports, VP9/H.264 and credential-free backup/recovery checks passed")
'''


def check_image(image):
    name = "stickerbot-check-" + uuid.uuid4().hex[:12]
    try:
        subprocess.run([
            "docker", "run", "--detach", "--name", name, "--network", "none", "--init", "--read-only",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true", "--pids-limit", "256",
            "--tmpfs", "/tmp:rw,nosuid,nodev,size=256m,mode=1777",
            "--tmpfs", "/app/data:rw,nosuid,nodev,size=32m,uid=65532,gid=65532,mode=0700",
            "--tmpfs", "/app/backups:rw,nosuid,nodev,size=32m,uid=65532,gid=65532,mode=0700",
            "-e", "PYTHON_DOTENV_DISABLED=1", "-e", "BOT_TOKEN=123456:IMAGE_TEST_ONLY",
            "-e", "API_SECRET_TOKEN=image-check-only", image,
        ], check=True, stdout=subprocess.DEVNULL)
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            result = subprocess.run(["docker", "exec", name, "python3", "-c",
                                     "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/ready',timeout=2)"],
                                    capture_output=True)
            if result.returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError("Image did not become ready within 60 seconds")
        subprocess.run(["docker", "exec", name, "python3", "-c", PROBE], check=True)
    except Exception:
        subprocess.run(["docker", "logs", "--tail", "100", name], check=False)
        raise
    finally:
        subprocess.run(["docker", "rm", "--force", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image")
    check_image(parser.parse_args().image)
