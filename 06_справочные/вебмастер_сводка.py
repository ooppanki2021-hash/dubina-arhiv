#!/usr/bin/env python3
"""Полная сводка Яндекс.Вебмастера по площадке zapahstarosti.ru — только чтение.

Зачем этот файл: раньше состояние Вебмастера снимали руками в дашборде и
переносили в 02_документы_проекта/ПОКАЗАТЕЛИ_поиска.json, а программные проверки
делались разовыми запросами «на глаз», из-за чего часть методов API оставалась
незамеченной (группа /indexing/ нашлась только 04.10.2026). Здесь собрано всё,
что API отдаёт, в одном вызове и в одном формате.

Что собирает (все запросы — GET, ничего не отправляет и не меняет):
  1. пользователь и список площадок (verified, host_data_status);
  2. карточку площадки, состояние верификации и владельцев;
  3. sitemap-ы: адрес, дата последнего чтения роботом, число URL, ошибки;
  4. очередь переобхода (состояния задач, незавершённые) и суточную квоту;
  5. /indexing/samples — что робот скачал и с каким статусом, полностью,
     с разбивкой по статусам и датой последнего обхода;
  6. сверку скачанного против sitemap снимка архива: чего робот не видел и
     чего нет в sitemap.

Чего здесь НЕТ и почему: число «страницы в поиске» и список исключённых из
поиска Вебмастер показывает только в дашборде — у этих цифр нет метода API
(проверено перебором имён 04.10.2026: /search-queries/, /search-appearance/,
/indexing/count и другие отвечают 404). Поэтому сводка честно помечает их как
«только дашборд» и берёт из ПОКАЗАТЕЛИ_поиска.json для сравнения, не выдавая
старое число за свежее.

Токен: переменная окружения YANDEX_TOKEN или файл token.txt рядом со скриптом
(одна строка) — та же договорённость, что у webmaster_recrawl.py. В архив токен
не пишется.

Использование:
    python3 вебмастер_сводка.py                 # печать сводки
    python3 вебмастер_сводка.py --записать      # плюс положить dated-JSON рядом
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
API = "https://api.webmaster.yandex.net"
HOST_HINT = "zapahstarosti"
ПОРОГ_ЛИМИТА = 100


def load_token():
    env = os.environ.get("YANDEX_TOKEN", "").strip()
    if env:
        return env
    for name in ("token.txt", "token.env"):
        p = HERE / name
        if p.is_file():
            return p.read_text(encoding="utf-8").strip()
    sys.exit("Не найден токен Яндекса. Задайте YANDEX_TOKEN или положите token.txt рядом.")


def api(version, path, token):
    req = urllib.request.Request(f"{API}/{version}{path}",
                                 headers={"Authorization": "OAuth " + token})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def probe(token):
    """Первая версия API, отвечающая на /user, и список живых методов площадки."""
    version = uid = None
    for v in ("v4.2", "v4.1", "v4"):
        try:
            d = api(v, "/user", token)
            version, uid = v, str(d["user_id"])
            break
        except Exception:
            continue
    if not version:
        sys.exit("Ни одна версия API Вебмастера не ответила — проверьте токен и сеть.")
    return version, uid


def indexing_samples(version, uid, host, token):
    """Все образцы индексации, с пагинацией: лимит 100, offset шагом 100."""
    out, offset = [], 0
    while True:
        d = api(version, f"/user/{uid}/hosts/{host}/indexing/samples"
                         f"?offset={offset}&limit={ПОРОГ_ЛИМИТА}", token)
        batch = d.get("samples", [])
        out += batch
        if len(out) >= d.get("count", 0) or not batch:
            return d.get("count", len(out)), out
        offset += ПОРОГ_ЛИМИТА


def sitemap_urls():
    p = ROOT / "03-сайт" / "сайт_текущий" / "sitemap.xml"
    if not p.is_file():
        return []
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    return [e.text.strip() for e in ET.parse(p).getroot().findall(".//s:loc", ns)]


def main():
    ap = argparse.ArgumentParser(description="Полная сводка Вебмастера, только чтение")
    ap.add_argument("--записать", action="store_true",
                    help="положить сводку в 06_справочные/ВЕБМАСТЕР_сводка.json")
    args = ap.parse_args()
    token = load_token()
    version, uid = probe(token)

    сводка = {"api_version": version, "user_id": uid}
    hosts = api(version, f"/user/{uid}/hosts", token).get("hosts", [])
    host = next((h["host_id"] for h in hosts if HOST_HINT in h.get("host_id", "")),
                hosts[0]["host_id"] if hosts else None)
    if not host:
        sys.exit("У пользователя нет площадок в Вебмастере.")
    сводка["площадки"] = [{k: h.get(k) for k in ("host_id", "verified", "host_data_status")}
                          for h in hosts]

    база = f"/user/{uid}/hosts/{host}"
    сводка["верификация"] = api(version, база + "/verification/", token)
    сводка["владельцы"] = api(version, база + "/owners/", token).get("users", [])
    сводка["sitemap_ы"] = api(version, база + "/sitemaps/", token).get("sitemaps", [])
    очередь = api(version, база + "/recrawl/queue", token).get("tasks", [])
    сводка["переобход"] = {
        "состояния": dict(Counter(t.get("state") for t in очередь)),
        "незавершённые": [t.get("url") for t in очередь if t.get("state") != "DONE"],
        "квота": api(version, база + "/recrawl/quota", token),
    }
    count, samples = indexing_samples(version, uid, host, token)
    сводка["индексация"] = {
        "всего_образцов": count,
        "статусы": dict(Counter(s.get("status") for s in samples)),
        "последний_обход": max((s.get("access_date", "") for s in samples), default=""),
        "страницы": [{k: s.get(k) for k in ("url", "status", "http_code", "access_date")}
                     for s in samples],
    }

    скачано = {s["url"] for s in samples if s.get("url")}
    из_sitemap = set(sitemap_urls())
    сводка["сверка_с_sitemap"] = {
        "в_sitemap_но_робот_не_скачивал": sorted(из_sitemap - скачано),
        "робот_скачивал_но_нет_в_sitemap": sorted(скачано - из_sitemap),
    }

    пок = ROOT / "02_документы_проекта" / "ПОКАЗАТЕЛИ_поиска.json"
    if пок.is_file():
        m = json.loads(пок.read_text(encoding="utf-8"))
        сводка["только_дашборд"] = {
            "источник": "02_документы_проекта/ПОКАЗАТЕЛИ_поиска.json (снято руками)",
            "дата_снятия": m.get("date"),
            "страниц_в_поиске": m.get("search", {}).get("pages_in_search"),
            "исключено_low_quality": m.get("search", {}).get("excluded_low_quality"),
            "примечание": "у этих цифр нет метода API; не принимать за свежие",
        }

    # ---------- печать ----------
    print(f"Вебмастер, пользователь {uid}, API /{version}")
    for h in сводка["площадки"]:
        print(f"  площадка {h['host_id']}: verified={h['verified']}, "
              f"статус данных {h['host_data_status']}")
    v = сводка["верификация"]
    print(f"  верификация: {v.get('verification_state')} кодом "
          f"{v.get('verification_uin')} ({v.get('verification_type')}), "
          f"проверка {str(v.get('latest_verification_time'))[:10]}")
    for s in сводка["sitemap_ы"]:
        print(f"  sitemap {s.get('sitemap_url')}: URL {s.get('urls_count')}, "
              f"ошибок {s.get('errors_count')}, робот читал "
              f"{str(s.get('last_access_date'))[:10]}")
    п = сводка["переобход"]
    print(f"  переобход: состояния {п['состояния']}, незавершённых "
          f"{len(п['незавершённые'])}; квота {п['квота'].get('daily_quota')}, "
          f"осталось {п['квота'].get('quota_remainder')}")
    и = сводка["индексация"]
    print(f"  индексация: образцов {и['всего_образцов']}, статусы {и['статусы']}, "
          f"последний обход {str(и['последний_обход'])[:10]}")
    св = сводка["сверка_с_sitemap"]
    print(f"  в sitemap, но робот не скачивал: {len(св['в_sitemap_но_робот_не_скачивал'])}")
    for u in св["в_sitemap_но_робот_не_скачивал"]:
        print(f"      {u}")
    if св["робот_скачивал_но_нет_в_sitemap"]:
        print(f"  робот скачивал, но нет в sitemap: "
              f"{св['робот_скачивал_но_нет_в_sitemap']}")
    д = сводка.get("только_дашборд")
    if д:
        print(f"  только дашборд (снято {д['дата_снятия']}): в поиске "
              f"{д['страниц_в_поиске']}, исключено {д['исключено_low_quality']} — "
              f"метода API у этих цифр нет")

    if args.записать:
        stamp = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d")
        сводка["дата_сводки"] = stamp
        out = HERE / "ВЕБМАСТЕР_сводка.json"
        out.write_text(json.dumps(сводка, ensure_ascii=False, indent=1) + "\n",
                       encoding="utf-8")
        print(f"\n  записано: {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
