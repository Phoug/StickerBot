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

Limits remain 50 MB per upload, 10 minutes and 4096×4096 for video, and 64 MP
for photos, including 48 MP iPhone captures. Photos are downscaled before RGBA
conversion to avoid retaining a full-resolution four-channel copy. HEVC conversion
preserves the original for Render. HDR tone mapping
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

The editor explicitly requests `preload="auto"` and starts muted inline playback
when metadata arrives, then pauses at the first decoded frame. This avoids
waiting on metadata-only preloading in iOS WebKit. If autoplay is blocked, the
play button can start decoding through a user gesture. After 30 seconds without
a decoded frame, the editor offers retry instead of an endless spinner; a late
first frame clears the error. Retry remounts the player even if its URL repeats.
See [WebKit's video loading policy](https://webkit.org/blog/6784/new-video-policies-for-ios/).

This removes the full-download wait after preparation; it does not remove upload,
download or HEVC transcoding time. No device latency measurements are claimed.

## Editor controls

All tool panels share one grid cell and reserve the tallest panel's height.
Inactive panels remain in layout but are invisible, inert and hidden from assistive
technology. Switching tabs therefore preserves the preview and crop bounds.
Shape labels wrap within equal-width columns. Short viewports use compact
controls and hide the app brand bar so the preview and action remain visible.
Browser layout checks visit every tool tab at 320–1024 px widths, including
landscape, and assert that text, buttons and panels fit without scrolling.
The editor has one video element, native controls are suppressed, and the custom
playback timer remains a single visible element on every tab.

`npm run test:layout` uses Chromium. To also check WebKit, install its browser
and system dependencies with `npx playwright install --with-deps webkit`, then
run `LAYOUT_BROWSER=webkit npm run test:layout` from `frontend/`.

## Timeline frames

After the first Source frame, the editor requests an authenticated JPEG filmstrip
for the visible `start` and `span` (up to 12 seconds initially). FFmpeg samples
eight frames from the normalized H.264 Preview into one 768×64 image. Tiles crop
their frame centers without stretching people or objects. Seeking begins one
second earlier; cloned final frames cover sub-frame windows near the end.
No second HTML video element or browser canvas decoder is created.

Window changes are debounced for 200 ms and stale responses are ignored. The
server checks ownership, expiry and finite window bounds before looking up its
shared Preview cache. Only the cache producer occupies media capacity, including
after HTTP disconnection. A failed timeline exposes a separate retry and leaves
crop, trim and Render available. A retry does not restart the Source player.

## Cache inventory

| Data | Scope and bounds | Revalidation |
| --- | --- | --- |
| Immutable Telegram files and generated Previews | User, 5 minutes, 32 MB / 256 entries, coalesced producers | Ownership/membership before serving |
| Browser image and sticker Blobs | Current app, 5 minutes, 100 MB / 128 entries | Failed requests removed; covers invalidated after writes |
| Link Sources | User + URL, 5 minutes, 64 entries | Source ownership, file and expiry |
| Editable copies of existing stickers | User + Pack + sticker file, 128 entries | Fresh membership and Source ownership/expiry |
| Repeated gallery Sources | User + SHA-256 of input bytes, 64 entries | Source ownership, file and expiry before reuse |
| Editor filmstrips | User + Source + visible window; shared 5 minute / 32 MB / 256 entry Preview cache and browser Blob cache | Ownership and expiry before serving; failures are not cached |
| Last Render | Current Studio + complete edit settings | Changed settings or Source replace the cached result |

Repeated uploads still transfer the input, but skip normalization and retaining
another original. Caches are process-local and remain suitable for one backend
worker. They do not extend Source lifetimes. Filmstrip caching avoids another
FFmpeg decode when returning to the same timeline window.

Further candidates: cache bot identity (`getMe`) with a short TTL and reset on
transport close; consider retained Source reuse across sessions only if repeat
uploads are measured as common. Neither is needed for the first-frame fix.
Do not cache publication/replacement/order reconciliation reads of `getStickerSet`:
remote contents can change in Telegram, and stale data could target the wrong
sticker. Broad Pack-state caching needs explicit invalidation across every write.

References: [FFmpeg formats](https://ffmpeg.org/ffmpeg-formats.html),
[pillow-heif plugin](https://pillow-heif.readthedocs.io/en/stable/pillow-plugin.html).
