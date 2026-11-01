import logging
import tempfile
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, File, Form, HTTPException, Query, Security, UploadFile
from fastapi.responses import FileResponse
from pydantic import HttpUrl
from starlette.background import BackgroundTask

from backend.config import MAX_SOURCE_SIZE
from backend.models import VideoInfo
from backend.security import verify_api_key
from backend.services.file_service import cleanup_files
from backend.services.media.downloader import DownloadFailed, download_to_file
from backend.services.media.extractor import ExtractError, get_video_info
from backend.services.media.sticker_converter import (
    StickerConversionError,
    convert_video_to_sticker,
    validate_sticker_file,
)

logger = logging.getLogger("video_backend.media")
router = APIRouter()


@router.get(
    "/info",
    response_model=VideoInfo,
    dependencies=[Security(verify_api_key)],
)
def info(
    url: HttpUrl = Query(..., description="Video URL"),
    only_with_video: bool = Query(True, description="Return only formats containing video"),
):
    try:
        return get_video_info(str(url), only_with_video=only_with_video)
    except ExtractError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/download", dependencies=[Security(verify_api_key)])
def download(
    url: HttpUrl = Query(..., description="Video URL"),
    format_id: str | None = Query(None, description="Format ID returned by /info"),
    name: str | None = Query(None, description="Output filename without extension"),
    as_attachment: bool = Query(True, description="Return the file as an attachment"),
):
    try:
        file_path, filename, mime_type = download_to_file(
            str(url), format_id=format_id, name=name
        )
    except DownloadFailed as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    headers = {"Cache-Control": "no-store"}
    if as_attachment:
        headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(filename)}"
    cleanup = BackgroundTask(cleanup_files, file_path, file_path.parent)
    return FileResponse(
        path=file_path,
        media_type=mime_type,
        filename=filename,
        headers=headers,
        background=cleanup,
    )


@router.post("/convert/sticker", dependencies=[Security(verify_api_key)])
def convert_sticker(
    video: UploadFile = File(..., description="Source video file"),
    start: float = Form(0.0, ge=0.0, allow_inf_nan=False, description="Start time in seconds"),
    end: float | None = Form(None, gt=0.0, allow_inf_nan=False, description="End time in seconds"),
):
    if not video.filename:
        raise HTTPException(status_code=400, detail="No input filename provided")

    input_suffix = Path(video.filename).suffix or ".mp4"
    with tempfile.NamedTemporaryFile(
        suffix=input_suffix,
        prefix="sticker_input_",
        delete=False,
    ) as tmp_input:
        input_path = Path(tmp_input.name)

    try:
        size = 0
        with input_path.open("wb") as buffer:
            while chunk := video.file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_SOURCE_SIZE:
                    raise HTTPException(413, "Видео должно быть не больше 50 МБ")
                buffer.write(chunk)
    except HTTPException:
        cleanup_files(input_path)
        raise
    except OSError as exc:
        cleanup_files(input_path)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save uploaded video: {exc}",
        ) from exc
    finally:
        video.file.close()

    try:
        output_path_str, duration = convert_video_to_sticker(
            input_path=str(input_path),
            start=start,
            end=end,
        )
        output_path = Path(output_path_str)
        validate_sticker_file(str(output_path))
    except StickerConversionError as exc:
        cleanup_files(input_path)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception:
        cleanup_files(input_path)
        raise

    cleanup = BackgroundTask(cleanup_files, input_path, output_path)
    return FileResponse(
        path=output_path,
        media_type="video/webm",
        filename="sticker.webm",
        background=cleanup,
        headers={"X-Sticker-Duration": f"{duration:.3f}"},
    )
