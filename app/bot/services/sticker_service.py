import logging
import tempfile
from html import escape as html_quote
from pathlib import Path

from aiogram.types import FSInputFile, Message

from app.bot.config import MAX_TELEGRAM_DOWNLOAD_SIZE
from app.bot.services.api_client import backend_client
from app.bot.utils import format_size

logger = logging.getLogger("telegram_bot.stickers")


async def download_telegram_file(bot, message: Message, output_path: str, tr) -> str:
    target = message.video or message.document
    if not target:
        raise ValueError("Message does not contain a video file.")
    if target.file_size and target.file_size > MAX_TELEGRAM_DOWNLOAD_SIZE:
        raise ValueError(tr("tg_limit_download"))
    telegram_file = await bot.get_file(target.file_id)
    if not telegram_file.file_path:
        raise RuntimeError("Failed to retrieve Telegram file path.")
    await bot.download_file(telegram_file.file_path, destination=output_path)
    return getattr(target, "file_name", None) or "video.mp4"


async def process_sticker_generation(
    bot,
    target_message: Message,
    reply_to_msg: Message,
    start: float,
    end: float | None,
    tr,
) -> None:
    status_message = await reply_to_msg.answer(tr("downloading_tg"))
    with tempfile.TemporaryDirectory(prefix="sticker_work_") as temp_dir:
        input_path = Path(temp_dir) / "input.mp4"
        output_path = Path(temp_dir) / "sticker.webm"
        try:
            await download_telegram_file(bot, target_message, str(input_path), tr)
            await status_message.edit_text(tr("converting"))
            output_data = await backend_client.upload_sticker(str(input_path), start, end)
            output_path.write_bytes(output_data)
            output_size = output_path.stat().st_size
            await status_message.edit_text(
                tr("sticker_ready", size=format_size(output_size))
            )
            await reply_to_msg.answer_document(
                document=FSInputFile(output_path, filename="sticker.webm"),
                caption=tr("sticker_caption"),
            )
            await status_message.delete()
        except Exception as exc:
            logger.exception("Error during sticker creation")
            error_msg = (
                str(exc)
                if isinstance(exc, (ValueError, RuntimeError))
                else tr("creation_failed")
            )
            try:
                await status_message.edit_text(
                    f"{tr('error_prefix')}: {html_quote(error_msg)}"
                )
            except Exception:
                pass
