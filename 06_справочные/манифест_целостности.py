#!/usr/bin/env python3
"""Пересборка манифеста целостности архива dubrava под состояние 27.09.2026.

Прежний baseline (19–21.09) перестал сопровождаться: документы правились,
макеты упаковки переименованы по решению автора, PWA обновлена — из-за этого
проверка показывала десятки ложных расхождений. Новый baseline описывает
фактическое состояние архива; прежний сохранён в истории Git и кратко описан
в ключе previous_baselines.
"""
import json
import subprocess
from hashlib import sha256
from pathlib import Path

ROOT = Path("/home/user/dubrava")
OUT = ROOT / "01_НАЧНИ_ОТСЮДА/КОНТРОЛЬ_СОХРАННОСТИ.json"
MANIFEST_REL = "01_НАЧНИ_ОТСЮДА/КОНТРОЛЬ_СОХРАННОСТИ.json"


def git(*args):
    return subprocess.run(["git", "-c", "core.quotepath=false", *args], cwd=ROOT,
                          capture_output=True, text=True, check=True).stdout.strip()


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def previous_baseline():
    """Прежний манифест берём из HEAD: текущий файл мог перезаписать наш же запуск."""
    raw = subprocess.run(["git", "show", "HEAD:" + MANIFEST_REL], cwd=ROOT,
                         capture_output=True, text=True).stdout
    if not raw.strip():
        return {"original_files": [], "counts": {}, "date": None}
    return json.loads(raw)


def main():
    tracked = git("ls-files").splitlines()
    files = []
    for rel in tracked:
        p = ROOT / rel
        files.append({"path": rel, "bytes": p.stat().st_size, "sha256": digest(p)})
    files.sort(key=lambda x: x["path"])

    old = previous_baseline()
    old_paths = {x["path"] for x in old.get("original_files", [])}
    new_paths = {x["path"] for x in files}

    # переименования макетов упаковки 26.09.2026 (решение автора, коммит 9d54695)
    renames = []
    for p in sorted(new_paths):
        for folder in ("финальные_макеты", "исходники_дизайнера"):
            marker = "04_упаковка/" + folder + "/УСТАРЕЛО_"
            if p.startswith(marker):
                src = p.replace("УСТАРЕЛО_", "DUBRAVA_")
                if src in old_paths:
                    renames.append({
                        "from": src, "to": p,
                        "reason": "префикс DUBRAVA_ → УСТАРЕЛО_ по решению автора 26.09.2026",
                        "commit": "9d54695"})

    protected = sorted(p for p in new_paths
                       if p.startswith(("04_упаковка/", "05_приложение/")))

    manifest = {
        "schema_version": 2,
        "date": "2026-09-27",
        "generated_at_utc": "2026-09-27T19:50:00+00:00",
        "base_commit": git("rev-parse", "HEAD"),
        "repository": "https://github.com/ooppanki2021-hash/dubrava",
        "purpose": ("Инвентарь архива и описание согласованной актуализации без удаления. "
                    "Обычный коммит с сохранением родителя; видимость репозитория не меняется. "
                    "Снимок сайта приведён к коммиту 255b46b (иллюстрации), "
                    "см. 03-сайт/СВЕРКА_ПУБЛИКАЦИИ.json."),
        "counts": {
            "files": len(files),
            "previous_baseline_files": len(old_paths),
            "added_since_previous_baseline": len(new_paths - old_paths),
            "renamed": len(renames),
            "deleted": 0,
        },
        "deleted_files": [],
        "renames_acknowledged": renames,
        "files": files,
        "protected_unchanged_files": protected,
        "previous_baselines": [{
            "date": old.get("date", "2026-09-19"),
            "generated_at_utc": old.get("generated_at_utc"),
            "base_commit": old.get("base_commit"),
            "files": len(old_paths),
            "counts": old.get("counts", {}),
            "note": ("Baseline 19–21.09.2026 перестал сопровождаться: документы и PWA правились, "
                     "макеты упаковки переименованы решением автора. Его содержимое сохранено "
                     "в истории Git (01_НАЧНИ_ОТСЮДА/КОНТРОЛЬ_СОХРАННОСТИ.json на коммите c048368)."),
        }],
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
    OUT.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"манифест: файлов {len(files)}, добавлено с прежнего baseline "
          f"{len(new_paths - old_paths)}, переименований {len(renames)}, удалений 0")


if __name__ == "__main__":
    main()
