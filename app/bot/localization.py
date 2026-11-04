from typing import Callable

MESSAGES = {
    "ru": {
        "start": (
            "<b>Видео Загрузчик и Стикер Бот</b>\n\n"
            "Отправьте ссылку на видео, чтобы скачать его в оригинальном качестве.\n\n"
            "<b>Поддерживаемые платформы:</b>\n"
            "YouTube, TikTok, Instagram, X/Twitter, VK/VK Video, OK, Rutube, "
            "Reddit, Facebook, Vimeo, Twitch, Dailymotion, Pinterest, Bilibili, "
            "Bluesky, Streamable, Coub.\n\n"
            "Вы также можете отправить видео напрямую с командой <code>/sticker</code> в подписи "
            "или ответить командой <code>/sticker</code> на видео."
        ),
        "help": (
            "<b>Доступные команды:</b>\n\n"
            "<code>/start</code> — Обзор бота\n"
            "<code>/help</code> — Список команд\n"
            "<code>/lang</code> — Сменить язык / Change language\n"
            "<code>/sticker</code> — Преобразовать видео в стикер\n\n"
            "Или просто отправьте ссылку для скачивания."
        ),
        "select_language": "Выберите язык / Select a language:",
        "lang_updated": "Язык успешно изменен на русский! 🇷🇺",
        "no_target": "Пожалуйста, отправьте видео с командой <code>/sticker</code> в подписи или ответьте на сообщение с видео.",
        "invalid_timestamp": "Неверный формат времени.\n{error}",
        "usage_sticker": "Использование: <code>/sticker</code>",
        "invalid_interval": "Неверный интервал: время окончания должно быть больше времени начала.",
        "downloading_tg": "Скачивание видео из Telegram...",
        "converting": "Конвертация в видео-стикер Telegram...",
        "sticker_ready": "Стикер готов!\nРазмер: {size}",
        "sticker_caption": "Вот ваш видео-стикер.",
        "creation_failed": "Не удалось создать стикер.",
        "analyzing_link": "Анализ ссылки...",
        "source": "Источник",
        "author": "Автор",
        "downloading": "Скачивание...",
        "limit_exceeded": "Размер скачанного видео превышает лимит Telegram (50 МБ).",
        "download_failed": "Не удалось скачать видео по ссылке.",
        "video_received": "Видео получено!\n\nОтветьте на него командой <code>/sticker</code>, чтобы сделать из него стикер.",
        "doc_received": "Видеофайл получен!\n\nОтветьте на него командой <code>/sticker</code> для конвертации.",
        "invalid_doc": "Пожалуйста, отправьте корректный видеофайл.",
        "tg_limit_download": "Файл превышает лимит загрузки Telegram бота (20 МБ).",
        "invalid_url": "Пожалуйста, отправьте корректную ссылку на видео или загрузите видеофайл.",
        "unknown_source": "Неизвестно",
        "error_prefix": "Ошибка",
        "open_webapp": "🚀 Открыть Mini App",
    },
    "en": {
        "start": (
            "<b>Video Downloader & Sticker Bot</b>\n\n"
            "Send a video link to download it in original quality.\n\n"
            "<b>Supported platforms:</b>\n"
            "YouTube, TikTok, Instagram, X/Twitter, VK/VK Video, OK, Rutube, "
            "Reddit, Facebook, Vimeo, Twitch, Dailymotion, Pinterest, Bilibili, "
            "Bluesky, Streamable, Coub.\n\n"
            "You can also upload a video file directly with <code>/sticker</code> in the caption, "
            "or reply to an existing video with <code>/sticker</code>."
        ),
        "help": (
            "<b>Available Commands:</b>\n\n"
            "<code>/start</code> — Bot overview\n"
            "<code>/help</code> — Command list\n"
            "<code>/lang</code> — Change language / Сменить язык\n"
            "<code>/sticker</code> — Convert video to a video sticker\n\n"
            "Or simply send a link to download a video."
        ),
        "select_language": "Select a language / Выберите язык:",
        "lang_updated": "Language successfully changed to English! 🇬🇧",
        "no_target": "Please send a video with <code>/sticker</code> in caption or reply to a video message.",
        "invalid_timestamp": "Invalid timestamp format.\n{error}",
        "usage_sticker": "Usage: <code>/sticker</code>",
        "invalid_interval": "Invalid time interval: end time must be greater than start time.",
        "downloading_tg": "Downloading video from Telegram...",
        "converting": "Converting to Telegram video sticker...",
        "sticker_ready": "Sticker ready!\nSize: {size}",
        "sticker_caption": "Here is your video sticker.",
        "creation_failed": "Failed to create sticker.",
        "analyzing_link": "Analyzing link...",
        "source": "Source",
        "author": "Author",
        "downloading": "Downloading...",
        "limit_exceeded": "Downloaded video exceeds Telegram upload limit (50 MB).",
        "download_failed": "Failed to download video from the link.",
        "video_received": "Video received!\n\nReply to it with <code>/sticker</code> to convert it into a video sticker.",
        "doc_received": "Video file received!\n\nReply to it with <code>/sticker</code> for conversion.",
        "invalid_doc": "Please send a valid video file.",
        "tg_limit_download": "File exceeds Telegram bot download limit (20 MB).",
        "invalid_url": "Please send a valid video link or upload a video file.",
        "unknown_source": "Unknown",
        "error_prefix": "Error",
        "open_webapp": "🚀 Open Mini App",
    },
}

USER_LANGUAGES: dict[int, str] = {}


def get_language(user_id: int | None, telegram_language_code: str | None = None) -> str:
    if user_id is not None and user_id in USER_LANGUAGES:
        return USER_LANGUAGES[user_id]
    if telegram_language_code and telegram_language_code.startswith("ru"):
        return "ru"
    return "en"


def translate(language: str, key: str, **kwargs) -> str:
    template = MESSAGES.get(language, MESSAGES["en"]).get(key, key)
    return template.format(**kwargs) if kwargs else template


def translator_for(language: str) -> Callable:
    def tr(key: str, **kwargs) -> str:
        return translate(language, key, **kwargs)
    return tr
