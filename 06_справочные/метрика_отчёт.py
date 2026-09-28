#!/usr/bin/env python3
"""Отчёт по аналитике zapahstarosti.ru: Яндекс.Метрика + Яндекс.Вебмастер.

Запуск:  python3 /home/user/метрика_отчёт.py [--days 60]

Что показывает:
  Метрика   — визиты, просмотры, посетители по дням, источники, устройства, гео,
              отказы, глубина, длительность, точки входа.
  Вебмастер — сколько страниц в поиске, ИКС, проблемы сайта, sitemap,
              поисковые запросы с показами, очередь и квота переобхода.

Токен берётся из webmaster_recrawl.py (яндексовый OAuth, тот же для Метрики
и Вебмастера). Ничего не пишет и не отправляет — только читает.
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

def load_token():
    """Токен Яндекса: переменная окружения YANDEX_TOKEN или соседний
    webmaster_recrawl.py. В архив токен не пишем — только способ его получить."""
    import os
    env = os.environ.get("YANDEX_TOKEN", "").strip()
    if env:
        return env
    here = Path(__file__).resolve().parent
    for cand in (here / "webmaster_recrawl.py",
                 here.parent / "webmaster_recrawl.py",
                 Path("/home/user/webmaster_recrawl.py")):
        try:
            m = re.search(r'TOKEN\s*=\s*"([^"]+)"', cand.read_text(encoding="utf-8"))
            if m:
                return m.group(1)
        except OSError:
            continue
    sys.exit("Не найден токен Яндекса. Задайте переменную окружения YANDEX_TOKEN "
             "или положите рядом файл webmaster_recrawl.py со строкой TOKEN = \"...\".")


TOKEN = load_token()
CID = '111871686'          # счётчик Метрики
UID = '1773537030'         # user_id Вебмастера
HOST = 'https:zapahstarosti.ru:443'
API_M = 'https://api-metrica.yandex.net'
API_W = 'https://api.webmaster.yandex.net'


def call(url):
    req = urllib.request.Request(url, method='GET')
    req.add_header('Authorization', 'OAuth ' + TOKEN)
    req.add_header('User-Agent', 'otchet/1.0')
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            raw = r.read().decode()
            return r.status, (json.loads(raw) if raw.strip() else {})
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}
    except Exception as e:
        return 0, {'error': str(e)}


def h(title):
    print(f"\n{'=' * 72}\n{title}\n{'=' * 72}")


def metrika(params):
    st, d = call(API_M + '/stat/v1/data?' + urllib.parse.urlencode(params))
    if st != 200:
        print(f"   ! HTTP {st}: {str(d)[:160]}")
        return None
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--days', type=int, default=60)
    args = ap.parse_args()
    d1 = (date.today() - timedelta(days=args.days)).isoformat()
    d2 = date.today().isoformat()

    print(f"ОТЧЁТ ПО САЙТУ zapahstarosti.ru")
    print(f"период: {d1} … {d2} ({args.days} дней)   счётчик Метрики: {CID}")

    # ---------- МЕТРИКА ----------
    h('МЕТРИКА — итоги')
    d = metrika({'id': CID, 'metrics': 'ym:s:visits,ym:s:pageviews,ym:s:users',
                 'dimensions': 'ym:s:date', 'date1': d1, 'date2': d2,
                 'limit': '1000', 'sort': 'ym:s:date'})
    if d:
        t = d['totals']
        rows = [(r['dimensions'][0].get('name'), r['metrics']) for r in d['data']]
        print(f"   визитов {int(t[0])} | просмотров {int(t[1])} | посетителей {int(t[2])}")
        print(f"   дней с данными: {len(rows)} из {args.days}"
              f"  (в среднем {round(t[0] / max(args.days, 1), 2)} визита в день)")
        print(f"\n   {'дата':>12} {'визитов':>8} {'просмотров':>11} {'посетителей':>12}")
        for day, m in rows:
            print(f"   {day:>12} {int(m[0]):>8} {int(m[1]):>11} {int(m[2]):>12}")

    h('МЕТРИКА — качество посещений')
    d = metrika({'id': CID, 'metrics': 'ym:s:bounceRate,ym:s:pageDepth,'
                 'ym:s:avgVisitDurationSeconds', 'date1': d1, 'date2': d2})
    if d:
        t = d['totals']
        print(f"   отказы {round(t[0], 1)} %  |  глубина {round(t[1], 2)} стр/визит"
              f"  |  длительность {round(t[2] / 60, 1)} мин")

    for label, dim in [('ИСТОЧНИКИ ТРАФИКА', 'ym:s:lastTrafficSource'),
                       ('УСТРОЙСТВА', 'ym:s:deviceCategory'),
                       ('ГЕО (топ-8)', 'ym:s:regionCountry')]:
        h(f'МЕТРИКА — {label}')
        d = metrika({'id': CID, 'metrics': 'ym:s:visits,ym:s:pageviews,ym:s:users',
                     'dimensions': dim, 'date1': d1, 'date2': d2,
                     'limit': '8', 'sort': '-ym:s:visits'})
        if d:
            for r in d['data']:
                name = str(r['dimensions'][0].get('name'))[:52]
                m = r['metrics']
                print(f"   {name:<52} визитов {int(m[0]):>4}  просмотров {int(m[1]):>4}"
                      f"  посет. {int(m[2]):>4}")

    h('МЕТРИКА — точки входа (топ-15)')
    d = metrika({'id': CID, 'metrics': 'ym:s:visits,ym:s:pageviews,ym:s:users',
                 'dimensions': 'ym:s:startURL', 'date1': d1, 'date2': d2,
                 'limit': '15', 'sort': '-ym:s:visits'})
    if d:
        for r in d['data']:
            name = str(r['dimensions'][0].get('name')).replace('https://zapahstarosti.ru', '')
            m = r['metrics']
            print(f"   {(name or '/'):<40} визитов {int(m[0]):>4}  просмотров {int(m[1]):>4}"
                  f"  посет. {int(m[2]):>4}")

    # ---------- ВЕБМАСТЕР ----------
    def w(path, params=None):
        url = f'{API_W}/v4.1/user/{UID}/hosts/{HOST}{path}'
        if params:
            url += '?' + urllib.parse.urlencode(params, doseq=True)
        return call(url)

    h('ВЕБМАСТЕР — сводка')
    st, d = w('/summary')
    if st == 200:
        print(f"   ИКС (качество сайта):      {d.get('sqi')}")
        print(f"   страниц в поиске:          {d.get('searchable_pages_count')}")
        print(f"   исключённых страниц:       {d.get('excluded_pages_count')}")
        print(f"   проблемы:                  {d.get('site_problems')}")
    else:
        print(f"   ! HTTP {st}: {str(d)[:160]}")

    h('ВЕБМАСТЕР — проблемы сайта')
    st, d = w('/diagnostics')
    if st == 200:
        probs = d.get('problems', {})
        bad = [(k, v) for k, v in probs.items() if v.get('state') == 'PRESENT']
        print(f"   проверок: {len(probs)}, присутствуют: {len(bad)}")
        for k, v in sorted(bad, key=lambda x: str(x[1].get('severity'))):
            print(f"   [{v.get('severity')}] {k}  ({str(v.get('last_state_update'))[:19]})")
        hard = [k for k, v in probs.items()
                if v.get('severity') in ('FATAL', 'CRITICAL', 'ERROR')]
        print(f"   серьёзных проверок (FATAL/CRITICAL/ERROR) в наборе: {len(hard)}"
              f" — все {'чисто' if not any(probs[k].get('state') == 'PRESENT' for k in hard) else 'ЕСТЬ ПРОБЛЕМЫ'}")
    else:
        print(f"   ! HTTP {st}: {str(d)[:160]}")

    h('ВЕБМАСТЕР — sitemap')
    st, d = w('/sitemaps')
    if st == 200:
        for s in d.get('sitemaps', []):
            print(f"   {s.get('sitemap_url')}")
            print(f"      URL обработано: {s.get('urls_count')}, ошибок: {s.get('errors_count')}")
    else:
        print(f"   ! HTTP {st}: {str(d)[:160]}")

    h('ВЕБМАСТЕР — поисковые запросы с показами')
    st, d = w('/search-queries/popular', {
        'order_by': 'TOTAL_SHOWS', 'device_type_indicator': 'ALL',
        'date_from': d1, 'date_to': d2,
        'query_indicator': ['TOTAL_SHOWS', 'TOTAL_CLICKS', 'AVG_SHOW_POSITION'],
        'limit': '500'})
    if st == 200:
        qs = d.get('queries', [])
        print(f"   запросов с показами: {d.get('count', len(qs))}")
        if not qs:
            print("   — сайт не показывался в поиске ни по одному запросу")
        for q in qs[:30]:
            ind = q.get('indicators', {})
            print(f"   {str(q.get('query_text'))[:44]:<44} показы {int(ind.get('TOTAL_SHOWS', 0)):>5}"
                  f"  клики {int(ind.get('TOTAL_CLICKS', 0)):>4}"
                  f"  поз. {round(ind.get('AVG_SHOW_POSITION', 0), 1)}")
    else:
        print(f"   ! HTTP {st}: {str(d)[:160]}")

    h('ВЕБМАСТЕР — переобход')
    st, d = w('/recrawl/quota')
    if st == 200:
        print(f"   дневная квота: {d.get('daily_quota')}, осталось: {d.get('quota_remainder')}")
    st, d = w('/recrawl/queue')
    if st == 200:
        tasks = d.get('tasks', [])
        print(f"   задач в очереди: {len(tasks)}")
        for t in tasks[:10]:
            print(f"      {str(t.get('url')).replace('https://zapahstarosti.ru', ''):<36}"
                  f" {t.get('state')}  (добавлено {str(t.get('added_time'))[:19]})")
    print("\nГотово. Ничего не отправлялось — только чтение.")


if __name__ == '__main__':
    sys.exit(main())
