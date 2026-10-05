# Video Downloader & Sticker Telegram Bot

An asynchronous Telegram Bot built with **aiogram 3** and **FastAPI** that downloads videos from popular social media platforms (YouTube, TikTok, Instagram, X/Twitter, etc.) and converts videos into Telegram WebM video stickers.

---

## Features

- **Video Downloading**: Fetch videos from YouTube, TikTok, Instagram, X (Twitter), and more in MP4 format.
- **Video Sticker Conversion**: Convert video files or Telegram videos into animated `.webm` stickers compliant with Telegram specifications (VP9, 512x512, <= 3s, <= 256 KB).
- **Asynchronous Architecture**: Built on `aiogram 3`, `FastAPI`, and `aiohttp`.

---

## Prerequisites

Before setting up the project, ensure you have the following installed on your system:

1. **Python**: Version `3.10` or higher.
2. **FFmpeg & FFprobe**: Required for media processing and video sticker conversion.
   - **Ubuntu/Debian**:
     ```bash
     sudo apt update && sudo apt install ffmpeg -y
     ```
   - **macOS** (via Homebrew):
     ```bash
     brew install ffmpeg
     ```
   - **Windows**: Download binaries from [FFmpeg Official Website](https://ffmpeg.org/download.html) and add the `bin` directory to your System `PATH`.

---

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/Phoug/sticker-bot
cd sticker-bot
```

### 2. Set Up a Virtual Environment

It is recommended to use a virtual environment to manage project dependencies:

```bash
# Create a virtual environment
python -m venv .venv

# Activate on Linux/macOS
source .venv/bin/activate

# Activate on Windows (Command Prompt)
.venv\Scripts\activate.bat

# Activate on Windows (PowerShell)
.venv\Scripts\Activate.ps1
```

### 3. Install Dependencies

Install all required Python packages using `pip`:

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

---

## Configuration

Create a `.env` file in the root directory of your project:

```bash
touch .env
```

Add the following environment variables to `.env`:

```env
# Telegram Bot Token obtained from @BotFather
BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyZ

# Backend API Service Base URL (Default: http://127.0.0.1:8000)
VIDEO_API_URL=http://127.0.0.1:8000
```

---

## Running the Application

The project consists of two separate components that need to run simultaneously:
1. **FastAPI Backend Server** (Handles video processing & sticker conversion)
2. **Telegram Bot Service** (Handles user interaction)

### Option 1: Running in Separate Terminal Windows

**Terminal 1 — Start the FastAPI Server:**

```bash
uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

**Terminal 2 — Start the Telegram Bot:**

```bash
python bot.py
```

---

## Bot Usage

- **Download Video**: Simply paste a supported link (e.g., YouTube, TikTok, Instagram) into the chat.
- **Create Video Sticker**:
  - Upload a video file or reply to an existing video with `/sticker`.
  - Specify a time range: `/sticker 5 8` (converts seconds 5 to 8 into a sticker).
