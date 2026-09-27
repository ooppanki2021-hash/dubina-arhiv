#!/usr/bin/env python3
"""Актуализация снимка сайта в архиве dubrava.

Что делает:
1. Берёт список файлов из репозитория сайта (только чтение).
2. Сверяет каждый файл с живым сайтом: HTTP-статус и SHA-256. Живой сайт — только чтение.
3. Если сверка чистая, копирует файлы в 03-сайт/сайт_текущий/ (ничего не удаляет,
   локальные технические MD снимка сохраняются).
4. Перезаписывает служебные поля 03-сайт/СВЕРКА_ПУБЛИКАЦИИ.json, сохраняя все прежние
   ключи и исторические записи (illustrations_*, pwa_brand_*, site_fix_*, task* и др.).
5. По желанию дописывает запись о задаче: --record ИМЯ --note "текст".

Порядок важен: сначала сверка с живым сайтом, и только при успехе — запись в архив.
Если GitHub Pages ещё не собрал только что отправленные правки, скрипт остановится
и ничего не испортит.

Запуск:
    python3 актуализация_снимка.py                       # сайт в /tmp/site
    python3 актуализация_снимка.py --site-repo /tmp/site
    python3 актуализация_снимка.py --record task41_2026_09_29 --note "что сделано"

Папку сайта задают тремя способами (по приоритету): --site-repo, переменная
окружения SITE_REPO, значение по умолчанию /tmp/site. Рабочую копию сайта в workspace
держать нельзя — правило 27.09.2026 в 01_НАЧНИ_ОТСЮДА/ПРОЧТИ_ПЕРВЫМ.md.
"""
import argparse
import json
import os
import re
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

try:                                    # даты записей ведём по времени автора
    from zoneinfo import ZoneInfo
    LOCAL = ZoneInfo("Europe/Moscow")
except Exception:                       # нет базы часовых поясов — берём UTC
    LOCAL = timezone.utc

ARCHIVE = Path(__file__).resolve().parent.parent
SNAPSHOT = ARCHIVE / "03-сайт/сайт_текущий"
PUBLICATION = ARCHIVE / "03-сайт/СВЕРКА_ПУБЛИКАЦИИ.json"
SITE = "https://zapahstarosti.ru"
DEFAULT_SITE_REPO = Path(os.environ.get("SITE_REPO", "/tmp/site"))

# локальные документы снимка, которых нет в репозитории сайта
LOCAL_DOCS = {"КОНСТРУКТОР_как_устроен.md", "ОПИСЬ.md", "ТЕХРЕГЛАМЕНТ_СТРАНИЦЫ.md"}
# служебные страницы: не входят в содержание, но закрыты от индексации
SERVICE = {"app", "politika-konfidencialnosti", "soglasie-na-obrabotku"}


def git(*args, cwd=ARCHIVE):
    return subprocess.run(["git", "-c", "core.quotepath=false", *args], cwd=cwd,
                          capture_output=True, text=True, check=True).stdout.strip()


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def repo_files(site_repo):
    out = subprocess.run(["git", "-c", "core.quotepath=false", "ls-files"], cwd=site_repo,
                         capture_output=True, text=True, check=True).stdout.splitlines()
    return sorted(f for f in out if f)


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
        return "ошибка: " + str(e), url, b""


def tracker_stats(path):
    """Число этапов и поддействий трекера прямо из разметки, без ручных констант."""
    text = path.read_text(encoding="utf-8")
    steps = len(re.findall(r"\{n:'", text))
    actions = len(re.findall(r"\{\s*t:'[^']*'\s*,\s*done:(?:true|false)\s*\}", text))
    return steps, actions


def locs(name):
    return [n.text for n in ET.parse(SNAPSHOT / name).getroot().iter()
            if n.tag.rsplit("}", 1)[-1] == "loc"]


