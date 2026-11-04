# Source compatibility and caching

## Input formats

Gallery uploads and direct public HTTPS links recognize photos by their bytes,
including uploads marked `application/octet-stream`. Supported photos are JPEG,
PNG, WebP, HEIC/HEIF (pillow-heif), AVIF, GIF, BMP and TIFF. GIF and multi-page
TIFF use their first frame. EXIF orientation and transparency are retained.

Local FFmpeg decoding supports MP4/MOV/M4V/3GP/3G2, MKV/WebM, AVI,
MPEG/MPG/VOB, TS/MTS/M2TS, OGV/OGG, ASF/WMV and FLV when their codecs are
supported by the installed FFmpeg build. H.264 and 10-bit HEVC MOV are covered
by generated integration fixtures. These container names do not imply that
arbitrary damaged or proprietary codecs work. Network protocols remain disabled
inside FFmpeg; direct links use the bounded public HTTPS downloader instead.

Limits remain 50 MB per upload, 10 minutes and 4096×4096 for video, and 40 MP
for photos. HEVC conversion preserves the original for Render. HDR tone mapping
is not implemented. Real iPhone/Android captures need a device smoke test.

## First frame

The Source upload/link request still prepares a browser-compatible H.264 Preview.
The editor obtains a one-hour, Source- and user-scoped signed playback URL with
an authenticated POST. The native player then uses HTTP Range requests directly,
without waiting for a complete Blob download. Telegram initData and bot tokens
never appear in playback URLs. Each range checks the signature, expiry and media
ownership; expired or deleted Sources remain inaccessible. Responses use
`private, no-store`. The ticket is a temporary capability for this Preview only;
keep query strings out of proxy access logs. Retry obtains a fresh ticket.

This removes the full-download wait after preparation; it does not remove upload,
download or HEVC transcoding time. No device latency measurements are claimed.

## Cache inventory

| Data | Scope and bounds | Revalidation |
| --- | --- | --- |
| Immutable Telegram files and generated Previews | User, 5 minutes, 32 MB / 256 entries, coalesced producers | Ownership/membership before serving |
| Browser image and sticker Blobs | Current app, 5 minutes, 100 MB / 128 entries | Failed requests removed; covers invalidated after writes |
| Link Sources | User + URL, 5 minutes, 64 entries | Source ownership, file and expiry |
| Editable copies of existing stickers | User + Pack + sticker file, 128 entries | Fresh membership and Source ownership/expiry |
| Repeated gallery Sources | User + SHA-256 of input bytes, 64 entries | Source ownership, file and expiry before reuse |
| Editor filmstrips | Immutable Source ID, 5 minutes, 16 completed filmstrips | Incomplete/failed decoding is never cached |
| Last Render | Current Studio + complete edit settings | Changed settings or Source replace the cached result |

Repeated uploads still transfer the input, but skip normalization and retaining
another original. Caches are process-local and remain suitable for one backend
worker. They do not extend Source lifetimes. Filmstrip caching avoids another
16 seeks when returning from Render Preview to the same editor.

Further candidates: cache bot identity (`getMe`) with a short TTL and reset on
transport close; consider retained Source reuse across sessions only if repeat
uploads are measured as common. Neither is needed for the first-frame fix.
Do not cache publication/replacement/order reconciliation reads of `getStickerSet`:
remote contents can change in Telegram, and stale data could target the wrong
sticker. Broad Pack-state caching needs explicit invalidation across every write.

References: [FFmpeg formats](https://ffmpeg.org/ffmpeg-formats.html),
[pillow-heif plugin](https://pillow-heif.readthedocs.io/en/stable/pillow-plugin.html).
