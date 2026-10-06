import asyncio
import logging
import os
import re
import tempfile
from html import escape as html_quote
from pathlib import Path
from urllib.parse import unquote, urlparse

import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import FSInputFile, Message
from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("telegram_bot")

load_dotenv()

API_BASE_URL = os.getenv("VIDEO_API_URL", "http://127.0.0.1:8000").rstrip("/")
BOT_TOKEN = os.getenv("BOT_TOKEN")

MAX_TELEGRAM_DOWNLOAD_SIZE = 20 * 1024 * 1024
MAX_TELEGRAM_UPLOAD_SIZE = 50 * 1024 * 1024
HTTP_TIMEOUT = 300
CHUNK_SIZE = 1024 * 1024

URL_PATTERN = re.compile(r"https?://[^\s]+", re.IGNORECASE)

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is not set")

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)

dp = Dispatcher()
http_session: aiohttp.ClientSession | None = None


def extract_url(text: str) -> str | None:
    match = URL_PATTERN.search(text)
    if not match:
        return None

    url = match.group(0).rstrip(".,!?;:)]}>")
    parsed = urlparse(url)

    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None

    return url


def parse_time(value: str) -> float:
    value = value.strip()
    try:
        if ":" not in value:
            result = float(value)
        else:
            parts = value.split(":")
            if len(parts) == 2:
                result = float(parts[0]) * 60 + float(parts[1])
            elif len(parts) == 3:
                result = float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
            else:
                raise ValueError
    except (TypeError, ValueError):
        raise ValueError from None

    if result < 0:
        raise ValueError

    return result


def parse_sticker_args(text: str | None) -> tuple[float, float | None]:
    if not text:
        return 0.0, None

    clean_text = text.strip()
    if not clean_text.startswith("/sticker"):
        return 0.0, None

    first_line = clean_text.splitlines()[0]
    parts = first_line.split()

    arguments = parts[1:]
    if len(arguments) > 2:
        raise ValueError("Usage: <code>/sticker</code>")

    start = 0.0
    end = None

    if len(arguments) >= 1:
        start = parse_time(arguments[0])
    if len(arguments) == 2:
        end = parse_time(arguments[1])

    if end is not None and end <= start:
        raise ValueError("Invalid time interval: end time must be greater than start time.")

    return start, end


def format_size(size: int) -> str:
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / 1024 / 1024:.1f} MB"


def get_content_disposition_filename(header: str | None) -> str | None:
    if not header:
        return None

    match = re.search(r"filename\*=UTF-8''([^;]+)", header, re.IGNORECASE)
    if match:
        return unquote(match.group(1).strip())

    match = re.search(r'filename="([^"]+)"', header, re.IGNORECASE)
    if match:
        return match.group(1)

    return None


async def get_http_session() -> aiohttp.ClientSession:
    global http_session
    if http_session is None or http_session.closed:
        timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT)
        connector = aiohttp.TCPConnector(limit=20, ttl_dns_cache=300)
        http_session = aiohttp.ClientSession(
            timeout=timeout,
            connector=connector,
        )
    return http_session


async def close_http_session() -> None:
    global http_session
    if http_session is not None:
        await http_session.close()
        http_session = None


async def api_json_get(endpoint: str, params: dict) -> dict:
    session = await get_http_session()
    try:
        async with session.get(f"{API_BASE_URL}{endpoint}", params=params) as resp:
            if resp.status == 200:
                return await resp.json()

            error_payload = await resp.json()
            detail = error_payload.get("detail", "Server error")
            logger.error("API GET Error [%s]: %s", resp.status, detail)
            raise RuntimeError("Failed to fetch video information.")
    except aiohttp.ClientError as exc:
        logger.error("HTTP Request Exception: %s", exc)
        raise RuntimeError("Backend service connection error.") from exc


