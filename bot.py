import asyncio
import json
import logging
import os
import re
import tempfile
from html import quote as html_quote
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
            detail = error_payload.get("detail", "Ошибка сервера")
            logger.error("API GET Error [%s]: %s", resp.status, detail)
            raise RuntimeError("Не удалось получить информацию о видео.")
    except aiohttp.ClientError as exc:
        logger.error("HTTP Request Exception: %s", exc)
        raise RuntimeError("Ошибка соединения с бэкенд-сервисом.") from exc


async def download_url_to_file(url: str, output_dir: str) -> tuple[str, Path, int]:
    session = await get_http_session()
    params = {"url": url, "as_attachment": "true"}

    try:
        async with session.get(f"{API_BASE_URL}/download", params=params) as resp:
            if resp.status != 200:
                logger.error("API Download Error [%s]", resp.status)
                raise RuntimeError("Не удалось скачать видео с указанного ресурса.")

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
                            "Размер видео превышает лимит отправки Telegram (50 МБ)."
                        )
                    file.write(chunk)

            return safe_filename, output_path, total_size
    except aiohttp.ClientError as exc:
        logger.error("HTTP Download Exception: %s", exc)
        raise RuntimeError("Ошибка сети при скачивании файла.") from exc


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
                    logger.error("API Sticker Error [%s]", resp.status)
                    raise RuntimeError("Ошибка при обработке видео на сервере.")
                return await resp.read()
        except aiohttp.ClientError as exc:
            logger.error("HTTP Sticker Upload Exception: %s", exc)
            raise RuntimeError("Ошибка сети при конвертации стикера.") from exc


async def download_telegram_file(message: Message, output_path: str) -> str:
    target = message.video or message.document
    if not target:
        raise ValueError("Сообщение не содержит видеоклип.")

    if target.file_size and target.file_size > MAX_TELEGRAM_DOWNLOAD_SIZE:
        raise ValueError("Файл превышает лимит загрузки ботом Telegram (20 МБ).")

    telegram_file = await bot.get_file(target.file_id)
    if not telegram_file.file_path:
        raise RuntimeError("Не удалось получить путь к файлу Telegram.")

    await bot.download_file(telegram_file.file_path, destination=output_path)
    return getattr(target, "file_name", "video.mp4") or "video.mp4"


@dp.message(CommandStart())
async def start_handler(message: Message):
    await message.answer(
        "<b>Video Downloader & Sticker Bot</b>\n\n"
        "Отправьте ссылку на видео для скачивания без сжатия.\n\n"
        "<b>Поддерживаемые площадки:</b>\n"
        "YouTube, TikTok, Instagram, X/Twitter.\n\n"
        "Вы также можете отправить видеофайл и ответить на него командой <code>/sticker</code>."
    )


@dp.message(Command("help"))
async def help_handler(message: Message):
    await message.answer(
        "<b>Доступные команды:</b>\n\n"
        "<code>/start</code> — Справка о боте\n"
        "<code>/help</code> — Список команд\n"
        "<code>/sticker</code> — Сконвертировать видео в видеостикер\n"
        "<code>/sticker 5 8</code> — Сконвертировать отрезок от 5 до 8 секунд\n\n"
        "Или просто отправьте ссылку на видео."
    )


@dp.message(Command("sticker"))
async def sticker_command_handler(message: Message):
    source_message = message.reply_to_message
    if not source_message or (not source_message.video and not source_message.document):
        await message.answer("Ответьте командой <code>/sticker</code> на сообщение с видео.")
        return

    arguments = (message.text or "").split()[1:]
    if len(arguments) > 2:
        await message.answer("Использование: <code>/sticker 5 8</code>")
        return

    start = 0.0
    end = None

    try:
        if len(arguments) >= 1:
            start = parse_time(arguments[0])
        if len(arguments) == 2:
            end = parse_time(arguments[1])

        if end is not None and end <= start:
            raise ValueError
    except ValueError:
        await message.answer("Некорректный временной интервал.\nПример: <code>/sticker 5 8</code>")
        return

    status_message = await message.answer("Загрузка видео из Telegram...")

    with tempfile.TemporaryDirectory(prefix="sticker_work_") as temp_dir:
        input_path = Path(temp_dir) / "input.mp4"
        output_path = Path(temp_dir) / "sticker.webm"

        try:
            await download_telegram_file(source_message, str(input_path))
            await status_message.edit_text("Конвертация в Telegram-стикер...")

            output_data = await api_upload_sticker(str(input_path), start, end)
            output_path.write_bytes(output_data)

            output_size = output_path.stat().st_size
            await status_message.edit_text(f"Стикер готов!\nРазмер: {format_size(output_size)}")

            await message.answer_document(
                document=FSInputFile(output_path, filename="sticker.webm"),
                caption="Ваш видеостикер готов.",
            )
            await status_message.delete()

        except Exception as exc:
            logger.exception("Ошибка при создании стикера:")
            error_msg = str(exc) if isinstance(exc, (ValueError, RuntimeError)) else "Не удалось создать стикер."
            try:
                await status_message.edit_text(f"❌ {html_quote(error_msg)}")
            except Exception:
                pass


@dp.message(F.video)
async def video_handler(message: Message):
    file_size = message.video.file_size or 0
    if file_size > MAX_TELEGRAM_DOWNLOAD_SIZE:
        await message.answer("Файл превышает лимит загрузки ботом Telegram (20 МБ).")
        return

    await message.answer(
        "Видео получено!\n\n"
        "Ответьте на него командой <code>/sticker</code>, чтобы обрезать первые 3 секунды в стикер.\n"
        "Для фрагмента: <code>/sticker 5 8</code>"
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
        await message.answer("Пожалуйста, отправьте видеофайл.")
        return

    if (doc.file_size or 0) > MAX_TELEGRAM_DOWNLOAD_SIZE:
        await message.answer("Файл превышает лимит загрузки ботом Telegram (20 МБ).")
        return

    await message.answer(
        "Видеофайл получен!\n\nОтветьте на него командой <code>/sticker</code> для конвертации."
    )


@dp.message(F.text)
async def url_handler(message: Message):
    url = extract_url(message.text or "")
    if not url:
        await message.answer("Отправьте ссылку на видео или загрузите видеофайл.")
        return

    status_message = await message.answer("Анализ ссылки...")

    try:
        info = await api_json_get("/info", {"url": url})

        title = html_quote(info.get("title") or "Video")
        uploader = html_quote(info.get("uploader") or "")
        source = html_quote(info.get("extractor_key") or info.get("extractor") or "Unknown")

        lines = [f"<b>{title}</b>", f"Источник: {source}"]
        if uploader:
            lines.append(f"Автор: {uploader}")
        lines.append("\nСкачивание...")

        await status_message.edit_text("\n".join(lines))

        with tempfile.TemporaryDirectory(prefix="telegram_video_") as temp_dir:
            filename, output_path, size = await download_url_to_file(url, temp_dir)

            if size > MAX_TELEGRAM_UPLOAD_SIZE:
                raise RuntimeError("Размер скачанного видео превышает лимит отправки Telegram (50 МБ).")

            await message.answer_document(
                document=FSInputFile(output_path, filename=filename),
                caption=f"<b>{title}</b>\n{format_size(size)}",
            )

        await status_message.delete()

    except Exception as exc:
        logger.exception("Ошибка при загрузке видео по ссылке:")
        error_msg = str(exc) if isinstance(exc, RuntimeError) else "Не удалось скачать видео по указанной ссылке."
        try:
            await status_message.edit_text(f"❌ {html_quote(error_msg)}")
        except Exception:
            pass


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