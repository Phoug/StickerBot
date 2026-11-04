"""Local visual QA fixture. No real credentials, Telegram requests or user files.

Run from the project root: .venv/Scripts/python tests/preview_server.py
Open http://127.0.0.1:8766/ for a phone-sized preview, /app/ for full width.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["PYTHON_DOTENV_DISABLED"] = "1"
os.environ["BOT_TOKEN"] = "123456:VISUAL_QA_ONLY"
os.environ["API_SECRET_TOKEN"] = "visual-qa-only"
workspace = tempfile.TemporaryDirectory(prefix="sticker_visual_qa_")
os.environ["DATA_DIR"] = workspace.name

import uvicorn
from fastapi.responses import HTMLResponse
from starlette.routing import Route
from backend.main import app
from backend.routers import stickers, studio
from backend.security import mini_app_user
from backend.storage import initialize, database
from tests.support import FakeTelegram, auth


class PreviewTelegram(FakeTelegram):
    def __init__(self):
        super().__init__()
        self.files = {}

    async def upload(self, user_id, path):
        result = await super().upload(user_id, path)
        self.files[result["file_id"]] = (path.read_bytes(), "image/webp" if path.suffix == ".webp" else "video/webm")
        return result

    async def file(self, file_id):
        if file_id in self.files:
            return self.files[file_id]
        if file_id == "video-fixture":
            return video_sticker.read_bytes(), "video/webm"
        if file_id.startswith("image-"):
            return photo.read_bytes(), "image/png"
        svg = '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><text x="50" y="70" font-size="60" text-anchor="middle">🙂</text></svg>'
        return svg.encode(), "image/svg+xml"


fake = PreviewTelegram()
stickers.telegram = studio.telegram = fake
app.dependency_overrides[mini_app_user] = lambda: {"id": 7, "first_name": "Preview"}
initialize()
with database() as db:
    db.execute("INSERT INTO packs(id,user_id,name,title,status,count,created_at) VALUES (?,?,?,?,?,?,?)", ("preview-pack",7,"preview_by_bot","Наши реакции","ready",12,1))
fake.sets["preview_by_bot"]={"sticker_type":"regular","stickers":[{"file_id":f"image-{i}","file_unique_id":f"sample-{i}","emoji":["🙂","😂","😎","🔥"][i%4],"thumbnail":{"file_id":f"thumb-{i}"}} for i in range(12)]}
source = Path(workspace.name) / "sample.mp4"
subprocess.run([
    "ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
    "testsrc2=size=640x360:rate=30", "-t", "6", "-c:v", "libx264",
    "-pix_fmt", "yuv420p", str(source),
], check=True)

from PIL import Image, ImageDraw
photo = Path(workspace.name) / "photo.png"
art = Image.new("RGBA", (800, 500), (55, 87, 120, 255))
draw = ImageDraw.Draw(art)
draw.ellipse((210, 60, 590, 440), fill=(244, 183, 109, 255))
draw.ellipse((305, 180, 335, 210), fill="#333333")
draw.ellipse((465, 180, 495, 210), fill="#333333")
draw.arc((330, 220, 470, 340), 10, 170, fill="#333333", width=12)
art.save(photo)
from backend.services.media.studio_renderer import render
video_sticker = Path(workspace.name) / "video.webm"
render(source, video_sticker, 0, 1, "original", 1, .5, .5)
fake.sets["preview_by_bot"]["stickers"][0].update(file_id="video-fixture", is_video=True)



def preview_download(url, user_id):
    copy = Path(workspace.name) / "copy.mp4"
    copy.write_bytes(source.read_bytes())
    return studio.register(copy, user_id, "source", 6)


studio.download_source = preview_download

MOCK_SDK = """<script>
window.Telegram={WebApp:{initData:'visual-qa',ready(){},expand(){},
viewportStableHeight:window.innerHeight,safeAreaInset:{top:44,bottom:24,left:0,right:0},contentSafeAreaInset:{top:56,bottom:0,left:0,right:0},
setHeaderColor(){},setBackgroundColor(){},onEvent(){},
BackButton:{show(){},hide(){},onClick(fn){window.qaBack=fn;},offClick(fn){if(window.qaBack===fn)window.qaBack=null;}},HapticFeedback:{notificationOccurred(){}}}};
</script>"""


async def preview_index(request):
    html = (ROOT / "app/webapp/index.html").read_text(encoding="utf-8")
    sdk = MOCK_SDK.replace("'visual-qa'", repr(auth()["X-Telegram-Init-Data"]))
    html = html.replace('<script src="https://telegram.org/js/telegram-web-app.js"></script>', sdk)
    html = html.replace('</body>', '''<div style="position:fixed;top:0;left:0;right:0;height:100px;background:#1f1f1f;z-index:100;pointer-events:none;font:600 14px sans-serif;color:white"><div style="padding:10px 26px">21:09 <span style="float:right">▰ 26%</span></div><div style="display:flex;justify-content:space-between;padding:12px 16px"><span style="background:#404040;border-radius:24px;padding:8px 14px">✕ Close</span><span style="background:#404040;border-radius:24px;padding:8px 14px">⌄ ···</span></div></div><div style="position:fixed;bottom:6px;left:35%;width:30%;height:4px;background:#ddd;border-radius:4px;z-index:100;pointer-events:none"></div></body>''')
    return HTMLResponse(html)


async def preview_phone(request):
    compact = request.query_params.get("size") == "compact"
    width, height = (360, 560) if compact else (390, 700)
    return HTMLResponse(f'''<!doctype html><html><head><title>Sticker Studio · Phone preview</title></head>
    <body style="margin:0;background:#151515;display:flex;justify-content:center;padding:8px;box-sizing:border-box">
    <iframe title="Telegram Mini App preview" src="/app/" style="width:{width}px;height:{height}px;border:1px solid #404040;border-radius:18px"></iframe>
    </body></html>''')


app.router.routes.insert(0, Route("/app/", preview_index))
app.router.routes.insert(0, Route("/", preview_phone))

if __name__ == "__main__":
    try:
        uvicorn.run(app, host="127.0.0.1", port=8766)
    finally:
        workspace.cleanup()