async def download_url_to_file(url: str, output_dir: str) -> tuple[str, Path, int]:
    session = await get_http_session()
    params = {"url": url, "as_attachment": "true"}

    try:
        async with session.get(f"{API_BASE_URL}/download", params=params) as resp:
            if resp.status != 200:
                logger.error("API Download Error [%s]", resp.status)
                raise RuntimeError("Failed to download video from the provided URL.")

            filename = (
                get_content_disposition_filename(resp.headers.get("Content-Disposition"))
                or "video.mp4"
            )
            if not Path(filename).suffix:
                filename = f"{filename}.mp4"

            safe_filename = Path(filename).name
            output_path = Path(output_dir) / safe_filename
            total_size = 0

            with open(output_path, "wb") as file:
                async for chunk in resp.content.iter_chunked(CHUNK_SIZE):
                    total_size += len(chunk)
                    if total_size > MAX_TELEGRAM_UPLOAD_SIZE:
                        raise RuntimeError(
                            "Video size exceeds Telegram limit (50 MB)."
                        )
                    file.write(chunk)

            return safe_filename, output_path, total_size
    except aiohttp.ClientError as exc:
        logger.error("HTTP Download Exception: %s", exc)
        raise RuntimeError("Network error while downloading file.") from exc


async def api_upload_sticker(input_path: str, start: float, end: float | None) -> bytes:
    session = await get_http_session()
    form = aiohttp.FormData()

    with open(input_path, "rb") as file:
        form.add_field(
            "video",
            file,
            filename=Path(input_path).name,
            content_type="application/octet-stream",
        )
        form.add_field("start", str(start))
        if end is not None:
            form.add_field("end", str(end))

        try:
            async with session.post(f"{API_BASE_URL}/convert/sticker", data=form) as resp:
                if resp.status != 200:
                    try:
                        error_payload = await resp.json()
                        detail = error_payload.get("detail", "Server processing error")
                    except Exception:
                        detail = "Server processing error"
                    logger.error("API Sticker Error [%s]: %s", resp.status, detail)
                    raise RuntimeError(f"Conversion failed: {detail}")
                return await resp.read()
        except aiohttp.ClientError as exc:
            logger.error("HTTP Sticker Upload Exception: %s", exc)
            raise RuntimeError("Network error during sticker conversion.") from exc


async def download_telegram_file(message: Message, output_path: str) -> str:
    target = message.video or message.document
    if not target:
        raise ValueError("Message does not contain a video file.")

    if target.file_size and target.file_size > MAX_TELEGRAM_DOWNLOAD_SIZE:
        raise ValueError("File exceeds Telegram bot download limit (20 MB).")

    telegram_file = await bot.get_file(target.file_id)
    if not telegram_file.file_path:
        raise RuntimeError("Failed to retrieve Telegram file path.")

    await bot.download_file(telegram_file.file_path, destination=output_path)
    return getattr(target, "file_name", "video.mp4") or "video.mp4"


async def process_sticker_generation(
    target_message: Message,
    reply_to_msg: Message,
    start: float,
    end: float | None,
):
    status_message = await reply_to_msg.answer("Downloading video from Telegram...")

    with tempfile.TemporaryDirectory(prefix="sticker_work_") as temp_dir:
        input_path = Path(temp_dir) / "input.mp4"
        output_path = Path(temp_dir) / "sticker.webm"

        try:
            await download_telegram_file(target_message, str(input_path))
            await status_message.edit_text("Converting to Telegram video sticker...")

            output_data = await api_upload_sticker(str(input_path), start, end)
            output_path.write_bytes(output_data)

            output_size = output_path.stat().st_size
            await status_message.edit_text(f"Sticker ready!\nSize: {format_size(output_size)}")

            await reply_to_msg.answer_document(
                document=FSInputFile(output_path, filename="sticker.webm"),
                caption="Here is your video sticker.",
            )
            await status_message.delete()

        except Exception as exc:
            logger.exception("Error during sticker creation:")
            error_msg = str(exc) if isinstance(exc, (ValueError, RuntimeError)) else "Failed to create sticker."
            try:
                await status_message.edit_text(f"Error: {html_quote(error_msg)}")
            except Exception:
                pass


