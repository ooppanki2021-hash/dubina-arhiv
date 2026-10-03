#!/usr/bin/env python3
"""Read-only, offline integrity check for the dubina-arhiv archive.

Uses only the Python 3 standard library. Does not edit files or access the network.

Baseline: 01_НАЧНИ_ОТСЮДА/КОНТРОЛЬ_СОХРАННОСТИ.json (schema 2, 27.09.2026).
Site snapshot: 03-сайт/сайт_текущий + 03-сайт/СВЕРКА_ПУБЛИКАЦИИ.json.
"""
from pathlib import Path
from hashlib import sha256
from html.parser import HTMLParser
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser
import json
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
CONTROL = ROOT / '01_НАЧНИ_ОТСЮДА/КОНТРОЛЬ_СОХРАННОСТИ.json'
PUBLICATION = ROOT / '03-сайт/СВЕРКА_ПУБЛИКАЦИИ.json'
SITE = ROOT / '03-сайт/сайт_текущий'
MANIFEST_PATH = '01_НАЧНИ_ОТСЮДА/КОНТРОЛЬ_СОХРАННОСТИ.json'
errors = []


def require(condition, message):
    if not condition:
        errors.append(message)


def file_at(relative):
    path = (ROOT / relative).resolve()
    if ROOT not in path.parents:
        raise ValueError('Путь вне архива: ' + relative)
    return path


_DIGEST_CACHE = {}


def digest(path):
    """SHA-256 файла с запоминанием результата.

    Без кэша один прогон хешировал 39 МБ трижды: 284 файла в инвентаре, затем
    те же 36 защищённых, затем те же 179 файлов снимка — 499 хешей вместо 284.
    Кэш безопасен, потому что этот скрипт ничего не записывает: содержимое
    файлов за один прогон не меняется.
    """
    key = str(Path(path).resolve())
    cached = _DIGEST_CACHE.get(key)
    if cached is None:
        cached = sha256(Path(path).read_bytes()).hexdigest()
        _DIGEST_CACHE[key] = cached
    return cached


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.h1 = 0
        self.robots = []
        self.ids = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'h1':
            self.h1 += 1
        if tag == 'meta' and attrs.get('name', '').lower() == 'robots':
            self.robots.append(attrs.get('content', '').lower())
        if attrs.get('id'):
            self.ids.append(attrs['id'])


def sitemap(name):
    return [n.text for n in ET.parse(SITE / name).iter()
            if n.tag.rsplit('}', 1)[-1] == 'loc']


