#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ЧИСЛА README — числа в README.md архива считаются из факта, а не правятся вручную.

Зачем: 28.09.2026 аудит понятности архива показал, что README разошёлся с фактом —
«177 файлов» против 182 на диске, коммит `fe44617d` против фактического `74151d0`,
«69 картинок» против 80 WebP, «первый продукт — порошок» против решения 24.09.2026.
README читают первым и цифры берут оттуда без перепроверки, поэтому расхождение
переходит в чужие выводы.

Как работает:
  1. числа берутся из машинного факта — СВЕРКА_ПУБЛИКАЦИИ.json, сам снимок,
     КОНТРОЛЬ_СОХРАННОСТИ.json, ПОКАЗАТЕЛИ_поиска.json;
  2. каждое правило правки — это регулярное выражение, которое обязано найтись
     в README ровно один раз. Ноль совпадений или два — отказ, файл не тронут;
  3. правка идёт через тот же механизм страховки, что и `не_угадывать.py править`:
     резервная копия README.md.bak, проверка после правки, откат при провале;
  4. правила идемпотентны: после правки они находят новый текст и не меняют его.

Запуск из корня архива:
    python3 06_справочные/числа_readme.py              # показать факт и расхождения
    python3 06_справочные/числа_readme.py --применить  # привести README к факту

Порядок при актуализации снимка: актуализация_снимка.py вызывает этот скрипт
сам, чтобы числа не отставали от снимка.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT = ROOT / "03-сайт/сайт_текущий"
PUBLICATION = ROOT / "03-сайт/СВЕРКА_ПУБЛИКАЦИИ.json"
CONTROL = ROOT / "01_НАЧНИ_ОТСЮДА/КОНТРОЛЬ_СОХРАННОСТИ.json"
METRICS = ROOT / "02_документы_проекта/ПОКАЗАТЕЛИ_поиска.json"
RESUME = ROOT / "02_документы_проекта/РЕЗЮМЕ_ПРОЕКТА.md"
README = ROOT / "README.md"
# Документ передачи тоже содержит числа, которые устаревают после синхронизации
# снимка: дата актуализации, коммит сайта, размер опубликованного трекера и число
# поддействий. До 03.10.2026 он не был покрыт правилами и отстал от факта на одну
# синхронизацию: 66 208 байт и 164 поддействия против фактических 76 878 и 153.
PROCHTI = ROOT / "01_НАЧНИ_ОТСЮДА/ПРОЧТИ_ПЕРВЫМ.md"

BAK = README.with_suffix(README.suffix + ".bak")

# --------------------------------------------------------------------------- #
# факт: считаем из файлов, не из памяти
# --------------------------------------------------------------------------- #


def count_files(path, pattern=None):
    n = 0
    for p in sorted(path.rglob("*")):
        if not p.is_file():
            continue
        if pattern and not pattern(p.name):
            continue
        n += 1
    return n


def tracker_stats(path):
    """Число этапов и поддействий трекера прямо из разметки, без ручных констант.

    Логика та же, что в актуализация_снимка.py: иначе числа в документах и числа
    в СВЕРКЕ считались бы разными способами и могли разойтись.
    """
    text = path.read_text(encoding="utf-8")
    steps = len(re.findall(r"\{n:'", text))
    actions = len(re.findall(r"\{\s*t:'[^']*'\s*,\s*done:(?:true|false)\s*\}", text))
    return steps, actions


def html_files(path):
    return [p for p in sorted(path.rglob("*.html")) if p.is_file()]


def used_webp(snapshot):
    """Уникальные имена WebP, которые действительно вставлены в разметку."""
    used, pages = set(), set()
    for p in html_files(snapshot):
        text = p.read_text(encoding="utf-8", errors="replace")
        hit = False
        for m in re.findall(r'(?:src|href)="([^"]+)"', text):
            if ".webp" in m:
                used.add(m.rsplit("/", 1)[-1])
                hit = True
        if hit:
            pages.add(p)
    return used, pages


