# -*- coding: utf-8 -*-
"""
Statusの中のURLをみて、そのURLのOGP情報を返す

もってなければ、クロールしておく。次アクセスした時に見られる。
"""
import datetime
import json
import logging
from urllib.parse import urlsplit

from tornado import gen, ioloop

from naumanni.plugin import Plugin
try:
    from .ogp import parse_ogp
except:
    from ogp import parse_ogp


logger = logging.getLogger(__name__)


class OGPPlugin(Plugin):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def on_filter_statuses(self, objects, entities):
        url_map = {}
        for status in objects.values():
            # reblogしたTootのほうにはmedia_attachmentsが付かない、された方には付いている。
            # つまりreblogのTootはskipした方がいい
            if status.reblog:
                continue

            for url in status.urls_without_media:
                if url not in url_map:
                    url_map[url] = []
                url_map[url].append(status)

        if not url_map:
            return objects

        # 1. RedisでOGPが保存済みかしらべてgetする
        urls = list(url_map.keys())
        async with self.app.get_async_redis() as redis:
            cached = await redis.mget(*[_make_redis_key(u) for u in urls])

        for url, cached_meta in zip(urls, cached):
            if cached_meta:
                cached_meta = json.loads(cached_meta)
                statuses = url_map.pop(url)
                for status in statuses:
                    ogps = status.get_extended_attributes('ogp', [])
                    meta = cached_meta.copy()
                    meta['target_url'] = url
                    ogps.append(meta)
                    status.add_extended_attributes('ogp', ogps)

        # 2. 全部celeryする。次回アクセスした時にogpが乗ってる
        for url in url_map.keys():
            ioloop.IOLoop.instance().spawn_callback(
                crawl_ogp_url, self.app_ref, url,
            )

        return objects


async def crawl_ogp_url(app_ref, url, level=0):
    """urlをクロールして、ogpなどの情報を返す

    :param str url: クロール対象のurl
    """
    app = app_ref()
    if not app:
        raise RuntimeError('naumanni is gone')

    original_url = url

    # 与えられたURLをクロールしてメタデータを保存
    for redirect in range(3):
        logger.debug('crawl_ogp_url %r', url)
        if not (url.startswith('http://') or url.startswith('https://')):
            logger.debug('bad url : %s', url)
            # bad url
            return

        response = await app.crawl_url(url)
        if 300 <= response.code < 400 and 'location' in response.headers:
            before = url
            url = response.headers['Location']
            logger.debug(' redirect %s -> %s', before, url)
            original_url = url
            continue
        break

    # responseからmeta情報を得る
    content_type = _get_content_type(response)
    next_url = None
    meta = {'status_code': response.code, 'content_type': content_type}
    if response.code == 200 and content_type == 'text/html':
        # 200 & htmlじゃないとメタ情報は探らない
        meta.update(parse_ogp(response.body))

        # og:url/link:canonicalがあればそちらのogpを保存したいので、次のクロール先を取得する
        if 'og:url' in meta and meta['og:url'] != url:
            next_url = meta['og:url']
        elif 'link:canonical' in meta and meta['link:canonical'] != url:
            next_url = meta['link:canonical']

    # meta情報を保存する
    await save_meta(app, original_url, meta)

    # canonical探しは1段のみ
    if level == 0:
        if next_url:
            original_url_parsed = urlsplit(original_url)
            next_url_parsed = urlsplit(next_url)
            # netlocがマッチしてなければ探査しない
            if original_url_parsed.netloc != next_url_parsed.netloc:
                logger.info('netloc mismatch, ignore next_url %s %s %s', original_url, url, next_url)
                next_url = None
            # https?じゃなければ探査しない
            elif next_url_parsed.scheme not in ('http', 'https'):
                logger.info('invalid next_url schema %s %s %s', original_url, url, next_url)
                next_url = None

        if next_url:
            meta = await crawl_ogp_url(app_ref, next_url, level=level + 1)
            await save_meta(app, original_url, meta)

    return meta


def _get_content_type(response):
    content_type = response.headers.get('Content-Type')
    if not content_type:
        return None
    if ';' in content_type:
        content_type = content_type.split(';', 1)[0]
    return content_type


async def save_meta(app, url, meta=None):
    """metaの情報を解釈して保存する"""
    logger.debug('save_meta: %s -> %r', url, meta)

    # redirect, og:url, link:canonical 的に、さらに見に行かないと行けないurl
    now = datetime.datetime.utcnow().isoformat()

    save = {}
    if meta['status_code'] == 200:
        save = {
            'date_crawled': now,
            'content_type': meta.get('content_type'),
            'image': meta.get('og:image', meta.get('scrape:image')),
            'description': meta.get('og:description', meta.get('scrape:description')),
            'title': meta.get('og:title', meta.get('scrape:title')),
            'type': meta.get('og:type', meta.get('scrape:type')),
            'url': meta.get('og:url', url),
        }
    else:
        # エラーを保存
        save = {
            'date_crawled': now,
            'error': meta['status_code'],
        }

    async with app.get_async_redis() as redis:
        key = _make_redis_key(url)
        await gen.multi([
            redis.set(key, json.dumps(save, ensure_ascii=True).encode('utf-8')),
            redis.expire(key, 15 * 24 * 60 * 60 * 1000.)  # 15days
        ])


def _make_redis_key(url):
    return '{}:ogp:{}'.format(__name__, url)
