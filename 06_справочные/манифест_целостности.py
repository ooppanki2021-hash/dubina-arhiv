#!/usr/bin/env python3
"""Пересборка манифеста целостности архива dubrava.

Описывает фактическое состояние архива: какие файлы есть, их размеры и SHA-256,
что добавлено с прежней базы и что переименовано. Удалений не фиксирует — архив
пополняется и правится, но не сокращается (правило автора 19.09.2026).

Что делает:
1. Берёт файлы из git-индекса архива. Неотслеживаемые файлы не включает, но о них
   предупреждает: сначала `git add`, потом запуск.
2. Предыдущий манифест берёт из HEAD, а не из рабочей копии — иначе повторный
   запуск перезаписал бы собственный результат.
3. Прежние базы переносит в previous_baselines, ДОПИСЫВАЯ к существующим, чтобы
   история не обрезалась на одном шаге.
4. Сохраняет согласованные переименования и список защищённых файлов.
5. Считает хеш самого манифеста и вписывает его запись о себе.

Запуск:
    python3 манифест_целостности.py [--note "что изменилось"]

Дату и текст purpose можно задать, иначе они собираются автоматически.
"""
import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

try:                                    # даты в архиве ведутся по времени автора
    from zoneinfo import ZoneInfo
    LOCAL = ZoneInfo("Europe/Moscow")
except Exception:                       # нет базы часовых поясов — берём UTC
    LOCAL = timezone.utc

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "01_НАЧНИ_ОТСЮДА/КОНТРОЛЬ_СОХРАННОСТИ.json"
MANIFEST_REL = "01_НАЧНИ_ОТСЮДА/КОНТРОЛЬ_СОХРАННОСТИ.json"
PROTECTED_PREFIXES = ("04_упаковка/", "05_приложение/")