def main():
    ap = argparse.ArgumentParser(description="Актуализация снимка сайта в архиве dubrava")
    ap.add_argument("--site-repo", type=Path, default=DEFAULT_SITE_REPO,
                    help=f"репозиторий сайта (по умолчанию {DEFAULT_SITE_REPO})")
    ap.add_argument("--record", help="имя записи о задаче, например task41_2026_09_29")
    ap.add_argument("--note", help="что сделано — попадёт в запись о задаче и в note")
    ap.add_argument("--no-manifest", action="store_true",
                    help="не пересобирать манифест целостности после сверки")
    args = ap.parse_args()

    site_repo = args.site_repo
    if not (site_repo / ".git").is_dir():
        sys.exit(f"Не найден репозиторий сайта: {site_repo}\n"
                 f"Клонируйте его во временную папку вне workspace — правило 27.09.2026.")

    files = repo_files(site_repo)
    print(f"файлов в репозитории сайта: {len(files)} ({site_repo})")

    # --- 1. сверка с живым сайтом ДО любой записи в архив -------------------
    def check(rel):
        status, final, body = fetch(url_for(rel))
        src = site_repo / rel
        same = bool(body) and src.is_file() and sha256(body).hexdigest() == digest(src)
        return {"path": rel, "url": url_for(rel), "final_url": final, "status": status,
                "bytes": len(body), "sha256": sha256(body).hexdigest() if body else "",
                "matches_source": same}

    targets = [rel for rel in files if rel != "CNAME"]  # CNAME не публикуется Pages
    with ThreadPoolExecutor(max_workers=8) as pool:
        http_checks = list(pool.map(check, targets))
    bad = [x for x in http_checks if x["status"] != 200 or not x["matches_source"]]
    print(f"сверка с живым сайтом: {len(http_checks)} адресов, расхождений: {len(bad)}")
    for x in bad[:20]:
        print("  !!", x["path"], "—", x["status"], "| совпадает:", x["matches_source"])
    if bad:
        sys.exit("Сверка с живым сайтом не пройдена — архив не тронут.\n"
                 "Если правки только что отправлены, подождите ~2 минуты (сборка Pages) "
                 "и запустите снова.")

    # --- 2. копируем публикацию в снимок, ничего не удаляя ------------------
    copied, updated = 0, 0
    for rel in files:
        src, dst = site_repo / rel, SNAPSHOT / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.exists():
            copied += 1
        elif dst.read_bytes() != src.read_bytes():
            updated += 1
        dst.write_bytes(src.read_bytes())
    print(f"снимок: новых {copied}, обновлено {updated}")
    for name in LOCAL_DOCS:
        assert (SNAPSHOT / name).is_file(), "потерян локальный документ снимка: " + name

    source_files = [{"path": rel, "bytes": (SNAPSHOT / rel).stat().st_size,
                     "sha256": digest(SNAPSHOT / rel)} for rel in files]

    # --- 3. содержание карт и страниц ---------------------------------------
    full, main_urls = locs("sitemap-full.xml"), locs("sitemap.xml")
    pages = [p for p in sorted(SNAPSHOT.glob("*/index.html"))
             if p.parent.name not in SERVICE] + [SNAPSHOT / "index.html"]
    noindex = [SITE + "/" + p.parent.relative_to(SNAPSHOT).as_posix() + "/"
               for p in pages if "noindex" in p.read_text(encoding="utf-8").lower()]

    # --- 4. обновляем СВЕРКА, сохраняя историю ------------------------------
    pub = json.loads(PUBLICATION.read_text(encoding="utf-8"))
    old_commit = pub.get("source_commit", "")
    new_commit = git("rev-parse", "HEAD", cwd=site_repo)

    pub["checked_at_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    pub["archive_base_commit"] = git("rev-parse", "HEAD")
    pub["source_commit"] = new_commit
    pub["source_files"] = source_files
    pub["http_checks"] = http_checks
    pub["content_pages"] = len(pages)
    pub["indexing_allowed"] = len(main_urls)
    pub["noindex_content"] = noindex
    pub["sitemap_urls"] = len(main_urls)
    pub["sitemap_full_urls"] = len(full)
    pub["service_pages_noindex"] = [SITE + "/" + name + "/" for name in sorted(SERVICE)]
    pub["tracker_versions"]["published"] = {
        "path": "03-сайт/сайт_текущий/app/index.html",
        "bytes": (SNAPSHOT / "app/index.html").stat().st_size,
        "sha256": digest(SNAPSHOT / "app/index.html")}
    newer = ARCHIVE / "05_приложение/app/index.html"
    steps, actions = tracker_stats(newer)
    pub["tracker_versions"]["newer_unpublished"] = {
        "path": "05_приложение/app/index.html",
        "bytes": newer.stat().st_size, "sha256": digest(newer),
        "steps": steps, "actions": actions, "untouched": True}

    if old_commit and old_commit != new_commit:
        changed = git("diff", "--name-only", old_commit, new_commit, cwd=site_repo).splitlines()
        pub["changed_site_files"] = sorted(changed)
    else:
        # коммит не менялся: оставляем прежнюю запись, а не затираем её пустым списком
        changed = pub.get("changed_site_files", [])

    stamp = datetime.now(timezone.utc).astimezone(LOCAL).strftime("%Y-%m-%d")
    if args.note:
        pub["note"] = args.note
    elif old_commit != new_commit:
        pub["note"] = (f"Актуализация {stamp}: снимок приведён к коммиту {new_commit[:7]}. "
                       f"Изменено файлов: {len(changed)}. Прежние записи сохранены.")

    if args.record:
        pub[args.record] = {
            "what": args.note or "Актуализация снимка без пояснения.",
            "date": stamp,
            "source_commit_range": (f"{old_commit[:7]}..{new_commit[:7]}"
                                    if old_commit and old_commit != new_commit
                                    else new_commit[:7] + " (без изменений с прошлой сверки)"),
            "changed_site_files": sorted(changed),
            "http_verified": (f"{len(http_checks)} адресов, статус 200 и SHA-256 совпадают "
                              f"(CNAME не публикуется GitHub Pages)")}

    PUBLICATION.write_text(json.dumps(pub, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"СВЕРКА обновлена: source_files={len(source_files)}, http_checks={len(http_checks)}, "
          f"content_pages={pub['content_pages']}, noindex={pub['noindex_content']}, "
          f"изменено с прошлой сверки={len(changed)}")
    if args.record:
        print(f"добавлена запись: {args.record}")

    # --- 5. манифест целостности: СВЕРКА только что изменилась -----------------
    if not args.no_manifest:
        cmd = [sys.executable, str(Path(__file__).with_name("манифест_целостности.py"))]
        if args.note:
            cmd += ["--note", args.note]
        subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
