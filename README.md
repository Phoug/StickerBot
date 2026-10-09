# StickerBot

StickerBot is a Telegram bot and Telegram Mini App backed by a FastAPI service. It can retrieve video information, download supported media, convert short video clips into Telegram-compatible WebM stickers, and provide Telegram account and sticker-set features through Telethon.

## Features

- Telegram bot commands and language selection.
- A Telegram Mini App served from the `webapp/` directory.
- Video information extraction and downloads through `yt-dlp`.
- Video-to-sticker conversion using FFmpeg and VP9/WebM.
- Telegram Mini App `initData` validation on the backend.
- Optional MTProto account sign-in and sticker-set inspection through Telethon.
- An API key for backend endpoints intended for trusted internal clients.

## Project structure

```text
STICKERBOT/
├── app/
│   ├── bot.py
│   ├── config.py
│   ├── localization.py
│   ├── middleware.py
│   ├── utils.py
│   ├── handlers/
│   ├── keyboards/
│   └── services/
│
├── backend/
│   ├── main.py
│   ├── config.py
│   ├── models.py
│   ├── security.py
│   ├── routers/
│   └── services/
│       └── media/
│
├── webapp/
│   ├── index.html
│   └── assets/
├── app/requirements.txt
├── backend/requirements.txt
├── run_bot.py
├── .env
├── Dockerfile
└── compose.yaml
```

The bot and backend are separate application components. `app/` contains Telegram bot code; `backend/` contains the FastAPI application and its services; `webapp/` contains the client-side Mini App. Keep the actual `index.html`, JavaScript, stylesheets, and images in `webapp/`.

## Requirements

- Python 3.10 or newer.
- FFmpeg and `ffprobe` installed and available through `PATH`.
- An FFmpeg build that supports the `libvpx-vp9` encoder.
- A Telegram bot token from BotFather.
- Telegram API ID and API hash if Telethon account features are enabled.
- A public HTTPS URL for the Mini App when running it inside Telegram.

Check the FFmpeg installation with:

```bash
ffmpeg -version
ffprobe -version
ffmpeg -hide_banner -encoders
```

Confirm that `libvpx-vp9` appears in the encoder list.

## Configuration

Create a `.env` file in the project root. Do not commit this file or share its secret values.

```dotenv
BOT_TOKEN=replace_with_your_bot_token
API_SECRET_TOKEN=replace_with_a_long_random_secret
VIDEO_API_URL=http://127.0.0.1:8000
WEBAPP_URL=https://your-domain.example/app/

TELEGRAM_API_ID=replace_with_your_telegram_api_id
TELEGRAM_API_HASH=replace_with_your_telegram_api_hash
TELETHON_SESSIONS_DIR=/absolute/path/to/telegram_sessions

MINI_APP_AUTH_MAX_AGE=3600
LOGIN_CODE_TTL=600
LOGIN_CODE_COOLDOWN=60
MAX_STICKER_SETS=2000
```

Configuration notes:

- `BOT_TOKEN` is used by the bot and by the backend to validate Telegram Mini App `initData`. Use the same value in both components.
- `API_SECRET_TOKEN` must be the same in the bot and backend. The bot sends it in the `X-API-Key` header when calling protected media endpoints. Generate a long, unpredictable value.
- `VIDEO_API_URL` is the base URL used by the bot to reach FastAPI. Use `http://127.0.0.1:8000` for a local process. In Docker Compose, use the backend service name and its internal port, for example `http://backend:8000`, if the service is named `backend`.
- `WEBAPP_URL` must be the public HTTPS address where the Mini App is available.
- `TELEGRAM_API_ID` and `TELEGRAM_API_HASH` are required by the backend for Telethon. Obtain them from Telegram's developer portal.
- `TELETHON_SESSIONS_DIR` should point to a persistent, private directory. Telethon session files contain sensitive account credentials and must never be served as static files or committed to source control.

