#!/usr/bin/env python3
"""Переобход страниц zapahstarosti.ru через API Яндекс.Вебмастера.

ПО УМОЛЧАНИЮ ТОЛЬКО ПРЕДЛАГАЕТ (решение автора 28.09.2026): проверяет URL,
очередь и квоту, печатает список того, что можно отправить, и НИЧЕГО не отправляет.
Чтобы реально поставить в очередь, нужен явный флаг --send.

Что делает:
  1. сам находит рабочую версию API (пробует v4.2 -> v4.1 -> v4);
  2. читает URL из сitemap снимка архива и проверяет, что они отдают 200;
  3. пропускает URL, которые уже стоят в очереди на переобход;
  4. без --send печатает предложение; с --send ставит в очередь и показывает квоту.

Важно (решение автора 28.09.2026): отправлять ТОЛЬКО страницы, которые
действительно изменились. Гнать весь сайт залпом — трата квоты впустую:
робот придёт, увидит то же самое и ничего не изменит. Квота — 150 URL в сутки.

Использование:
  python3 /home/user/webmaster_recrawl.py                          # весь sitemap, только предложение
  python3 /home/user/webmaster_recrawl.py --urls /,/faq/,/kviz/    # выбранные страницы
  python3 /home/user/webmaster_recrawl.py --urls spisok.txt        # список из файла
  python3 /home/user/webmaster_recrawl.py --since 2026-09-27       # у кого lastmod свежее даты
  python3 /home/user/webmaster_recrawl.py --urls /,/faq/ --send    # реально отправить
  python3 /home/user/webmaster_recrawl.py --force                  # не пропускать уже queued

Порядок при правке страницы: опубликовать -> обновить lastmod в sitemap.xml
-> отправить на переобход только изменённые страницы.
"""
import argparse
import json
import os
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path
import xml.etree.ElementTree as ET

def load_token():
    """Токен Яндекса: переменная окружения YANDEX_TOKEN или файл token.txt
    рядом со скриптом (одна строка). В архив сам токен не пишем."""
    import os
    env = os.environ.get("YANDEX_TOKEN", "").strip()
    if env:
        return env
    for name in ("token.txt", "token.env"):
        p = Path(__file__).resolve().parent / name
        if p.is_file():
            t = p.read_text(encoding="utf-8").strip().splitlines()[0].strip()
            if t:
                return t
    sys.exit("Не найден токен Яндекса. Задайте переменную окружения YANDEX_TOKEN "
             "или положите рядом файл token.txt с одной строкой — самим токеном.")


# Токен загружается при первом обращении, а не при импорте модуля: иначе скрипт
# падал на строке импорта и не давал даже --help. Ошибка остаётся той же.
TOKEN = ""


def token():
    global TOKEN
    if not TOKEN:
        TOKEN = load_token()
    return TOKEN


API = "https://api.webmaster.yandex.net"
# карта берётся из снимка архива: он всегда на месте и сверен с живым сайтом
# Карта берётся из снимка архива. Путь считаем от расположения самого скрипта,
# а не от жёстко прописанной папки: архив может лежать где угодно.
# Переопределяется переменной окружения SITEMAP.
_HERE = Path(__file__).resolve().parent
SITEMAP = Path(os.environ.get(
    "SITEMAP", _HERE.parent / "03-сайт/сайт_текущий/sitemap.xml"))
HOST = "https:zapahstarosti.ru:443"
NS = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
VERSIONS = ["v4.2", "v4.1", "v4"]  # в порядке предпочтения; мёртвые отсекаются сами


def api(version, path, method="GET", body=None):
    """Запрос к API. Возвращает (http_code, dict)."""
    req = urllib.request.Request(f"{API}/{version}{path}", method=method)
    req.add_header("Authorization", "OAuth " + token())
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, data, timeout=60) as r:
            raw = r.read().decode()
            return r.status, (json.loads(raw) if raw.strip() else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors="replace")
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"raw": raw[:300]}


def detect_version(verbose=True):
    """Первая версия API, которая отвечает на /user. На 27.09.2026 это v4."""
    for v in VERSIONS:
        code, _ = api(v, "/user")
        if code == 200:
            if verbose:
                print(f"рабочая версия API: /{v}")
            return v
        if verbose:
            print(f"  /{v} -> {code}, пробую следующую")
    sys.exit("Ни одна версия API не отвечает — проверь токен и доступ в интернет")


