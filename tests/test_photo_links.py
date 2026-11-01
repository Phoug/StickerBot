import asyncio
import json
from io import BytesIO

import pytest
from PIL import Image

from backend.services.media.photo_links import tiktok_photos, validate_url, PublicResolver
from backend.services.media.sticker_converter import StickerConversionError
from test_api import client, auth
from backend.routers import studio
from backend import storage


def test_tiktok_album_keeps_order_and_does_not_use_music():
    data={'__DEFAULT_SCOPE__':{'webapp.video-detail':{'itemInfo':{'itemStruct':{'imagePost':{'images':[
        {'imageURL':{'urlList':['https://cdn.example.com/one.webp']}},
        {'imageURL':{'urlList':['https://cdn.example.com/two.webp']}}]},'music':{'playUrl':'https://cdn.example.com/music.mp3'}}}}}}
    html='<script type="application/json" id="__UNIVERSAL_DATA_FOR_REHYDRATION__">'+json.dumps(data)+'</script>'
    assert tiktok_photos(html)==['https://cdn.example.com/one.webp','https://cdn.example.com/two.webp']
    assert tiktok_photos('<html>challenge</html>')==[]


@pytest.mark.parametrize('url',['http://example.com/a.png','https://127.0.0.1/a','https://[::1]/a','https://169.254.169.254/a','https://user:pass@example.com/a','https://example.com:8080/a'])
def test_photo_urls_reject_nonpublic_targets(url):
    with pytest.raises(StickerConversionError):validate_url(url)


def test_resolver_rejects_private_dns_results(monkeypatch):
    from aiohttp.resolver import ThreadedResolver
    async def resolve(*args,**kwargs):return [{'host':'10.0.0.1'}]
    monkeypatch.setattr(ThreadedResolver,'resolve',resolve)
    async def scenario():
        resolver=PublicResolver()
        try:
            with pytest.raises(OSError):await resolver.resolve('public.example.com',443)
        finally:await resolver.close()
    asyncio.run(scenario())


def png():
    data=BytesIO();Image.new('RGB',(640,400),'orange').save(data,'PNG');return data.getvalue()


def test_album_import_returns_separate_owned_sources_and_thumbnails(client,monkeypatch):
    api,_,_=client
    async def resolve(url):return ['https://cdn.example.com/1','https://cdn.example.com/2']
    async def fetch(url,**kwargs):return png(),url
    monkeypatch.setattr(studio,'resolve_tiktok',resolve);monkeypatch.setattr(studio,'fetch_public',fetch)
    result=api.post('/api/studio/link',json={'url':'https://www.tiktok.com/@test/photo/123'},headers=auth())
    assert result.status_code==201
    album=result.json();assert album['kind']=='album' and len(album['photos'])==2
    for photo in album['photos']:
        assert photo['kind']=='photo'
        route='/api/studio/media/'+photo['id']+'?thumbnail=true'
        assert api.get(route,headers=auth(8)).status_code==404
        thumb=api.get(route,headers=auth())
        assert max(Image.open(BytesIO(thumb.content)).size)<=180


def test_failed_album_rolls_back_files(client,monkeypatch):
    api,_,folder=client
    async def resolve(url):return ['https://cdn.example.com/1','https://cdn.example.com/2']
    async def fetch(url,**kwargs):
        if url.endswith('/2'):raise StickerConversionError('failed')
        return png(),url
    monkeypatch.setattr(studio,'resolve_tiktok',resolve);monkeypatch.setattr(studio,'fetch_public',fetch)
    assert api.post('/api/studio/link',json={'url':'https://www.tiktok.com/@test/photo/123'},headers=auth()).status_code==422
    with storage.database() as db:assert db.execute('SELECT COUNT(*) FROM media').fetchone()[0]==0
    assert not list((folder/'media').glob('*'))


def test_direct_photo_link(client,monkeypatch):
    api,_,_=client
    async def fetch(url,**kwargs):return png(),url
    monkeypatch.setattr(studio,'fetch_public',fetch)
    response=api.post('/api/studio/link',json={'url':'https://cdn.example.com/photo.png'},headers=auth())
    assert response.status_code==201 and response.json()['kind']=='photo'