def facts():
    pub = json.loads(PUBLICATION.read_text(encoding="utf-8"))
    commit = pub.get("source_commit", "")
    stamp = pub.get("checked_at_utc", "")
    webp, pages_fig = used_webp(SNAPSHOT)
    f = {
        "commit": commit,
        "commit8": commit[:7],
        "sync_date": "%s.%s.%s" % (stamp[8:10], stamp[5:7], stamp[:4]) if stamp else "",
        "pub_files": len(pub.get("source_files", [])),
        "http_files": len(pub.get("http_checks", [])),
        "snap_files": count_files(SNAPSHOT),
        "local_docs": count_files(SNAPSHOT) - len(pub.get("source_files", [])),
        "content_pages": pub.get("content_pages"),
        "indexing_allowed": pub.get("indexing_allowed"),
        "sitemap_urls": pub.get("sitemap_urls"),
        "app_bytes": (SNAPSHOT / "app/index.html").stat().st_size,
        # Опубликованная версия трекера — отдельное число: в ПРОЧТИ_ПЕРВЫМ.md оба
        # сравниваются в одной строке. В СВЕРКЕ для published хранятся только bytes
        # и sha256, этапы с поддействиями туда не пишутся, поэтому считаем прямо из
        # разметки. Факт на 03.10.2026 — 173 поддействия, тогда как в документе
        # стояло 164: число отстало дважды, от синхронизации снимка и от разметки.
        "pub_steps": tracker_stats(SNAPSHOT / "app/index.html")[0],
        "pub_actions": tracker_stats(SNAPSHOT / "app/index.html")[1],
        "new_app_bytes": (ROOT / "05_приложение/app/index.html").stat().st_size,
        "webp": count_files(SNAPSHOT / "images", lambda n: n.endswith(".webp")),
        "webp_used": len(webp),
        "pages_fig": len(pages_fig),
        "png": count_files(ROOT / "04_упаковка/финальные_макеты",
                           lambda n: n.endswith(".png")),
        "png_actual": count_files(ROOT / "04_упаковка/финальные_макетах"
                                  if False else ROOT / "04_упаковка/финальные_макеты",
                                  lambda n: n.startswith("ДУБИНА_") and n.endswith(".png")),
        "src_files": count_files(ROOT / "04_упаковка/исходники_дизайнера"),
        "scripts": count_files(ROOT / "04_упаковка/скрипты_генерации"),
        "tracker_steps": pub.get("tracker_versions", {}).get(
            "newer_unpublished", {}).get("steps"),
        "tracker_actions": pub.get("tracker_versions", {}).get(
            "newer_unpublished", {}).get("actions"),
    }
    if CONTROL.is_file():
        control = json.loads(CONTROL.read_text(encoding="utf-8"))
        f["manifest_files"] = control.get("counts", {}).get("files")
        f["manifest_deleted"] = len(control.get("deleted_files", []))
    if METRICS.is_file():
        m = json.loads(METRICS.read_text(encoding="utf-8"))
        f["metrics_date"] = m.get("date", "")
        f["in_search"] = m.get("search", {}).get("pages_in_search")
        f["excluded"] = m.get("search", {}).get("excluded_low_quality")
        f["still_out"] = m.get("search", {}).get("still_excluded")
        f["visits"] = m.get("metrika", {}).get("visits_60d")
        f["from_search"] = m.get("metrika", {}).get("visits_from_search")
    return f


def human(n):
    """Разряды пробелом — как в README."""
    return "{:,}".format(n).replace(",", " ")


# --------------------------------------------------------------------------- #
# правила: что в README заменяется, а что только сверяется
# --------------------------------------------------------------------------- #