def main():
    control = json.loads(CONTROL.read_text(encoding='utf-8'))
    publication = json.loads(PUBLICATION.read_text(encoding='utf-8'))

    # --- манифест целостности ---------------------------------------------
    inventory = [item for item in control['files'] if item['path'] != MANIFEST_PATH]
    require(control['deleted_files'] == [], 'В манифесте указаны удаления')
    require(len(inventory) == control['counts']['files'] - 1,
            'Инвентарь манифеста не сходится с counts')
    for item in inventory:
        p = file_at(item['path'])
        require(p.is_file(), 'Отсутствует файл архива: ' + item['path'])
        if p.is_file():
            require(digest(p) == item['sha256'],
                    'Файл отличается от манифеста: ' + item['path'])
    for relative in control['protected_unchanged_files']:
        item = next((x for x in inventory if x['path'] == relative), None)
        require(item is not None, 'Защищённый файл не описан в манифесте: ' + relative)
        if item:
            require(digest(file_at(relative)) == item['sha256'],
                    'Изменён защищённый файл: ' + relative)

    # --- снимок публикации -------------------------------------------------
    require(publication['source_commit'] and publication['source_files'],
            'В сверке не указан источник')
    for item in publication['source_files']:
        p = file_at('03-сайт/сайт_текущий/' + item['path'])
        require(p.is_file() and digest(p) == item['sha256'],
                'Снимок расходится с публикацией: ' + item['path'])
    require(len(publication['http_checks']) == len(publication['source_files']) - 1,
            'Ожидалось HTTP-сопоставление для каждого файла, кроме CNAME')
    require(all(x.get('status') == 200 and x.get('matches_source')
                for x in publication['http_checks']), 'Неуспешное HTTP-сопоставление')

    # --- карты страниц, robots, разметка -----------------------------------
    full = sitemap('sitemap-full.xml')
    main_urls = sitemap('sitemap.xml')
    require(len(full) == len(set(full)) == publication['sitemap_full_urls'],
            'Полная карта не сходится с журналом сверки')
    require(len(main_urls) == len(set(main_urls)) == publication['sitemap_urls'],
            'Основная карта не сходится с журналом сверки')

    robots = RobotFileParser()
    robots.parse((SITE / 'robots.txt').read_text(encoding='utf-8').splitlines())
    open_urls, closed_urls = set(), set()
    pages = sorted(SITE.glob('*/index.html')) + [SITE / 'index.html']
    for page in pages:
        relative = page.relative_to(SITE).as_posix()
        url = 'https://zapahstarosti.ru/' + (relative[:-len('index.html')] or '')
        parsed = Page()
        parsed.feed(page.read_text(encoding='utf-8'))
        require(parsed.h1 == 1, 'Не один H1: ' + url)
        require(len(parsed.ids) == len(set(parsed.ids)), 'Дубли id: ' + url)
        if any('noindex' in directive for directive in parsed.robots):
            closed_urls.add(url)
        else:
            open_urls.add(url)
            require(robots.can_fetch('*', url), 'Открытый URL заблокирован robots.txt: ' + url)
    expected_closed = (set(publication['noindex_content'])
                       | set(publication.get('service_pages_noindex', [])))
    require(closed_urls == expected_closed,
            'Изменился список закрытых контентных URL')
    require(open_urls == set(main_urls),
            'Открытые страницы не совпадают с основной картой')

    # --- трекер и упаковка -------------------------------------------------
    newer = ROOT / '05_приложение/app/index.html'
    standalone = ROOT / '05_приложение/МЕЧТА_автономная_копия.html'
    require(newer.read_bytes() == standalone.read_bytes(),
            'Новая PWA и автономная копия расходятся')
    for key, path in (('published', SITE / 'app/index.html'),
                      ('newer_unpublished', newer)):
        record = publication['tracker_versions'][key]
        require(digest(path) == record['sha256'],
                'Версия трекера не сохранена: ' + key)
        require(path.stat().st_size == record['bytes'],
                'Размер версии трекера изменился: ' + key)

    png = {item['path'] for item in inventory
           if item['path'].startswith('04_упаковка/финальные_макеты/')
           and item['path'].endswith('.png')}
    require(len(png) == len(list((ROOT / '04_упаковка/финальные_макеты').glob('*.png'))),
            'Количество PNG-макетов расходится с манифестом')

    if errors:
        print('Проверка не пройдена:')
        for message in errors:
            print(' - ' + message)
        return 1
    print('Проверка пройдена.')
    # len(inventory) на единицу меньше counts['files']: сам манифест исключён из
    # списка, чтобы не сверять его хеш с самим собой. Раньше строка печаталась как
    # «в инвентаре N файлов» и расходилась с manifest_files на единицу — выглядело
    # как расхождение, которого на самом деле нет.
    print(f'В инвентаре {len(inventory)} файлов + сам манифест = {control["counts"]["files"]}; '
          f'удалений нет; {len(control["protected_unchanged_files"])} защищённых файлов на месте.')
    print(f'Снимок сверен с {len(publication["source_files"])} файлами публикации '
          f'(сайт, коммит {publication["source_commit"][:7]}).')
    print(f'{len(publication["http_checks"])} HTTP-сопоставлений относятся к дате журнала; '
          'сетевых запросов эта проверка не делает.')
    print(f'Открытых контентных URL {len(open_urls)}, закрытых {len(closed_urls)}.')
    print('Новая версия приложения и автономная копия совпадают; опубликованная сохранена отдельно.')
    print('Это проверка архивного обновления, не испытание продукции и не полный тест функций сайта.')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, ET.ParseError) as exc:
        print('Не удалось проверить архив: ' + str(exc), file=sys.stderr)
        sys.exit(1)
