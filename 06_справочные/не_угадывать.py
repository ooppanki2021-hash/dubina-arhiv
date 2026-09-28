#!/usr/bin/env python3
"""Инструмент против ошибок «предположил вместо проверки».

Зачем: почти все промахи помощника имели одну природу — он шёл от памяти,
а не от фактического ответа. Отсюда четыре инструмента, которые заставляют
смотреть сначала, а писать код под реальную форму данных потом.

  probe     — сырой ответ API + разбор его формы. Перед любым выводом из API.
  shape     — разбор формы JSON (словарь или список? какие ключи?).
  clean     — чистка HTML от служебного мусора перед любым сравнением текстов.
  main      — только содержимое <main>, без меню и подвала.
  править   — правка файла со страховкой: якорь обязан быть единственным,
              после правки проверяется синтаксис, делается резервная копия.
  git-файлы — список файлов репозитория с отключённым quotepath и сверкой
              числа файлов с манифестом. Кириллица в путях иначе даёт
              ложную картину «файлы исчезли».
  история   — поиск в истории первого коммита с непустым содержимым файла.
              Нужно при сверке переименований: коммит удаления даёт пустой
              вывод и ложный вердикт «содержимое потеряно».
  вывод     — обязательный чек-лист перед тем, как что-то заявить.

Примеры:
  python3 не_угадывать.py probe "https://api-metrica.yandex.net/stat/v1/data?id=1&metrics=ym:s:visits"
  python3 не_угадывать.py probe --token-env YANDEX_TOKEN "https://api.webmaster.yandex.net/v4/user"
  python3 не_угадывать.py shape /tmp/metrika.json
  python3 не_угадывать.py clean страница.html --text
  python3 не_угадывать.py clean a.html b.html      # сравнить две страницы после чистки
  python3 не_угадывать.py править doc.md --старый "раз" --новый "два"
  python3 не_угадывать.py git-файлы --repo /путь/к/репо
  python3 не_угадывать.py история "04_упаковка/файл.png" --repo /путь/к/репо
  python3 не_угадывать.py вывод

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
from pathlib import Path

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
# править: правка файла со страховкой
# --------------------------------------------------------------------------- #

def verify_file(path):
    """Проверка после правки: то, что файл вообще остался рабочим."""
    import ast
    suffix = Path(path).suffix.lower()
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except Exception as e:
        return f"не читается: {e}"
    if not raw.strip():
        return "файл опустел"
    if suffix == ".py":
        try:
            ast.parse(raw)
        except SyntaxError as e:
            return f"SyntaxError после правки: {e}"
    elif suffix == ".json":
        try:
            json.loads(raw)
        except Exception as e:
            return f"не JSON после правки: {e}"
    elif suffix == ".html":
        # только HTML: в Markdown <main>, <header> и прочие теги встречаются
        # как обычный текст документации, и проверка дала бы ложную тревогу
        for tag in ("div", "section", "main", "table", "p", "span"):
            o = len(re.findall(rf"<{tag}\b", raw))
            c = len(re.findall(rf"</{tag}>", raw))
            if o != c:
                return f"непарный <{tag}>: открыто {o}, закрыто {c}"
    return None


def edit_cmd(path, old, new, old_file, new_file):
    p = Path(path)
    if not p.is_file():
        print(f"Нет файла: {path}")
        return 1
    if old_file:
        old = Path(old_file).read_text(encoding="utf-8")
    if new_file:
        new = Path(new_file).read_text(encoding="utf-8")
    if not old:
        print("Пустой якорь — такое «найти и заменить» затронет весь файл. Отказано.")
        return 1
    text = p.read_text(encoding="utf-8")
    n = text.count(old)
    print(f"Якорь встречается в файле: {n} раз(а)")
    if n == 0:
        print("ОТКАЗ: якоря нет в файле. Значит правка уйдёт в никуда или")
        print("вы взяли якорь по памяти, а не по реальному тексту файла.")
        return 1
    if n > 1:
        print("ОТКАЗ: якорь неоднозначный. Где именно:")
        for i, line in enumerate(text.splitlines(), 1):
            if old[:40] in line or old.splitlines()[0][:40] in line:
                print(f"   строка {i}: {line.strip()[:80]}")
        print("Сделайте якорь длиннее и уникальным.")
        return 1

    bak = p.with_suffix(p.suffix + ".bak")
    if not bak.exists():
        bak.write_text(text, encoding="utf-8")
        print(f"Резервная копия: {bak.name}")
    else:
        print(f"Резервная копия {bak.name} уже есть — не перезаписываю")

    before = len(text.splitlines())
    text = text.replace(old, new, 1)
    p.write_text(text, encoding="utf-8")
    after = len(text.splitlines())
    print(f"Правка внесена: строк {before} → {after}")

    err = verify_file(path)
    if err:
        print(f"!!! ПРОВЕРКА ПОСЛЕ ПРАВКИ НЕ ПРОЙДЕНА: {err}")
        print(f"Откат из {bak.name}:  cp '{bak}' '{p}'")
        return 1
    print("Проверка после правки пройдена (синтаксис/целость в порядке)")
    return 0


# --------------------------------------------------------------------------- #
# git-файлы: список без quotepath + сверка числа с манифестом
# --------------------------------------------------------------------------- #

def git_files_cmd(repo):
    import subprocess
    r = Path(repo)
    if not (r / ".git").is_dir():
        print(f"{repo} не похож на git-репозиторий (нет .git)")
        return 1
    out = subprocess.run(["git", "-C", str(r), "-c", "core.quotepath=false",
                          "ls-files"], capture_output=True, text=True)
    if out.returncode != 0:
        print("git ls-files упал:", out.stderr[:200])
        return 1
    files = [f for f in out.stdout.splitlines() if f.strip()]
    print(f"Файлов в индексе git: {len(files)}")
    quoted = [f for f in files if f.startswith('"')]
    if quoted:
        print(f"!!! {len(quoted)} путей пришли в кавычках — quotepath не сработал")
    else:
        print("Кавычек в путях нет — кириллица читается правильно")

    # сверка с манифестом целостности, если он есть
    man = None
    for cand in (r / "01_НАЧНИ_ОТСЮДА" / "КОНТРОЛЬ_СОХРАННОСТИ.json",):
        if cand.is_file():
            man = cand
            break
    if man:
        m = json.loads(man.read_text(encoding="utf-8"))
        mfiles = [f["path"] for f in m.get("files", [])]
        gset, mset = set(files), set(mfiles)
        print(f"\nМанифест: {len(mfiles)} файлов")
        only_git = gset - mset
        only_man = mset - gset
        if only_git:
            print(f"   в git, но не в манифесте ({len(only_git)}) — манифест устарел:")
            for f in sorted(only_git)[:10]:
                print(f"      {f}")
        if only_man:
            print(f"   в манифесте, но не в git ({len(only_man)}) — файлы удалены:")
            for f in sorted(only_man)[:10]:
                print(f"      {f}")
        if not only_git and not only_man:
            print("   git и манифест совпадают полностью")
        if m.get("counts", {}).get("deleted", 0) != len(only_man):
            print(f"   ! манифест заявляет удалений "
                  f"{m['counts'].get('deleted')}, а фактически {len(only_man)}")
    else:
        print("Манифест целостности рядом не найден — сверять не с чем")
    return 0


# --------------------------------------------------------------------------- #
# история: первый коммит с непустым содержимым
# --------------------------------------------------------------------------- #

def history_cmd(path, repo):
    import subprocess
    r = Path(repo)
    if not (r / ".git").is_dir():
        print(f"{repo} не git-репозиторий")
        return 1
    # все коммиты, где файл встречался, от старых к новым
    out = subprocess.run(["git", "-C", str(r), "log", "--reverse", "--format=%H",
                          "--", path], capture_output=True, text=True)
    revs = [x for x in out.stdout.split() if x]
    if not revs:
        print(f"Файл {path} не встречается в истории")
        return 1
    print(f"Коммитов с этим путём: {len(revs)} (от старых к новым)")
    found = None
    for rev in revs:
        show = subprocess.run(["git", "-C", str(r), "show", f"{rev}:{path}"],
                              capture_output=True)
        if show.returncode == 0 and show.stdout.strip():
            found = (rev, show.stdout)
            break
    if not found:
        print("Ни в одном коммите содержимого нет — файл всегда был пустым")
        return 1
    rev, content = found
    import hashlib
    date = subprocess.run(["git", "-C", str(r), "show", "-s", "--format=%ci", rev],
                          capture_output=True, text=True).stdout.strip()
    print(f"\nПервый коммит с НЕПУСТЫМ содержимым: {rev[:7]}  ({date})")
    print(f"   размер {len(content)} байт, sha256 "
          f"{hashlib.sha256(content).hexdigest()[:16]}...")
    print("\nПочему это важно: коммит УДАЛЕНИЯ файла тоже «касается» пути,")
    print("но `git show REV:path` на нём даст пустой вывод. Сверка переименований")
    print("по такому коммиту даст ложный вердикт «содержимое потеряно».")
    return 0


# --------------------------------------------------------------------------- #
# вывод: чек-лист перед тем, как что-то заявить
# --------------------------------------------------------------------------- #

REPORT_CHECKLIST = [
    ("Сырой ответ напечатан?", "не_угадывать.py probe ... — до любого вывода из API"),
    ("Форма данных проверена?", "словарь или список, точные имена ключей"),
    ("Имена параметров из документации?", "не из памяти, не перебором"),
    ("Служебный мусор вырезан?", "не_угадывать.py clean ... — до сравнения текстов"),
    ("Искал внутри <main>?", "не первым find() по всему файлу"),
    ("Вызов рядом с цифрой?", "метод, путь, сырой ответ — иначе цифра непроверяема"),
    ("quotepath отключён?", "git -c core.quotepath=false ls-files"),
    ("Манифест пересобран после правок?", "порядок: правка → манифест → коммит"),
    ("Смежные эндпоины посмотрены?", "неполная находка — не находка"),
    ("Якорь для правки единственный?", "не_угадывать.py править ..."),
    ("Правка сделана через править?", "иначе нет ни проверки, ни откатa"),
    ("После правки файл проверен?", "ast.parse / json.loads / парные теги (только .html)"),
    ("Список файлов git без кавычек?", "core.quotepath=false"),
    ("Переименования сверены по первому непустому коммиту?", "не_угадывать.py история ..."),
]


def report_cmd():
    print("=" * 72)
    print("ЧЕК-ЛИСТ ПЕРЕД ТЕМ, КАК ЧТО-ТО ЗАЯВИТЬ")
    print("=" * 72)
    for i, (q, how) in enumerate(REPORT_CHECKLIST, 1):
        print(f"  {i:>2}. [ ] {q}")
        print(f"        {how}")
    print()
    print("Если хоть один пункт не отмечен — это гипотеза, а не результат,")
    print("и в отчёте она должна называться гипотезой.")
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

    e = sub.add_parser("править", help="правка файла со страховкой")
    e.add_argument("path")
    e.add_argument("--старый", help="что заменить (обязан быть единственным в файле)")
    e.add_argument("--новый", help="на что заменить")
    e.add_argument("--старый-файл", help="файл с текстом для замены")
    e.add_argument("--новый-файл", help="файл с новым текстом")

    g = sub.add_parser("git-файлы", help="список файлов без quotepath + сверка с манифестом")
    g.add_argument("--repo", default=".")

    h = sub.add_parser("история", help="первый коммит с непустым содержимым файла")
    h.add_argument("path")
    h.add_argument("--repo", default=".")

    sub.add_parser("вывод", help="чек-лист перед тем, как что-то заявить")

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
    if args.cmd == "править":
        return edit_cmd(args.path, args.старый, args.новый,
                        args.старый_файл, args.новый_файл)
    if args.cmd == "git-файлы":
        return git_files_cmd(args.repo)
    if args.cmd == "история":
        return history_cmd(args.path, args.repo)
    if args.cmd == "вывод":
        return report_cmd()
    return 1


if __name__ == "__main__":
    sys.exit(main())