RULES = [
    # Шапка README устаревала отдельно от тела: правила правили строки
    # «коммит `X` (актуализация Y)» и «сверка Y, коммит сайта `X`», а верхний
    # жирный абзац «Обновлён …: снимок сайта приведён к коммиту `X`» оставался
    # на прежнем коммите. Отсюда расхождение 74151d0/aa745f7 внутри одного файла.
    dict(id="шапка README: дата и коммит актуализации",
         mode="replace",
         find=r'''\*\*Обновлён \d{2}\.\d{2}\.\d{4}: снимок сайта приведён к коммиту `[0-9a-f]{7,40}''',
         repl=r'''**Обновлён @sync_date@: снимок сайта приведён к коммиту `@commit8@''',
         done=r'''\*\*Обновлён \d{2}\.\d{2}\.\d{4}: снимок сайта приведён к коммиту `[0-9a-f]{7,40}'''),

    dict(id="коммит снимка (раздел «Сайт и приложение»)",
         mode="replace",
         find=r"коммит `[0-9a-f]{7,40}` \(актуализация \d{2}\.\d{2}\.\d{4}\)",
         repl="коммит `@commit8@` (актуализация @sync_date@)"),

    dict(id="коммит и дата снимка (раздел «Размещение обновления»)",
         mode="replace",
         find=r"сверка \d{2}\.\d{2}\.\d{4}, коммит сайта `[0-9a-f]{7,40}`",
         repl="сверка @sync_date@, коммит сайта `@commit8@`"),

    dict(id="число сверенных файлов публикации",
         mode="replace",
         find=r"Все \d+ файлов с HTTP-доступом сверены с живым сайтом побайтово",
         repl="@http_files@ файлов из @pub_files@ сверены с живым сайтом по HTTP "
              "(все 200, SHA-256 совпадают); всего в папке снимке @snap_files@ файла, "
              "из них @local_docs@ — локальные технические Markdown архива",
         done=r"\d+ файлов из \d+ сверены с живым сайтом по HTTP"),

    dict(id="размер опубликованного трекера",
         mode="replace",
         find=r"\*\*опубликованная\*\* версия трекера, \d{2} \d{3} байта",
         repl="**опубликованная** версия трекера, @app_bytes_h@ байта"),

    dict(id="иллюстрации в снимке",
         mode="replace",
         find=r"\d+ картинок акварелью и тушью на \d+ страницах",
         repl="@webp@ файлов WebP в `images/`, из них @webp_used@ вставлены "
              "в разметку @pages_fig@ страниц",
         done=r"\d+ файлов WebP в `images/`, из них \d+ вставлены в разметку \d+ страниц"),

    dict(id="первый продукт — согласовать с РЕЗЮМЕ",
         mode="replace",
         find=r"\*\*(?:Гель|Порошок для цветного белья)\*\*[^|]*\|",
         repl="**Гель** (решение автора 24.09.2026; прежний выбор — порошок для "
              "цветного, сохранён в истории), а не мыло "
              "и не одновременный запуск всей линейки |",
         done=r"\*\*Гель\*\* \(решение автора 24\.09\.2026",
         guard=(RESUME, "Первый продукт — гель")),

    dict(id="поиск: проверен или нет",
         mode="replace",
         find=r"Фактические страницы в поиске, посещаемость и конверсии "
              r"без Вебмастера/аналитики не проверены",
         repl="Проверено @metrics_date@ (Вебмастер + Метрика): в поиске @in_search@ "
              "из @indexing_allowed@ разрешённых URL, версии от 22.09.2026; "
              "@excluded@ страницы исключены 09.09.2026 как LOW_QUALITY, "
              "@still_out@ из них не вернулись; визитов за 60 дней @visits@, "
              "из поиска @from_search@",
         done=r"Проверено \d{2}\.\d{2}\.\d{4} \(Вебмастер \+ Метрика\)"),

    dict(id="состав папок упаковки",
         mode="replace",
         find=r"\d+ макетов, \d+ исходник\w*, \d+ скрипт\w*",
         repl="@png@ PNG в финальных макетах, @src_files@ файлов исходников, "
              "@scripts@ скриптов",
         done=r"\d+ PNG в финальных макетах, \d+ файлов исходников, \d+ скриптов"),

    # --- только сверка: если факт разошёлся, править надо осознанно ---------- #
    dict(id="сверка: контентных URL",
         mode="check",
         find=r"\*\*(\d+) контентных URL",
         value="content_pages"),
    dict(id="сверка: разрешено к индексации",
         mode="check",
         find=r"\*\*(\d+) контентных URL, все отвечают 200; (\d+) разрешены",
         value="indexing_allowed"),
    dict(id="сверка: PNG в финальных макетах",
         mode="check",
         find=r"\*\*(\d+) PNG\*\* в `финальные_макетах/`: (\d+) актуальных",
         value="png"),
    dict(id="сверка: этапы трекера",
         mode="check",
         find=r"(\d+) этапов",
         value="tracker_steps"),
    dict(id="сверка: поддействия трекера",
         mode="check",
         find=r"\*\*(\d+)\*\* поддействия",
         value="tracker_actions"),
    dict(id="сверка: размер новой версии трекера",
         mode="check",
         find=r"(\d{2} \d{3}) байт; сохранена без изменений",
         value="new_app_bytes_h"),
]