def live(url):
    req = urllib.request.Request(url, method="GET", headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=30, context=ssl.create_default_context()) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception as e:
        return str(e)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--send", action="store_true",
                    help="реально поставить в очередь (без флага — только предложение)")
    ap.add_argument("--force", action="store_true", help="не пропускать уже queued URL")
    ap.add_argument("--urls", default="",
                    help="свои страницы вместо всего sitemap: пути через запятую "
                         "или путь к файлу со списком. Пример: "
                         "--urls /,/faq/,/kviz/  или  --urls spisok.txt")
    ap.add_argument("--since", default="",
                    help="отправить только страницы, изменённые после этой даты "
                         "(ГГГГ-ММ-ДД) — берётся lastmod из sitemap")
    args = ap.parse_args()
    if not args.send:
        print("РЕЖИМ ПРЕДЛОЖЕНИЯ: ничего не отправляю. Для отправки добавьте --send.\n")

    version = detect_version()
    _, user = api(version, "/user")
    uid = user["user_id"]

    _, hosts = api(version, f"/user/{uid}/hosts")
    if HOST not in [h["host_id"] for h in hosts.get("hosts", [])]:
        sys.exit(f"Хост {HOST} не найден среди сайтов пользователя")

    sitemap_urls = {u.find("s:loc", NS).text:
                    (u.find("s:lastmod", NS).text if u.find("s:lastmod", NS) is not None else "")
                    for u in ET.parse(SITEMAP).getroot().findall("s:url", NS)}

    if args.urls:
        # свои страницы: список прямо в аргументе или файл
        raw = args.urls.strip()
        if Path(raw).is_file():
            items = [ln.strip() for ln in Path(raw).read_text(encoding="utf-8").splitlines()
                     if ln.strip() and not ln.strip().startswith("#")]
        else:
            items = [s.strip() for s in raw.split(",") if s.strip()]
        base = "https://zapahstarosti.ru"
        urls = []
        for i in items:
            if i.startswith("http"):
                urls.append(i)
            else:
                tail = i.strip("/")
                urls.append(base + "/" if not tail else base + "/" + tail + "/")
        outside = [u for u in urls if u not in sitemap_urls]
        if outside:
            print(f"внимание: {len(outside)} адресов нет в sitemap "
                  f"(отправлю всё равно): " + ", ".join(x.replace(base, '') for x in outside))
        print(f"выбрано страниц вручную: {len(urls)}")
    elif args.since:
        urls = [u for u, lm in sitemap_urls.items() if lm and lm[:10] > args.since]
        print(f"страниц с lastmod позже {args.since}: {len(urls)} из {len(sitemap_urls)}")
    else:
        urls = list(sitemap_urls)
        print(f"URL в sitemap: {len(urls)} — это ВЕСЬ сайт. "
              f"Лучше указать --urls или --since, чтобы не тратить квоту зря.")

    _, queue = api(version, f"/user/{uid}/hosts/{HOST}/recrawl/queue")
    busy = {t["url"]: t["state"] for t in queue.get("tasks", []) if t["state"] != "DONE"}
    if busy:
        print(f"уже в очереди ({len(busy)}): " + ", ".join(sorted(set(busy.values()))))

    _, quota = api(version, f"/user/{uid}/hosts/{HOST}/recrawl/quota")
    print(f"суточная квота: {quota.get('daily_quota')}, осталось: {quota.get('quota_remainder')}")

    ok, bad, sent, skipped = [], [], 0, 0
    for url in urls:
        if url in busy and not args.force:
            skipped += 1
            print(f"  --  {url} уже в очереди ({busy[url]}), пропускаю")
            continue
        code = live(url)
        if code != 200:
            bad.append((url, code))
            print(f"  !!  {url} -> {code}, не отправляю")
            continue
        ok.append(url)
        if not args.send:
            print(f"  ..  {url} -> готов к отправке")
            continue
        status, resp = api(version, f"/user/{uid}/hosts/{HOST}/recrawl/queue", "POST", {"url": url})
        if status in (200, 201, 202):
            sent += 1
            print(f"  ok  {url} -> задача {resp.get('task_id')} (квота осталась {resp.get('quota_remainder')})")
        else:
            print(f"  ERR {url} -> HTTP {status} {json.dumps(resp, ensure_ascii=False)[:200]}")

    if not args.send:
        print(f"\nитог: живых {len(ok)}, мёртвых {len(bad)}, пропущено {skipped}, "
              f"к отправке предложено {len(ok) - sent}")
        print("Ничего не отправлено. Покажите этот список автору; "
              "при согласии запустите с --send.")
        return 0
    print(f"\nитог: живых {len(ok)}, мёртвых {len(bad)}, пропущено {skipped}, отправлено {sent}")
    _, quota = api(version, f"/user/{uid}/hosts/{HOST}/recrawl/quota")
    print(f"остаток квоты на сегодня: {quota.get('quota_remainder')}")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
