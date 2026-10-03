#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Генератор OG-карточек 1200×630 для zapahstarosti.ru.

Шаблон снят с существующих картинок 26.09.2026:
  левая полоса 15 px #7C9AB7, вертикальный градиент фона,
  «запах старости.ru» → раздел → крупный серифный заголовок → линейка → подвал.

Запуск:  python3 og_generate.py [--out ДИРЕКТОРИЯ] [--only СТРАНИЦА]
Без аргументов перезаписывает images/og/*.jpg в репозитории сайта.
"""
import argparse
import glob
import os
import re
import sys

from PIL import Image, ImageDraw, ImageFont

FONTS = '/usr/share/fonts/truetype/dejavu/'
SERIF_BOLD = FONTS + 'DejaVuSerif-Bold.ttf'
SANS_BOLD = FONTS + 'DejaVuSans-Bold.ttf'
SANS = FONTS + 'DejaVuSans.ttf'

W, H = 1200, 630
BAR = (123, 154, 183)          # левая полоса
BG_TOP = (244, 247, 254)       # градиент фона
BG_BOTTOM = (220, 232, 246)
C_SITE = (94, 121, 148)        # «запах старости.ru»
C_SECTION = (141, 149, 160)    # раздел
C_TITLE = (44, 51, 59)         # заголовок
C_RULE = (200, 212, 226)       # линейка
C_FOOTER = (140, 150, 162)     # подвал

X_TEXT = 72                    # левый край текста
X_RULE_END = 1126
SITE_TEXT = 'запах старости.ru'
FOOTER_TEXT = 'Научно-практический ресурс  •  без стыда и опасных советов'
MAX_TITLE_LINES = 3
TITLE_MAX_W = 1050

# Разделы OG-карточек. Совпадают с теми, что были нарисованы на прежних
# картинках: таксономия шире хлебных крошек и живёт только в этих файлах.
SECTIONS = {
    'chto-takoe-2-nonenal': 'НАУЧНАЯ БАЗА',
    'faq': 'ЗАПАХ СТАРОСТИ',
    'home': 'ЗАПАХ СТАРОСТИ',
    'kak-otlichit-istochnik-zapakha': 'ДИАГНОСТИКА',
    'kak-pogovorit-s-blizkim': 'КАК ПОГОВОРИТЬ',
    'kak-ubrat-zapah-iz-shkafa': 'ДОМ И ВОЗДУХ',
    'kak-ubrat-zapah-s-divana': 'ДОМ И ВОЗДУХ',
    'kak-ubrat-zapah-s-matrasa': 'ДОМ И ВОЗДУХ',
    'kak-ubrat-zapah-v-sanuzle': 'ДОМ И ВОЗДУХ',
    'kak-ubrat-zapah-v-stiralnoj-mashine': 'СТИРКА',
    'karta-kvartiry': 'ДОМ И ВОЗДУХ',
    'karta-osetii': 'О ПРОЕКТЕ',
    'kogda-k-vrachu': 'КОГДА К ВРАЧУ',
    'kviz': 'ДИАГНОСТИКА',
    'lekarstva-i-zapah': 'КОГДА К ВРАЧУ',
    'material-metod': 'ОДЕЖДА И ТЕКСТИЛЬ',
    'nabor': 'ПРОДУКТЫ',
    'o-proekte': 'О ПРОЕКТЕ',
    'ochistitel-vozduha': 'ДОМ И ВОЗДУХ',
    'odezhda-i-tekstil': 'ОДЕЖДА И ТЕКСТИЛЬ',
    'poroshok-dlya-tekstila': 'СТИРКА',
    'sredstva-ot-zapaha': 'СРЕДСТВА',
    'tonik-protirka': 'ТЕЛО И КОЖА',
    'ubrat-zapah': 'ТЕЛО И КОЖА',
    'ventilyatsiya-i-vlazhnost': 'ДОМ И ВОЗДУХ',
    'zapah-v-kvartire': 'ДОМ И ВОЗДУХ',
}

# Путь к рабочему репозиторию сайта. В архиве сайта нет — он живёт отдельно.
# Задаётся переменной окружения SITE_REPO; значение по умолчанию сохранено
# для совместимости с прежней рабочей средой автора.
SITE = os.environ.get('SITE_REPO', '/home/user/zapahstarosti')


def background():
    """Вертикальный градиент + левая полоса."""
    img = Image.new('RGB', (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / (H - 1)
        c = tuple(round(BG_TOP[i] + (BG_BOTTOM[i] - BG_TOP[i]) * t) for i in range(3))
        d.line([(0, y), (W, y)], fill=c)
    d.rectangle([0, 0, 15, H], fill=BAR)
    return img


def text_w(font, s, tracking=0):
    w = sum(font.getbbox(ch)[2] for ch in s)
    return w + tracking * max(0, len(s) - 1)


def draw_tracked(draw, xy, s, font, fill, tracking=0):
    x, y = xy
    for ch in s:
        draw.text((x, y), ch, font=font, fill=fill)
        x += font.getbbox(ch)[2] + tracking


def wrap(title, font, max_w, max_lines):
    """Перенос по словам; возвращает (строки, уместились_ли)."""
    words = title.split()
    lines, cur = [], ''
    for w in words:
        trial = (cur + ' ' + w).strip()
        if font.getbbox(trial)[2] - font.getbbox(trial)[0] <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines, len(lines) <= max_lines


def render(section, title, path):
    img = background()
    d = ImageDraw.Draw(img)

    d.text((X_TEXT, 64), SITE_TEXT, font=ImageFont.truetype(SANS_BOLD, 30), fill=C_SITE)
    draw_tracked(d, (X_TEXT, 120), section, ImageFont.truetype(SANS_BOLD, 21), C_SECTION, 2)

    size = 62
    while size > 34:
        font = ImageFont.truetype(SERIF_BOLD, size)
        lines, ok = wrap(title, font, TITLE_MAX_W, MAX_TITLE_LINES)
        if ok:
            break
        size -= 2
    else:
        font = ImageFont.truetype(SERIF_BOLD, 34)
        lines, _ = wrap(title, font, TITLE_MAX_W, MAX_TITLE_LINES)

    lh = round(size * 1.22)
    y = 209
    for ln in lines:
        d.text((73, y), ln, font=font, fill=C_TITLE)
        y += lh

    d.line([(X_TEXT, 528), (X_RULE_END, 528)], fill=C_RULE, width=2)
    d.text((X_TEXT, 561), FOOTER_TEXT, font=ImageFont.truetype(SANS, 25), fill=C_FOOTER)

    img.save(path, 'JPEG', quality=92, optimize=True)
    return len(lines), size


def page_title(page):
    """og:image:alt страницы — то, что нарисовано на карточке."""
    path = os.path.join(SITE, page, 'index.html') if page != 'home' else os.path.join(SITE, 'index.html')
    h = open(path, encoding='utf-8').read()
    m = re.search(r'og:image:alt"[^>]+content="([^"]*)"', h)
    return m.group(1) if m else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=os.path.join(SITE, 'images', 'og'))
    ap.add_argument('--only', default=None)
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    pages = [args.only] if args.only else sorted(SECTIONS)
    bad = []
    for page in pages:
        section = SECTIONS[page]
        title = page_title(page)
        if not title:
            bad.append(page)
            print(f"  ! {page}: нет og:image:alt, пропуск")
            continue
        out = os.path.join(args.out, page + '.jpg')
        lines, size = render(section, title, out)
        print(f"  {page + '.jpg':40} {lines} стр., {size} px, {os.path.getsize(out)//1024} КБ")
    if bad:
        sys.exit(1)


if __name__ == '__main__':
    main()
