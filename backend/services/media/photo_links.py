"""Bounded public HTTPS downloads and TikTok photo-post extraction."""
import ipaddress
import json
import re
from urllib.parse import urljoin, urlparse

import aiohttp
from aiohttp.resolver import ThreadedResolver

from backend.services.media.sticker_converter import StickerConversionError

MAX_BYTES = 50 * 1024 * 1024
MAX_PHOTOS = 35


class PublicResolver(ThreadedResolver):
    async def resolve(self, host, port=0, family=0):
        records = await super().resolve(host, port, family)
        if not records or any(not ipaddress.ip_address(record['host']).is_global for record in records):
            raise OSError('Private address')
        return records


def validate_url(url):
    try:
        parsed = urlparse(url)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None, 443):
            raise ValueError()
        try:
            address = ipaddress.ip_address(parsed.hostname)
        except ValueError:
            address = None
        if address is not None and not address.is_global:
            raise ValueError()
    except ValueError as exc:
        raise StickerConversionError('Нужна публичная HTTPS-ссылка на фото или публикацию') from exc
    return parsed


async def fetch_public(url, limit=MAX_BYTES, image=False, tiktok_only=False):
    connector = aiohttp.TCPConnector(resolver=PublicResolver())
    async with aiohttp.ClientSession(connector=connector, timeout=aiohttp.ClientTimeout(total=30), trust_env=False) as session:
        for _ in range(6):
            parsed = validate_url(url)
            if tiktok_only and not (parsed.hostname == 'tiktok.com' or parsed.hostname.endswith('.tiktok.com')):
                raise StickerConversionError('Ссылка TikTok перенаправляет на другой сайт')
            async with session.get(url, allow_redirects=False, headers={'User-Agent':'Mozilla/5.0', 'Referer':'https://www.tiktok.com/'}) as response:
                if response.status in (301,302,303,307,308):
                    url = urljoin(url, response.headers.get('Location',''))
                    continue
                if response.status != 200:
                    raise StickerConversionError('Не удалось скачать публикацию. Попробуйте файл из галереи.')
                if image and not response.headers.get('Content-Type','').lower().startswith('image/'):
                    raise StickerConversionError('По этой ссылке нет фото. Вставьте прямую ссылку на JPEG, PNG или WebP.')
                data = bytearray()
                async for chunk in response.content.iter_chunked(65536):
                    data.extend(chunk)
                    if len(data) > limit:
                        raise StickerConversionError('Фотографии публикации должны занимать не больше 50 МБ')
                return bytes(data), url
        raise StickerConversionError('Слишком много перенаправлений')


def tiktok_photos(html):
    match = re.search(r'<script\b[^>]*\bid=["\']__UNIVERSAL_DATA_FOR_REHYDRATION__["\'][^>]*>(.*?)</script>', html, re.S)
    if not match:
        return []
    try:
        scope = json.loads(match[1])['__DEFAULT_SCOPE__']
        post = scope.get('webapp.video-detail', {}).get('itemInfo', {}).get('itemStruct', {})
        images = post.get('imagePost', {}).get('images', [])
        if len(images) > MAX_PHOTOS:
            raise StickerConversionError('В публикации больше 35 фотографий')
        urls = [image['imageURL']['urlList'][0] for image in images]
        for url in urls:
            validate_url(url)
        return list(dict.fromkeys(urls))
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise StickerConversionError('Не удалось прочитать фотографии публикации TikTok') from exc


async def resolve_tiktok(url):
    html, final = await fetch_public(url, limit=4*1024*1024, tiktok_only=True)
    photos = tiktok_photos(html.decode('utf-8', errors='replace'))
    if not photos and '/photo/' in final:
        html, _ = await fetch_public(final.replace('/photo/','/video/',1), limit=4*1024*1024, tiktok_only=True)
        photos = tiktok_photos(html.decode('utf-8', errors='replace'))
    return photos
