#!/usr/bin/env python3
"""Актуализация снимка сайта в архиве dubrava.

1. Копирует все файлы рабочего репозитория zapahstarosti в 03-сайт/сайт_текущий/
   (ничего не удаляет; локальные технические MD снимка сохраняются).
2. Сверяет каждый файл с живым сайтом: HTTP-статус и SHA-256.
3. Перезаписывает 03-сайт/СВЕРКА_ПУБЛИКАЦИИ.json, сохраняя все прежние ключи
   и добавляя запись illustrations_2026_09_27.

Сетевых удалений и правок сайта не делает.
"""
import json
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path

SITE_REPO = Path("/home/user/zapahstarosti")
ARCHIVE = Path("/home/user/dubrava")
SNAPSHOT = ARCHIVE / "03-сайт/сайт_текущий"
PUBLICATION = ARCHIVE / "03-сайт/СВЕРКА_ПУБЛИКАЦИИ.json"
SITE = "https://zapahstarosti.ru"
NS = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}

# локальные документы снимка, которых нет в репозитории сайта
LOCAL_DOCS = {"КОНСТРУКТОР_как_устроен.md", "ОПИСЬ.md", "ТЕХРЕГЛАМЕНТ_СТРАНИЦЫ.md"}


def repo_files():
    out = subprocess.run(["git", "ls-files"], cwd=SITE_REPO, capture_output=True,
                         text=True, check=True).stdout.split()
    return sorted(out)


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def url_for(rel):
    if rel == "index.html":
        return SITE + "/"
    if rel.endswith("/index.html"):
        return SITE + "/" + rel[: -len("index.html")]
    return SITE + "/" + rel