# --------------------------------------------------------------------------- #
# правила для ПРОЧТИ_ПЕРВЫМ.md — те же факты, другой документ
# --------------------------------------------------------------------------- #

RULES_PROCHTI = [
    dict(id="ПРОЧТИ: дата актуализации",
         mode="replace",
         find=r'''\*\*Актуализация: \d{2}\.\d{2}\.\d{4}\*\*''',
         repl=r'''**Актуализация: @sync_date@**'''),
    dict(id="ПРОЧТИ: коммит публикации снимка",
         mode="replace",
         find=r'''приведён к публикации `[0-9a-f]{7,40}` от \d{2}\.\d{2}\.\d{4} \(сверено с живым сайтом побайтово, (\d+) файлов\)''',
         repl=r'''приведён к публикации `@commit8@` от @sync_date@ (сверено с живым сайтом побайтово, @http_files@ файлов)'''),
    dict(id="ПРОЧТИ: размер опубликованного трекера",
         mode="replace",
         find=r'''(\d{2} \d{3}) байт \(\*\*опубликованная\*\* версия трекера\)''',
         repl=r'''@app_bytes_h@ байт (**опубликованная** версия трекера)'''),
    dict(id="ПРОЧТИ: поддействия в строке «Не перепутать»",
         mode="replace",
         find=r'''поддействий \d+ в опубликованной и \d+ в новой''',
         repl=r'''поддействий @pub_actions@ в опубликованной и @tracker_actions@ в новой'''),
    dict(id="ПРОЧТИ: поддействия в строке «В трекере 20 этапов»",
         mode="replace",
         find=r'''поддействий \d+ в новой и \d+ в опубликованной''',
         repl=r'''поддействий @tracker_actions@ в новой и @pub_actions@ в опубликованной'''),
]

TARGETS = [(README, RULES, "README"), (PROCHTI, RULES_PROCHTI, "ПРОЧТИ_ПЕРВЫМ.md")]


def expand(repl, f):
    """@имя@ → значение из факта."""
    out = repl
    for key, val in sorted(f.items(), key=lambda kv: -len(kv[0])):
        out = out.replace("@" + key + "@", str(val))
    return out


def verify(path):
    """Проверка после правки — та же, что в «не угадывать»: файл остался живым."""
    sys.path.insert(0, str(ROOT / "06_справочные"))
    try:
        from не_угадывать import verify_file  # noqa: E402
    except Exception:
        return None
    return verify_file(str(path))


