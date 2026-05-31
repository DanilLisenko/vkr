import re
from django import template

register = template.Library()

TRANSLIT_MAP = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo',
    'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'j', 'к': 'k', 'л': 'l', 'м': 'm',
    'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
    'ф': 'f', 'х': 'kh', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch',
    'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
}


@register.filter
def translit_slug(value):
    value = str(value).lower()
    result = ''
    for char in value:
        result += TRANSLIT_MAP.get(char, char)
    result = re.sub(r'[^a-z0-9]+', '-', result).strip('-')
    return result


@register.filter
def lookup(d, key):
    if isinstance(d, dict):
        return d.get(key, '')
    return ''


@register.filter
def youtube_embed_url(url):
    if not url:
        return ''
    url = str(url)
    match = re.search(r'(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})', url)
    if match:
        return f'https://www.youtube.com/embed/{match.group(1)}'
    return url
