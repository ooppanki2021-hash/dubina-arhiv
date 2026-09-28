#!/usr/bin/env python3
"""Инструмент против ошибок «предположил вместо проверки».

Зачем: почти все промахи помощника имели одну природу — он шёл от памяти,
а не от фактического ответа. Отсюда четыре инструмента, которые заставляют
смотреть сначала, а писать код под реальную форму данных потом.

  probe   — сырой ответ API + разбор его формы. Перед любым выводом из API.
  shape   — разбор формы JSON (словарь или список? какие ключи?).
  clean   — чистка HTML от служебного мусора перед любым сравнением текстов.
  main    — только содержимое <main>, без меню и подвала.

Примеры:
  python3 не_угадывать.py probe "https://api-metrica.yandex.net/stat/v1/data?id=1&metrics=ym:s:visits"
  python3 не_угадывать.py probe --token-env YANDEX_TOKEN "https://api.webmaster.yandex.net/v4/user"
  python3 не_угадывать.py shape /tmp/metrika.json
  python3 не_угадывать.py clean страница.html --text
  python3 не_угадывать.py clean a.html b.html      # сравнить две страницы после чистки

Правило, которое здесь автоматизировано: сначала сырой ответ, потом код под него.
"""
import argparse
import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

MAX_RAW = 2500          # сколько знаков сырого ответа печатать
MAX_DEPTH = 4           # глубина разбора формы

# --------------------------------------------------------------------------- #
# probe: сырой ответ API и его форма
# --------------------------------------------------------------------------- #

def probe(url, token=None, header=None, raw_len=MAX_RAW):
    req = urllib.request.Request(url, method="GET")
    req.add_header("User-Agent", "probe/1.0")
    if token:
        req.add_header("Authorization", token)
    for h in header or []:
        if ":" in h:
            k, v = h.split(":", 1)
            req.add_header(k.strip(), v.strip())
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        with urllib.request.urlopen(req, timeout=90, context=ctx) as r:
            status, body = r.status, r.read().decode("utf-8", "replace")
            hdrs = dict(r.headers)
    except urllib.error.HTTPError as e:
        status, body = e.code, e.read().decode("utf-8", "replace")
        hdrs = dict(e.headers)
    except Exception as e:
        print(f"ОШИБКА ЗАПРОСА: {e}")
        return 1

    print("=" * 72)
    print("СЫРОЙ ОТВЕТ — сначала он, потом любой вывод")
    print("=" * 72)
    print(f"HTTP {status}")
    for k in ("Content-Type", "X-Content-Type-Options", "Retry-After"):
        if k in hdrs:
            print(f"{k}: {hdrs[k]}")
    print()
    print(body[:raw_len])
    if len(body) > raw_len:
        print(f"... [ещё {len(body) - raw_len} знаков]")
    print()

    print("=" * 72)
    print("РАЗБОР ФОРМЫ")
    print("=" * 72)
    try:
        obj = json.loads(body)
    except Exception:
        print("Ответ не JSON — дальше разбирать нечего. Читайте сырой ответ выше.")
        return 0
    describe(obj)
    return 0


def describe(obj, depth=0, path="$"):
    pad = "  " * depth
    if isinstance(obj, dict):
        print(f"{pad}{path}: объект, ключей {len(obj)}")
        if depth >= MAX_DEPTH:
            print(f"{pad}  ... (глубже не смотрю)")
            return
        for k, v in obj.items():
            describe(v, depth + 1, f"{path}.{k}")
    elif isinstance(obj, list):
        print(f"{pad}{path}: список, элементов {len(obj)}")
        if not obj:
            return
        if depth >= MAX_DEPTH:
            print(f"{pad}  ... (глубже не смотрю)")
            return
        describe(obj[0], depth + 1, f"{path}[0]")
    else:
        val = repr(obj)
        if len(val) > 70:
            val = val[:67] + "..."
        print(f"{pad}{path}: {type(obj).__name__} = {val}")


def shape_cmd(source):
    if source == "-":
        raw = sys.stdin.read()
    else:
        raw = open(source, encoding="utf-8").read()
    try:
        obj = json.loads(raw)
    except Exception as e:
        print(f"Не JSON: {e}")
        return 1
    describe(obj)
    return 0


# --------------------------------------------------------------------------- #
# clean: снять служебный мусор перед сравнением текстов
# --------------------------------------------------------------------------- #

