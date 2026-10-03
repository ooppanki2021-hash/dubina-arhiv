#!/usr/bin/env python3
"""Один общий гейт сохранения вместо пяти отдельных шагов.

Зачем этот файл существует. Штатный порядок архива требует после любой правки
выполнить цепочку: числа_readme.py --применить -> git add -A ->
манифест_целостности.py -> проверить_архив.py -> git commit. Сама цепочка
занимает меньше секунды, но каждый шаг отдельным вызовом — это отдельный
обращение к инструменту со своей задержкой. Замер 03.10.2026: вычисления
0,57 с, а накладные расходы на пять отдельных вызовов — в десятки раз больше.
Этот скрипт делает всю цепочку одним вызовом и останавливается на первой ошибке.

Порядок шагов сохранён ровно тот, что предписан правилами архива. Ничего не
пропускается и не заменяется: вызываются те же самые скрипты, просто подряд.

Что делает:
0. Предпроверка. Репозиторий, git-идентичность (без неё коммит молча падает,
   поэтому при заказанном --коммит её отсутствие останавливает прогон; без
   --коммит это только предупреждение),
   мусор от инструментов: каталоги __pycache__ и резервные копии .bak. Файла
   .gitignore в архиве нет, поэтому git add -A подхватил бы и то и другое.
   .bak удаляются: их содержимое всегда есть в git, а не_угадывать.py не
   перезаписывает уже существующую копию, из-за чего протухший .bak иначе
   лежал бы вечно и мешал пересборке манифеста.
1. числа_readme.py --применить — приводит числа в документах к факту.
2. git add -A — чтобы манифест увидел новые файлы: он берёт их из индекса.
3. манифест_целостности.py — пересобирается ПОСЛЕДНИМ из содержательных шагов,
   и только если изменилось что-то кроме самого манифеста: он вшивает метку
   времени, поэтому холостая пересборка оставила бы ложный diff.
4. git add -A ещё раз — манифест сам изменился.
5. проверить_архив.py — итоговая самопроверка.
6. Коммит, если передан --коммит.

Пуш намеренно не входит: у архива не настроен remote с учётными данными, и
публикация — отдельное решение автора.

Запуск:
    python3 сохранить.py --справка                список флагов
    python3 сохранить.py                          только проверить и пересобрать
    python3 сохранить.py --note "что изменилось"  с пояснением для манифеста
    python3 сохранить.py --коммит "сообщение"     плюс коммит
    python3 сохранить.py --сухо                   ничего не менять, только отчёт

Код возврата 0 — всё сошлось. Не 0 — назван шаг, на котором остановились.
"""
import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "06_справочные"
MANIFEST_REL = "01_НАЧНИ_ОТСЮДА/КОНТРОЛЬ_СОХРАННОСТИ.json"


def git(*args, check=True, capture=True):
    """git с core.quotepath=false, иначе кириллица в путях возвращается \\320…"""
    return subprocess.run(["git", "-c", "core.quotepath=false", *args], cwd=ROOT,
                          capture_output=capture, text=True, check=check)


def run_step(title, cmd):
    """Шаг с замером времени. Возвращает (код, вывод) и печатает сводку."""
    t0 = time.time()
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    dt = time.time() - t0
    out = (p.stdout or "") + (p.stderr or "")
    ok = p.returncode == 0
    print(f"\n{'─' * 72}\n[{ '✓' if ok else '✗' }] {title}  ({dt:.2f} с)")
    for line in out.strip().splitlines():
        print(f"      {line}")
    return p.returncode, out, dt


def clean_junk(сухо, quiet=False):
    """Убирает мусор, который создают сами инструменты архива.

    Вызывается дважды: до шагов и после шага 1. Второй вызов обязателен —
    числа_readme.py импортирует общее.py, и Python создаёт __pycache__ заново
    уже после предпроверки; git add -A подхватил бы его. Так в архив однажды
    попал .pyc, и .gitignore теперь прикрывает это со своей стороны.

    Возвращает число убранных объектов.
    """
    pycache = [p for p in ROOT.rglob("__pycache__") if ".git" not in p.parts and p.is_dir()]
    baks = sorted(p for p in ROOT.rglob("*.bak") if ".git" not in p.parts)
    if not pycache and not baks:
        if not quiet:
            print("      мусора от инструментов нет")
        return 0

    print(f"      __pycache__: {len(pycache)}, .bak: {len(baks)}"
          + (" — убраны" if not сухо else " — были бы убраны"))
    for p in baks:
        print(f"        {p.relative_to(ROOT)}")
    if not сухо:
        for p in pycache:
            shutil.rmtree(p, ignore_errors=True)
        for p in baks:
            p.unlink(missing_ok=True)
    return len(pycache) + len(baks)


def preflight(сухо, need_identity):
    """Шаг 0. Возвращает список замечаний; падает, если продолжать нельзя."""
    print(f"{'─' * 72}\n[·] Предпроверка")
    problems = []

    if not (ROOT / ".git").exists():
        print("      ✗ это не git-репозиторий, продолжать нельзя")
        return False, []

    # Идентичность нужна только для коммита: git add и пересборка манифеста
    # обходятся без неё. Поэтому при запуске без --коммит это предупреждение,
    # а не остановка, иначе гейт блокировал бы холостую проверку.
    ident = git("config", "user.email", check=False).stdout.strip()
    if not ident:
        mark = "✗" if need_identity else "⚠"
        print(f"      {mark} не задана git-идентичность"
              + (" — коммит упадёт." if need_identity else " — для коммита понадобится."))
        print("        Исправляется так:")
        print('        git config user.email "вы@example.com"')
        print('        git config user.name  "Имя"')
        if need_identity:
            problems.append("нет git-идентичности, а заказан --коммит")
    else:
        print(f"      git-идентичность: {ident}")

    clean_junk(сухо, quiet=True)

    dirty = git("status", "--porcelain").stdout.strip()
    print(f"      незакоммиченных изменений: {len(dirty.splitlines()) if dirty else 0}")
    return not problems, problems