def fetch(url):
    req = urllib.request.Request(url, method="GET", headers={"User-Agent": "archive-sync/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=60, context=ssl.create_default_context()) as r:
            return r.status, r.geturl(), r.read()
    except urllib.error.HTTPError as e:
        return e.code, url, b""
    except Exception as e:
        return str(e), url, b""


def main():
    files = repo_files()
    print(f"файлов в репозитории сайта: {len(files)}")

    # 1. копируем публикацию в снимок, ничего не удаляя
    copied, updated = 0, 0
    for rel in files:
        src = SITE_REPO / rel
        dst = SNAPSHOT / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.exists():
            copied += 1
        elif dst.read_bytes() != src.read_bytes():
            updated += 1
        dst.write_bytes(src.read_bytes())
    print(f"скопировано новых: {copied}, обновлено: {updated}")

    # локальные документы снимка должны остаться на месте
    for name in LOCAL_DOCS:
        assert (SNAPSHOT / name).is_file(), "потерян локальный документ снимка: " + name

    # 2. журнал файлов публикации
    source_files = [{"path": rel, "bytes": (SNAPSHOT / rel).stat().st_size,
                     "sha256": digest(SNAPSHOT / rel)} for rel in files]

    # 3. HTTP-сверка с живым сайтом
    targets = [(rel, url_for(rel)) for rel in files if rel != "CNAME"]

    def check(item):
        rel, url = item
        status, final, body = fetch(url)
        return {"path": rel, "url": url, "final_url": final, "status": status,
                "bytes": len(body), "sha256": sha256(body).hexdigest() if body else "",
                "matches_source": bool(body) and sha256(body).hexdigest() == digest(SNAPSHOT / rel)}

    with ThreadPoolExecutor(max_workers=8) as pool:
        http_checks = list(pool.map(check, targets))
    bad = [x for x in http_checks if x["status"] != 200 or not x["matches_source"]]
    print(f"HTTP-сверка: {len(http_checks)} адресов, расхождений: {len(bad)}")
    for x in bad[:20]:
        print("  !!", x["path"], x["status"], "совпадает:", x["matches_source"])
    if bad:
        sys.exit("Сверка с живым сайтом не пройдена — архив не обновляю")

    # 4. содержание карт и страниц
    def locs(name):
        return [n.text for n in ET.parse(SNAPSHOT / name).getroot().iter()
                if n.tag.rsplit("}", 1)[-1] == "loc"]

    full, main_urls = locs("sitemap-full.xml"), locs("sitemap.xml")
    # контентные страницы: всё, кроме PWA-трекера и юридических страниц
    service = {"app", "politika-konfidencialnosti", "soglasie-na-obrabotku"}
    pages = [p for p in sorted(SNAPSHOT.glob("*/index.html"))
             if p.parent.name not in service] + [SNAPSHOT / "index.html"]
    noindex = []
    for page in pages:
        text = page.read_text(encoding="utf-8")
        if "noindex" in text.lower():
            noindex.append(SITE + "/" + page.parent.relative_to(SNAPSHOT).as_posix() + "/")

    # 5. обновляем СВЕРКА_ПУБЛИКАЦИИ.json, сохраняя историю
    pub = json.loads(PUBLICATION.read_text(encoding="utf-8"))
    pub["checked_at_utc"] = "2026-09-27T19:30:00+00:00"
    pub["archive_base_commit"] = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ARCHIVE, capture_output=True, text=True,
        check=True).stdout.strip()
    pub["source_repository"] = "https://github.com/ooppanki2021-hash/zapahstarosti"
    pub["source_commit"] = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=SITE_REPO, capture_output=True, text=True,
        check=True).stdout.strip()
    pub["destination"] = "03-сайт/сайт_текущий"
    pub["note"] = ("Актуализация 27.09.2026: снимок приведён к состоянию сайта после "
                   "завершения иллюстраций (69 картинок). Прежние записи сохранены.")
    pub["source_files"] = source_files
    pub["http_checks"] = http_checks
    pub["content_pages"] = len(pages)
    pub["indexing_allowed"] = len(main_urls)
    pub["noindex_content"] = noindex
    pub["sitemap_urls"] = len(main_urls)
    pub["sitemap_full_urls"] = len(full)
    pub["service_pages_noindex"] = [
        SITE + "/app/", SITE + "/politika-konfidencialnosti/", SITE + "/soglasie-na-obrabotku/"]
    published = SNAPSHOT / "app/index.html"
    pub["tracker_versions"]["published"] = {
        "path": "03-сайт/сайт_текущий/app/index.html",
        "bytes": published.stat().st_size, "sha256": digest(published)}
    newer = ARCHIVE / "05_приложение/app/index.html"
    record = dict(pub["tracker_versions"].get("newer_unpublished", {}))
    record.update({"path": "05_приложение/app/index.html",
                   "bytes": newer.stat().st_size, "sha256": digest(newer),
                   "steps": 20, "actions": 153, "untouched": True})
    pub["tracker_versions"]["newer_unpublished"] = record
    pub["pwa_brand_rename_2026_09_26"] = {
        "what": ("Новая (неопубликованная) версия трекера: ДУБРАВА 40+ → ДУБИНА 40+ "
                 "в title, подзаголовке, подсказке и тексте этапа про регистрацию имени. "
                 "Структура не менялась: 20 этапов, 153 поддействия."),
        "commit": "394ea85"}
    pub["illustrations_2026_09_27"] = {
        "what": ("Снимок приведён к сайту после полного цикла иллюстраций: 69 картинок в стиле "
                 "акварель/тушь на бумаге, включая последние страницы /kviz/ и /faq/"),
        "source_commit_range": "b14e44d..255b46b",
        "webp_added": len([f for f in files if f.endswith(".webp")]),
        "pages_with_figures": 25,
        "checked_live": True,
        "sitemap_lastmod": "2026-09-27 (обновлены все 25 URL)",
        "yandex_webmaster": ("27.09.2026 все 25 URL отправлены на переобход; суточная квота 150, "
                             "остаток 125; критических проблем диагностики нет")}
    PUBLICATION.write_text(json.dumps(pub, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"СВЕРКА обновлена: source_files={len(source_files)}, http_checks={len(http_checks)}, "
          f"content_pages={pub['content_pages']}, noindex={pub['noindex_content']}")


if __name__ == "__main__":
    main()