Do not put `BOT_TOKEN`, `API_SECRET_TOKEN`, `TELEGRAM_API_HASH`, or Telethon session data in frontend JavaScript, HTML, URLs, or logs.

## Installation

Create and activate a virtual environment from the project root.

### Windows PowerShell

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r app/requirements.txt
pip install -r backend/requirements.txt
```

### Linux or macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r app/requirements.txt
pip install -r backend/requirements.txt
```

Installing both requirement files into one virtual environment is convenient for local development. For production, the bot and backend can be built as separate containers, each installing its own requirements file.

## Running locally

Start the backend from the project root:

```bash
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

In a second terminal, activate the same virtual environment and start the bot:

```bash
python run_bot.py
```

The bot's `VIDEO_API_URL` must point to the backend address. The backend health endpoint is available at:

```text
http://127.0.0.1:8000/health
```

The application must be configured to serve the `webapp/` directory at `/app/` for the Mini App URL shown in `WEBAPP_URL` to work. If the frontend is served by Nginx instead, configure Nginx to serve the static files and adjust the deployment accordingly.

## API overview

The backend includes these routes:

| Route | Purpose | Access |
|---|---|---|
| `GET /health` | Health check | Public |
| `GET /info` | Extract video metadata and formats | Requires `X-API-Key` |
| `GET /download` | Download a video | Requires `X-API-Key` |
| `POST /convert/sticker` | Convert an uploaded video into a WebM sticker | Requires `X-API-Key` |
| `GET /api/telegram/status` | Check the connected Telegram account | Requires valid `X-Telegram-Init-Data` |
| `POST /api/telegram/login/request-code` | Request an MTProto login code | Requires valid `X-Telegram-Init-Data` |
| `POST /api/telegram/login/verify` | Verify a login code or 2FA password | Requires valid `X-Telegram-Init-Data` |
| `POST /api/telegram/logout` | Disconnect the MTProto account | Requires valid `X-Telegram-Init-Data` |
| `GET /api/sticker-sets` | List the account's sticker sets | Requires valid `X-Telegram-Init-Data` |
| `GET /api/sticker-sets/{short_name}` | Get details for one sticker set | Requires valid `X-Telegram-Init-Data` |

The exact routes depend on the code currently installed in the project. Keep the bot's API client and backend route definitions aligned when changing endpoint paths or request formats.

## Security and deployment notes

- Serve the Mini App over HTTPS in production.
- Validate Telegram Mini App `initData` on the backend; never trust a user ID supplied only by frontend JavaScript.
- Apply authorization checks to every private operation and enforce request, upload, and processing limits.
- Do not expose the backend API key, Telethon API hash, or session files to the frontend.
- Keep PostgreSQL, Redis, and internal service ports private if those services are added.
- Configure persistent private storage for Telethon sessions if users must remain signed in after container restarts.
- Add resource limits and timeouts for media processing. Do not allow user-controlled file paths.
- Review `Dockerfile` and `compose.yaml` before deployment to ensure the correct entry point, environment variables, storage mounts, and internal networking are configured.

## Troubleshooting

### The bot cannot connect to the backend

Check that the backend is running and `VIDEO_API_URL` points to the address reachable from the bot process. When using Docker, `127.0.0.1` inside one container refers to that same container, not another service.

### Sticker conversion fails

Check that `ffmpeg` and `ffprobe` are installed and available on `PATH`, and that the FFmpeg build supports `libvpx-vp9`.

### The Mini App does not open

Verify `WEBAPP_URL`, HTTPS availability, and that the configured static-file server serves `webapp/` at the expected `/app/` path.

### Telegram account sign-in fails

Check `TELEGRAM_API_ID` and `TELEGRAM_API_HASH`, network access to Telegram, the session directory's permissions, and whether Telegram requires a 2FA password or a wait period.

## License

Add the project's license here before publishing or distributing it.