def main():
    ap = argparse.ArgumentParser(description="Один общий гейт сохранения архива.")
    ap.add_argument("--note", default="", help="пояснение для манифеста")
    ap.add_argument("--коммит", dest="commit", default="", help="сообщение коммита")
    ap.add_argument("--сухо", action="store_true", help="только отчёт, ничего не менять")
    ap.add_argument("--разрешить-удаление", dest="allow_delete", default="",
                    help="причина, по которой удаление допустимо; без неё удаления блокируются")
    ap.add_argument("--пропуск-чисел", action="store_true",
                    help="не запускать числа_readme.py (если правка его не касается)")
    # флаг --справка для единообразия с остальными скриптами архива
    ap.add_argument("--справка", action="help", help=argparse.SUPPRESS)
    args = ap.parse_args()

    t_all = time.time()
    print("=" * 72)
    print("СОХРАНЕНИЕ АРХИВА — общий гейт")
    print("=" * 72)

    ok, _ = preflight(args.сухо, need_identity=bool(args.commit))
    if not ok:
        print("\nОСТАНОВЛЕНО НА: предпроверка")
        return 2
    if args.сухо:
        print("\n--сухо: дальше ничего не выполняется.")
        return 0

    def step(title, cmd):
        code, _out, _dt = run_step(title, cmd)
        if code != 0:
            print(f"\nОСТАНОВЛЕНО НА: {title}")
            print("Порядок нарушать нельзя: следующий шаг опирается на результат этого.")
            sys.exit(code)

    if not args.пропуск_чисел:
        step("Шаг 1. Числа в документах приводятся к факту",
             [sys.executable, str(TOOLS / "числа_readme.py"), "--применить"])

    # Шаг 1 импортирует общее.py, и Python снова создаёт __pycache__. Убираем
    # повторно, ДО git add -A, иначе служебный байткод уедет в коммит.
    clean_junk(args.сухо, quiet=True)

    step("Шаг 2. git add -A — манифест берёт файлы из индекса",
         ["git", "-c", "core.quotepath=false", "add", "-A"])

    # Манифест вшивает generated_at_utc, поэтому его пересборка всегда меняет
    # файл и оставляет ложный diff, даже если по существу ничего не изменилось.
    # Пересобираем только когда изменилось что-то кроме самого манифеста:
    # иначе шаг лишний, а рабочая копия перестаёт быть чистой после проверки.
    staged = [x for x in git("diff", "--cached", "--name-only").stdout.splitlines() if x]
    changed = [x for x in staged if x != MANIFEST_REL]
    if changed:
        man = [sys.executable, str(TOOLS / "манифест_целостности.py")]
        if args.note:
            man += ["--note", args.note]
        if args.allow_delete:
            # причина пробрасывается в манифест и записывается там, а не теряется
            man += ["--разрешить-исчезновение", args.allow_delete]
        step(f"Шаг 3. Манифест пересобирается последним (изменилось файлов: {len(changed)})", man)
        step("Шаг 4. git add -A — манифест сам изменился",
             ["git", "-c", "core.quotepath=false", "add", "-A"])
    else:
        print(f"\n{'─' * 72}\n[–] Шаг 3–4 пропущены: кроме самого манифеста ничего не изменилось.")
        print("      Пересборка оставила бы ложный diff из-за метки времени.")

    step("Шаг 5. Итоговая самопроверка",
         [sys.executable, str(TOOLS / "проверить_архив.py")])

    # --- сводка -----------------------------------------------------------
    print(f"\n{'=' * 72}\nСВОДКА")
    staged = git("diff", "--cached", "--name-status").stdout.strip().splitlines()
    adds = [x for x in staged if x.startswith("A")]
    mods = [x for x in staged if x.startswith("M")]
    dels = [x for x in staged if x.startswith("D")]
    rens = [x for x in staged if x.startswith("R")]
    print(f"  к коммиту подготовлено: новых {len(adds)}, изменённых {len(mods)}, "
          f"переименований {len(rens)}, удалений {len(dels)}")
    if dels:
        for d in dels:
            print(f"    {d}")
        if not args.allow_delete:
            print("  ⚠ УДАЛЕНИЯ. Правило архива — пополняется и правится, но не сокращается.")
            print("    Коммит не создан. Если удаление действительно намеренное,")
            print("    повторите с явной причиной:")
            print('    сохранить.py --разрешить-удаление "почему это можно удалить" ...')
            return 3
        print(f"  ⚠ удаления разрешены явно, причина: {args.allow_delete}")

    if args.commit:
        git("commit", "-q", "-m", args.commit)
        head = git("log", "-1", "--format=%h %s").stdout.strip()
        print(f"  коммит: {head}")
    else:
        print("  коммит не создавался (не передан --коммит)")

    print(f"\n  всего времени: {time.time() - t_all:.2f} с одним вызовом")
    print("  ГОТОВО. Все шаги прошли, порядок соблюден.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
