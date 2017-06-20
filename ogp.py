# -*- coding: utf-8 -*-
"""
1. og:url, canonical両方ない → そのページのogp
2. og:urlだけ → og:urlのogp
3. canonicalだけ → canonicalのogp
4. 両方 → og:urlのogp
"""
import re

from bs4 import BeautifulSoup

OG_NODES_REX = re.compile(r'^og:')
HEADING_NODES_REX = re.compile(r'h\d')


def parse_ogp(html):
    """htmlを与えられたら、ParseしてOGPとcanonicalを返す
    """
    doc = BeautifulSoup(html, 'html.parser')
    if not doc or not doc.html or not doc.html.head:
        return {}

    rv = {}
    # meta og
    for node in doc.html.head.find_all('meta', property=OG_NODES_REX):
        if 'content' in node.attrs:
            rv[node['property']] = node['content']

    # <link rel="canonical" />
    for node in doc.html.head.find_all('link', rel='canonical'):
        if 'href' in node.attrs:
            rv['link:canonical'] = node['href']

    for key in ['image', 'title', 'type', 'description']:
        try:
            val = globals()['scrape_{}'.format(key)](doc)
        except AttributeError:
            pass
        else:
            if val:
                rv['scrape:{}'.format(key)] = val

    return rv


def scrape_image(doc):
    try:
        for node in doc.html.body.findAll('img'):
            if 'src' in node.attrs:
                return node['src']
    except AttributeError:
        return None


def scrape_title(doc):
    return doc.html.head.title.text


def scrape_type(doc):
    return 'other'


def scrape_description(doc):
    nodes = doc.html.head.findAll(
        'meta',
        attrs={"name": ("description", "DC.description", "eprints.abstract")})
    for node in nodes:
        content = node.get('content')
        if content:
            return content.strip()
    else:
        heading = doc.html.find(HEADING_NODES_REX)
        if heading:
            return heading.text.strip()
        else:
            node = doc.html.find('p')
            if node:
                return node.text.strip()


if __name__ == '__main__':
    import sys
    meta = parse_ogp(sys.stdin.read())
    for key, value in meta.items():
        print(key, value)