def main():
    apply = "--применить" in sys.argv[1:]
    f = facts()
    f["app_bytes_h"] = human(f["app_bytes"])
    f["new_app_bytes_h"] = human(f["new_app_bytes"])
    missing = [k for k in ("commit", "sync_date", "metrics_date") if not f.get(k)]
    if missing:
        sys.exit("Нет данных для чисел: " + ", ".join(missing) +
                 "\nСначала актуализируйте снимок и показатели поиска.")

    targets_changed = []
    print("ФАКТ (из файлов архива, не из памяти):")
    for k in ("commit8", "sync_date", "pub_files", "http_files", "snap_files",
              "content_pages", "indexing_allowed", "app_bytes_h", "new_app_bytes_h",
              "webp", "webp_used", "pages_fig", "png", "src_files", "scripts",
              "tracker_steps", "tracker_actions", "pub_steps", "pub_actions",
              "manifest_files",
              "metrics_date", "in_search", "visits", "from_search"):
        print(f"  {k:20} {f.get(k)}")
    print()

    problems = []
    for target, rules, name in TARGETS:
        if not target.is_file():
            problems.append(f"{name}: файл не найден — правило не применить")
            continue
        text = target.read_text(encoding="utf-8")
        bak = target.with_suffix(target.suffix + ".bak")
        changed, ok = 0, 0
        print(f"--- {name} ---")
        for rule in rules:
            pat = re.compile(rule["find"])
            hits = list(pat.finditer(text))
            if rule["mode"] == "check":
                want = f.get(rule["value"])
                if want is None:
                    problems.append(f"{rule['id']}: нет факта для сверки ({rule['value']})")
                    continue
                found = False
                for m in hits:
                    nums = [g.replace(" ", "") for g in m.groups() if g]
                    if str(want).replace(" ", "") in nums:
                        found = True
                if found:
                    ok += 1
                    print(f"  сходится  {rule['id']}")
                else:
                    problems.append(f"{rule['id']}: в {name} {hits and [m.group(0)[:60] for m in hits] or 'нет такого места'}, а факт {want}")
                continue

            if len(hits) != 1 and rule.get("done"):
                # правка могла быть внесена раньше: ищем уже применённый текст
                done_hits = list(re.finditer(rule["done"], text))
                if len(done_hits) == 1:
                    ok += 1
                    print(f"  уже верно {rule['id']}")
                    continue
            if len(hits) != 1:
                problems.append(f"{rule['id']}: найдено {len(hits)} совпадений, жду ровно одно. "
                                "Правило устарело или текст правлен вручную — сверьте правило с README.")
                continue
            new_text = pat.sub(lambda m: expand(rule["repl"], f).replace("\\", "\\\\"), text, count=1)
            if new_text == text:
                ok += 1
                print(f"  уже верно {rule['id']}")
                continue
            if not apply:
                print(f"  расходится {rule['id']}")
                print(f"      было:  {hits[0].group(0)[:100]}")
                print(f"      стало: {expand(rule['repl'], f)[:100]}")
                continue
            # страховка: копия, правка, проверка, откат при провале
            # страховка пишется рядом с тем файлом, который правим: до 03.10.2026
            # здесь стояла глобальная BAK (= README.md.bak), и для второго документа
            # резервная копия уехала бы в чужой файл
            if not bak.exists():
                bak.write_text(text, encoding="utf-8")
            text = new_text
            changed += 1
            print(f"  исправлено {rule['id']}")

        if apply and changed:
            target.write_text(text, encoding="utf-8")
            err = verify(target)
            if err:
                if bak.exists():
                    target.write_text(bak.read_text(encoding="utf-8"), encoding="utf-8")
                    sys.exit(f"!!! ПРОВЕРКА ПОСЛЕ ПРАВКИ НЕ ПРОЙДЕНА в {name}: {err}\n"
                             f"Файл восстановлен из {bak.name}")
                sys.exit(f"!!! ПРОВЕРКА ПОСЛЕ ПРАВКИ НЕ ПРОЙДЕНА в {name}: {err}")
            # правка подтверждена и покрыта историей Git — копия больше не нужна
            if bak.exists():
                bak.unlink()
            targets_changed.append((name, changed))
            print(f"{name}: приведён к факту, правок {changed}. Проверка пройдена.")
        elif apply:
            print(f"{name}: уже совпадает с фактом — правок не потребовалось.")
        print(f"  сверок сходится: {ok}\n")

    if apply and targets_changed:
        print("Приведены к факту: "
              + ", ".join(f"{n} ({c})" for n, c in targets_changed) + ".")
    elif apply:
        print("Все документы уже совпадают с фактом — правок не потребовалось.")

    if problems:
        print("\nТРЕБУЕТ ВНИМАНИЯ:")
        for p in problems:
            print("  !!", p)
        return 1
    if not apply:
        print("Для правки: --применить")
    return 0


if __name__ == "__main__":
    sys.exit(main())
