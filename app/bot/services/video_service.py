import logging
import tempfile
from html import escape as html_quote
from pathlib import Path

from aiogram.types import FSInputFile, Message

from app.bot.config import MAX_TELEGRAM_UPLOAD_SIZE
from app.bot.services.api_client import backend_client
from app.bot.utils import format_size

logger = logging.getLogger("telegram_bot.video")


async def process_video_download(message: Message, url: str, tr) -> None:
    status_message = await message.answer(tr("downloading"))
    try:
        with tempfile.TemporaryDirectory(prefix="telegram_video_") as temp_dir:
            filename, output_path, size = await backend_client.download_url_to_file(
                url,
                temp_dir,
                tr,
            )
            if size > MAX_TELEGRAM_UPLOAD_SIZE:
                raise RuntimeError(tr("limit_exceeded"))
            title = html_quote(Path(filename).stem)
            await message.answer_document(
                document=FSInputFile(output_path, filename=filename),
                caption=f"<b>{title}</b>\n{format_size(size)}",
            )
        await status_message.delete()
    except Exception as exc:
        logger.exception("Error downloading video from link")
        error_msg = str(exc) if isinstance(exc, RuntimeError) else tr("download_failed")
        try:
            await status_message.edit_text(
                f"{tr('error_prefix')}: {html_quote(error_msg)}"
            )
        except Exception:
            pass
