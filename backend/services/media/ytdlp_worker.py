"""Internal JSON worker. No bot credentials, .env, or API imports are needed."""
import json
import sys

from backend.services.media.network import public_network, validate_public_url


def execute(job):
    from yt_dlp import YoutubeDL
    from yt_dlp.downloader.external import ExternalFD
    from yt_dlp.downloader.rtmp import RtmpFD
    from yt_dlp.utils import DownloadError, determine_protocol

    def disallow_external(*args, **kwargs):
        raise DownloadError("Поток требует внешнего сетевого загрузчика. Загрузите файл из галереи.")

    # Native HLS can fall back to an external process; such a process would not
    # inherit Python's connection checks. FFmpeg is allowed only for local PP.
    ExternalFD.real_download = disallow_external
    RtmpFD.real_download = disallow_external
    from yt_dlp.downloader.external import FFmpegFD
    FFmpegFD.real_download = disallow_external

    class PublicYoutubeDL(YoutubeDL):
        def process_info(self, info):
            if info.get("is_live"):
                raise DownloadError("Прямые трансляции не поддерживаются")
            allowed = {"http", "https", "m3u8", "m3u8_native", "http_dash_segments", "http_dash_segments_generator"}
            for part in info.get("requested_formats") or [info]:
                if any(protocol not in allowed for protocol in determine_protocol(part).split("+")):
                    raise DownloadError("Неподдерживаемый сетевой протокол видео")
            return super().process_info(info)

    options = job["options"]
    sizes = {}

    def limit(progress):
        sizes[progress.get("filename", "download")] = progress.get("downloaded_bytes", 0)
        if sum(sizes.values()) > job["max_bytes"]:
            raise DownloadError("Видео должно быть не больше 50 МБ")

    def duration_limit(info, *, incomplete=False):
        if info.get("is_live") or (info.get("duration") or 0) > job["max_duration"]:
            return "Видео должно быть не длиннее 10 минут; трансляции не поддерживаются"

    options.update({
        "cachedir": False,
        "proxy": "", "usenetrc": False, "enable_file_urls": False,
        "external_downloader": {"default": "native"}, "hls_prefer_native": True,
        "concurrent_fragment_downloads": 1, "max_filesize": job["max_bytes"],
        "progress_hooks": [limit], "match_filter": duration_limit,
        "socket_timeout": 20, "retries": 1, "fragment_retries": 1, "extractor_retries": 1,
        "postprocessor_args": {"ffmpeg_i": ["-protocol_whitelist", "file,pipe"]},
    })
    with public_network(), PublicYoutubeDL(options) as ydl:
        info = ydl.extract_info(validate_public_url(job["url"]), download=job["download"])
        return ydl.sanitize_info(info)


def main():
    try:
        result = execute(json.load(sys.stdin))
        print(json.dumps({"ok": True, "info": result}))
    except Exception as exc:
        # Network libraries can include URLs and headers in their exceptions.
        print(json.dumps({"ok": False, "reason": type(exc).__name__,
                          "error": "Не удалось загрузить публичное видео. Проверьте ссылку и ограничения размера/длительности."}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