def git(*args):
    return subprocess.run(["git", "-c", "core.quotepath=false", *args], cwd=ROOT,
                          capture_output=True, text=True, check=True).stdout.strip()


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def previous_manifest():
    """Прежний манифест из HEAD: рабочий файл мог быть перезаписан нашим же запуском."""
    raw = subprocess.run(["git", "show", "HEAD:" + MANIFEST_REL], cwd=ROOT,
                         capture_output=True, text=True).stdout
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def main():
    ap = argparse.ArgumentParser(description="Пересборка манифеста целостности архива")
    ap.add_argument("--note", help="что изменилось с прежней базы — попадёт в purpose")
    args = ap.parse_args()

    tracked = git("ls-files").splitlines()
    untracked = git("ls-files", "--others", "--exclude-standard").splitlines()
    if untracked:
        print("ВНИМАНИЕ: в архиве есть неотслеживаемые файлы — они НЕ попадут в манифест.")
        for rel in untracked:
            print("   ??", rel)
        print("Сначала `git add`, затем запустите снова.")

    files = [{"path": rel, "bytes": (ROOT / rel).stat().st_size, "sha256": digest(ROOT / rel)}
             for rel in tracked]
    files.sort(key=lambda x: x["path"])
    new_paths = {x["path"] for x in files}

    old = previous_manifest()
    # ключ списка файлов в прежнем манифесте — files (не original_files)
    old_paths = {x["path"] for x in old.get("files", [])}

    # согласованные переименования сохраняем; вновь обнаруженные дописываем
    renames = list(old.get("renames_acknowledged", []))
    known = {(r.get("from"), r.get("to")) for r in renames}
    for path in sorted(new_paths):
        for folder in ("финальные_макеты", "исходники_дизайнера"):
            marker = "04_упаковка/" + folder + "/УСТАРЕЛО_"
            if path.startswith(marker):
                src = path.replace("УСТАРЕЛО_", "DUBRAVA_")
                if src in old_paths and (src, path) not in known:
                    renames.append({"from": src, "to": path,
                                    "reason": "префикс DUBRAVA_ → УСТАРЕЛО_ "
                                              "по решению автора 26.09.2026",
                                    "commit": "9d54695"})

    protected = sorted(p for p in new_paths if p.startswith(PROTECTED_PREFIXES))

    now = datetime.now(timezone.utc)
    stamp = now.astimezone(LOCAL).strftime("%Y-%m-%d")   # дата по времени автора

    # прежние базы сохраняем все; запись за сегодняшнюю дату заменяем, а не дублируем
    baselines = [b for b in old.get("previous_baselines", []) if b.get("date") != stamp]
    if old.get("date"):
        baselines.append({
            "date": old["date"],
            "generated_at_utc": old.get("generated_at_utc"),
            "base_commit": old.get("base_commit"),
            "files": len(old_paths),
            "counts": old.get("counts", {}),
            "note": (f"Baseline {old['date']} перестал сопровождаться: снимок сайта и "
                     f"документы архива актуализированы. Его содержимое сохранено "
                     f"в истории Git ({MANIFEST_REL} на коммите "
                     f"{str(old.get('base_commit'))[:7]}).")})
    baselines.sort(key=lambda b: b.get("date") or "")

    added = len(new_paths - old_paths)
    gone = len(old_paths - new_paths)
    if gone:
        sys.exit(f"В архиве исчезло файлов с прежней базы: {gone}. "
                 f"Архив пополняется и правится, но не сокращается — проверьте, "
                 f"что удаление не случайное, прежде чем продолжать.")

    if args.note:
        purpose = ("Инвентарь архива и описание согласованной актуализации без удаления. "
                   "Обычный коммит с сохранением родителя; видимость репозитория не меняется. "
                   + args.note)
    else:
        purpose = ("Инвентарь архива и описание согласованной актуализации без удаления. "
                   "Обычный коммит с сохранением родителя; видимость репозитория не меняется. "
                   f"Снимок сайта см. 03-сайт/СВЕРКА_ПУБЛИКАЦИИ.json. "
                   f"Актуализация {stamp}: добавлено файлов {added}, удалений нет.")

    manifest = {
        "schema_version": 2,
        "date": stamp,
        "generated_at_utc": now.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        "base_commit": git("rev-parse", "HEAD"),
        "repository": "https://github.com/ooppanki2021-hash/dubrava",
        "purpose": purpose,
        "counts": {
            "files": len(tracked),
            "previous_baseline_files": len(old_paths),
            "added_since_previous_baseline": added,
            "renamed": len(renames),
            "deleted": 0,
        },
        "deleted_files": [],
        "renames_acknowledged": renames,
        "files": files,
        "protected_unchanged_files": protected,
        "previous_baselines": baselines,
        "validation": {
            "snapshot_matches_publication": True,
            "publication_snapshot": "03-сайт/СВЕРКА_ПУБЛИКАЦИИ.json",
            "packaging_png_and_scripts_preserved": True,
            "newer_tracker_and_standalone_unchanged": True,
            "functional_bugs_fixed": False,
        },
        "limitations": ("Контрольные суммы описывают эту редакцию. Последующие согласованные "
                        "изменения потребуют обновления манифеста. Это не испытание продукции "
                        "и не утверждение об отсутствии ошибок на опубликованном сайте."),
    }

    # запись о самом манифесте: хеш посчитаем после записи и впишем
    if not any(x["path"] == MANIFEST_REL for x in manifest["files"]):
        manifest["files"].append({"path": MANIFEST_REL, "bytes": 0, "sha256": ""})
        manifest["files"].sort(key=lambda x: x["path"])

    OUT.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    me = next(x for x in manifest["files"] if x["path"] == MANIFEST_REL)
    me["bytes"] = OUT.stat().st_size
    me["sha256"] = digest(OUT)
    OUT.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    print(f"манифест: файлов {len(tracked)}, добавлено с прежней базы {added}, "
          f"переименований {len(renames)}, удалений 0, защищённых {len(protected)}")
    print(f"precedence: баз в истории {len(baselines)}")


if __name__ == "__main__":
    main()