BORING_TAGS = {"header", "footer", "nav", "aside", "script", "style",
               "svg", "noscript", "template", "form"}
BORING_ATTR = re.compile(
    r"cookie|consent|banner|agree|accept|gdpr|social|share|breadcrumb|"
    r"menu|nav|sidebar|widget|promo|subscribe", re.I)


class Cleaner(HTMLParser):
    """Выдаёт текст, выбросив служебные блоки.

    Служебное: header, footer, nav, aside, script, style, svg, form и любой
    элемент, у которого id/class похож на баннер согласия, меню или подвал.
    С main_only=True берётся только то, что внутри <main>.
    """

    def __init__(self, main_only=False):
        super().__init__(convert_charrefs=True)
        self.main_only = main_only
        self.stack = []          # [(тег, это_мусор)]
        self.out = []

    @property
    def in_boring(self):
        return any(b for _, b in self.stack)

    @property
    def in_main(self):
        return any(t == "main" for t, _ in self.stack)

    def _is_boring(self, tag, attrs):
        if tag in BORING_TAGS:
            return True
        for k, v in attrs:
            if k in ("id", "class") and v and BORING_ATTR.search(v):
                return True
        return False

    def handle_starttag(self, tag, attrs):
        self.stack.append((tag, self._is_boring(tag, attrs)))

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        if self.in_boring:
            return
        if self.main_only and not self.in_main:
            return
        s = " ".join(data.split())
        if s:
            self.out.append(s)

    def text(self):
        return "\n".join(self.out)


def clean_one(path, main_only=False):
    html = open(path, encoding="utf-8").read()
    c = Cleaner(main_only=main_only)
    c.feed(html)
    c.close()
    return c.text()


def clean_cmd(paths, main_only, show_text):
    texts = {}
    for p in paths:
        if not os.path.exists(p):
            print(f"Нет файла: {p}")
            return 1
        texts[p] = clean_one(p, main_only=main_only)
        words = len(texts[p].split())
        print(f"{p}: {words} слов после чистки"
              f"{' (только <main>)' if main_only else ''}")
        if show_text:
            print("-" * 72)
            print(texts[p][:3000])
            print("-" * 72)
        # проверка, что мусор действительно ушёл
        for marker in ("Настройки cookie", "Согласие на обработку",
                       "Владелец сайта", "zsConsent"):
            if marker in texts[p]:
                print(f"   ! мусорное «{marker}» осталось — чистилка неточна")
    if len(paths) == 2:
        a, b = paths
        wa, wb = set(texts[a].split()), set(texts[b].split())
        inter = wa & wb
        union = wa | wb
        j = len(inter) / len(union) if union else 0
        print(f"\nПересечение двух страниц после чистки:")
        print(f"   общих слов {len(inter)} из {len(union)} уникальных, "
              f"Жаккар {j:.3f}")
        if j > 0.4:
            print("   ! высоко — проверьте, не сравниваете ли вы меню с подвалом")
        else:
            print("   нормально, служебный мусор не мешает")
    return 0


# --------------------------------------------------------------------------- #

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("probe", help="сырой ответ API + разбор формы")
    p.add_argument("url")
    p.add_argument("--token-env", help="имя переменной окружения с токеном")
    p.add_argument("--token", help="токен прямо (не для публичных файлов)")
    p.add_argument("--header", action="append", help="заголовок 'Имя: значение'")
    p.add_argument("--raw-len", type=int, default=MAX_RAW)

    s = sub.add_parser("shape", help="разбор формы JSON")
    s.add_argument("source", help="файл или - для stdin")

    c = sub.add_parser("clean", help="чистка HTML от служебного мусора")
    c.add_argument("paths", nargs="+")
    c.add_argument("--main", action="store_true", help="только <main>")
    c.add_argument("--text", action="store_true", help="печатать очищенный текст")

    args = ap.parse_args()

    if args.cmd == "probe":
        token = args.token
        if not token and args.token_env:
            token = os.environ.get(args.token_env, "")
            if not token:
                print(f"Переменная {args.token_env} пуста или не задана")
                return 1
        if token and not token.lower().startswith(("oauth ", "bearer ", "token ")):
            token = "OAuth " + token
        return probe(args.url, token=token, header=args.header,
                     raw_len=args.raw_len)
    if args.cmd == "shape":
        return shape_cmd(args.source)
    if args.cmd == "clean":
        return clean_cmd(args.paths, args.main, args.text)
    return 1


if __name__ == "__main__":
    sys.exit(main())
