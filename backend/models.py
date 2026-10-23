from pydantic import BaseModel, Field


class FormatInfo(BaseModel):
    format_id: str | None = None
    ext: str | None = None
    resolution: str | None = None
    width: int | None = None
    height: int | None = None
    fps: float | None = None
    vcodec: str | None = None
    acodec: str | None = None
    filesize: int | None = None
    filesize_approx: int | None = None
    tbr: float | None = None
    abr: float | None = None
    vbr: float | None = None
    protocol: str | None = None
    url: str | None = None
    has_audio: bool = False
    has_video: bool = False


class VideoInfo(BaseModel):
    source_url: str
    id: str | None = None
    title: str | None = None
    description: str | None = None
    uploader: str | None = None
    uploader_id: str | None = None
    uploader_url: str | None = None
    duration: float | None = None
    thumbnail: str | None = None
    thumbnails: list[dict] = Field(default_factory=list)
    webpage_url: str | None = None
    extractor: str | None = None
    extractor_key: str | None = None
    view_count: int | None = None
    like_count: int | None = None
    comment_count: int | None = None
    repost_count: int | None = None
    timestamp: int | None = None
    upload_date: str | None = None
    formats: list[FormatInfo] = Field(default_factory=list)
