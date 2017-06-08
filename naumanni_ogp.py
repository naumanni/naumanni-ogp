# -*- coding: utf-8 -*-
"""
Statusの中のURLをみて、そのURLのOGP情報を返す

もってなければ、クロールしておく。次アクセスした時に見られる。
この実装だと、Naumanniが流行った時に同じURLへのクロールがたくさんceleryに貯まってヤバそう
"""
import datetime
import json
import logging
from tornado import httpclient

from celery import current_app as current_celeryapp, chain

from naumanni import celery as naumanni_celery
from naumanni.plugin import Plugin
try:
    from .ogp import parse_ogp
except:
    from ogp import parse_ogp


USER_AGENT = 'Naumannibot-ogp/1.0'

logger = logging.getLogger(__name__)


class OGPPlugin(Plugin):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def on_filter_statuses(self, objects, entities):
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
        # TODO: flaskの方から取るべきでは
        redis = current_celeryapp.naumanni.redis
        urls = list(url_map.keys())
        cached = redis.mget([_make_redis_key(u) for u in urls])
        for url, cached_meta in zip(urls, cached):
            if cached_meta:
                cached_meta = json.loads(cached_meta)
                statuses = url_map.pop(url)
                for status in statuses:
                    status.add_extended_attributes('ogp', cached_meta)

        # 2. 全部celeryする。次回アクセスした時にogpが乗ってる
        logger.debug('url_map : %r', url_map)
        for url in url_map.keys():
            job = chain(
                crawl_ogp_url.s(url),
                process_meta.s()
            )
            job()

        return objects


@naumanni_celery.task
def crawl_ogp_url(url):
    """urlをクロールして、ogpなどの情報を返す

    :param str url: クロール対象のurl
    """
    logger.debug('crawl_ogp_url %r', url)
    assert url.startswith('http://') or url.startswith('https://')
    http_client = httpclient.HTTPClient()
    # TODO: User-Agent
    response = http_client.fetch(url, raise_error=False, user_agent=USER_AGENT)
    if response.code == 200:
        content_type = response.headers['Content-Type']
        if ';' in content_type:
            content_type = content_type.split(';', 1)[0]
        if content_type.lower() == 'text/html':
            meta = parse_ogp(response.body)
            meta['status_code'] = 200
            return url, meta
        else:
            meta = {
                'status_code': 200,
                'content_type': content_type.lower()
            }
            return url, meta

    elif 300 <= response.code < 400:
        # redirect
        location = response.headers['Location']
        return url, {'status_code': response.code, 'redirect': location}
    else:
        return url, {'status_code': response.code}


@naumanni_celery.task
def process_meta(url, meta=None, original_url=None):
    """metaの情報を解釈して保存する"""
    if isinstance(url, (list, tuple)):
        url, meta = url
    logger.debug('process_meta: %s -> %r', url, meta)
    if not original_url:
        original_url = url

    # redirect, og:url, link:canonical 的に、さらに見に行かないと行けないurl
    next_url = None
    save = None
    now = datetime.datetime.utcnow().isoformat()

    if meta['status_code'] == 200:
        if url != original_url:
            if meta.get('og:url') != url:
                next_url = meta['og:url']
            elif meta.get('link:canonical') != url:
                next_url = meta['link:canonical']

        if 'content_type' in meta:
            # not html
            save = meta.copy()
        else:
            save = {
                'date_crawled': now,
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

    # redis phase
    redis = current_celeryapp.naumanni.redis

    # 次のクロール先に既に結果があるかチェック
    if next_url:
        cached = redids.get(_make_redis_key(next_url))
        if cached:
            save = cached
            next_url = None

    # 保存するものがあれば保存
    if save:
        expires = datetime.timedelta(days=15)
        save = json.dumps(save, ensure_ascii=True).encode('utf-8')
        with redis.pipeline() as pipe:
            for u in set([url, original_url]):
                key = _make_redis_key(u)
                pipe.set(key, save)
                pipe.expire(key, expires)
                logger.debug('save meta: %s -> %r', key, save)
            pipe.execute()

    # 次にfetchするものがあれば、それ
    if next_url:
        if next_url.startswith('http://') or next_url.startswith('https://'):
            job = chain(
                crawl_ogp_url.s(next_url),
                process_meta.s(original_url=original_url)
            )
            job()


def _make_redis_key(url):
    return '{}:ogp:{}'.format(__name__, url)


if __name__ == '__main__':
    import sys

    url, meta = crawl_ogp_urls(sys.argv[1])
    for k, v in meta.items():
        print(k, v)
