import logging
import tempfile
from html import escape as html_quote

from aiogram.types import FSInputFile, Message

from app.config import MAX_TELEGRAM_UPLOAD_SIZE
from app.services.api_client import backend_client
from app.utils import format_size

logger = logging.getLogger("telegram_bot.video")


async def process_video_download(message: Message, url: str, tr) -> None:
    status_message = await message.answer(tr("analyzing_link"))
    try:
        info = await backend_client.get_json("/info", {"url": url})
        title = html_quote(info.get("title") or "Video")
        uploader = html_quote(info.get("uploader") or "")
        source = html_quote(
            info.get("extractor_key")
            or info.get("extractor")
            or tr("unknown_source")
        )
        lines = [f"<b>{title}</b>", f"{tr('source')}: {source}"]
        if uploader:
            lines.append(f"{tr('author')}: {uploader}")
        lines.append(f"\n{tr('downloading')}")
        await status_message.edit_text("\n".join(lines))
        with tempfile.TemporaryDirectory(prefix="telegram_video_") as temp_dir:
            filename, output_path, size = await backend_client.download_url_to_file(
                url,
                temp_dir,
                tr,
            )
            if size > MAX_TELEGRAM_UPLOAD_SIZE:
                raise RuntimeError(tr("limit_exceeded"))
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