async def process_video_download(message: Message, url: str):
    status_message = await message.answer("Analyzing link...")

    try:
        info = await api_json_get("/info", {"url": url})

        title = html_quote(info.get("title") or "Video")
        uploader = html_quote(info.get("uploader") or "")
        source = html_quote(info.get("extractor_key") or info.get("extractor") or "Unknown")

        lines = [f"<b>{title}</b>", f"Source: {source}"]
        if uploader:
            lines.append(f"Author: {uploader}")
        lines.append("\nDownloading...")

        await status_message.edit_text("\n".join(lines))

        with tempfile.TemporaryDirectory(prefix="telegram_video_") as temp_dir:
            filename, output_path, size = await download_url_to_file(url, temp_dir)

            if size > MAX_TELEGRAM_UPLOAD_SIZE:
                raise RuntimeError("Downloaded video exceeds Telegram upload limit (50 MB).")

            await message.answer_document(
                document=FSInputFile(output_path, filename=filename),
                caption=f"<b>{title}</b>\n{format_size(size)}",
            )

        await status_message.delete()

    except Exception as exc:
        logger.exception("Error downloading video from link:")
        error_msg = str(exc) if isinstance(exc, RuntimeError) else "Failed to download video from the link."
        try:
            await status_message.edit_text(f"Error: {html_quote(error_msg)}")
        except Exception:
            pass


@dp.message(CommandStart())
async def start_handler(message: Message):
    await message.answer(
        "<b>Video Downloader & Sticker Bot</b>\n\n"
        "Send a video link to download it in original quality.\n\n"
        "<b>Supported platforms:</b>\n"
        "YouTube, TikTok, Instagram, X/Twitter.\n\n"
        "You can also upload a video file directly with <code>/sticker</code> in the caption, "
        "or reply to an existing video with <code>/sticker</code>."
    )


@dp.message(Command("help"))
async def help_handler(message: Message):
    await message.answer(
        "<b>Available Commands:</b>\n\n"
        "<code>/start</code> — Bot overview\n"
        "<code>/help</code> — Command list\n"
        "<code>/sticker</code> — Convert video to a video sticker\n\n"
        "Or simply send a link to download a video."
    )


@dp.message(Command("sticker"))
async def sticker_command_handler(message: Message):
    target_message = None

    if message.video or message.document:
        target_message = message
    elif message.reply_to_message and (message.reply_to_message.video or message.reply_to_message.document):
        target_message = message.reply_to_message

    if not target_message:
        await message.answer("Please send a video with <code>/sticker</code> in caption or reply to a video message.")
        return

    try:
        caption_or_text = message.caption or message.text
        start, end = parse_sticker_args(caption_or_text)
    except ValueError as exc:
        await message.answer(f"Invalid timestamp format.\n{html_quote(str(exc))}")
        return

    await process_sticker_generation(target_message, message, start, end)


@dp.message(F.video)
async def video_handler(message: Message):
    file_size = message.video.file_size or 0
    if file_size > MAX_TELEGRAM_DOWNLOAD_SIZE:
        await message.answer("File exceeds Telegram bot download limit (20 MB).")
        return

    await message.answer(
        "Video received!\n\n"
        "Reply to it with <code>/sticker</code> to convert it into a video sticker."
    )


@dp.message(F.document)
async def document_handler(message: Message):
    doc = message.document
    if not doc:
        return

    filename = doc.file_name or ""
    mime_type = doc.mime_type or ""

    is_video = mime_type.startswith("video/") or filename.lower().endswith(
        (".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v")
    )

    if not is_video:
        await message.answer("Please send a valid video file.")
        return

    if (doc.file_size or 0) > MAX_TELEGRAM_DOWNLOAD_SIZE:
        await message.answer("File exceeds Telegram bot download limit (20 MB).")
        return

    await message.answer(
        "Video file received!\n\nReply to it with <code>/sticker</code> for conversion."
    )


@dp.message(F.text)
async def url_handler(message: Message):
    url = extract_url(message.text or "")
    if not url:
        await message.answer("Please send a valid video link or upload a video file.")
        return

    await process_video_download(message, url)


async def main():
    await get_http_session()
    try:
        await dp.start_polling(
            bot,
            allowed_updates=dp.resolve_used_update_types(),
        )
    finally:
        await close_http_session()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())