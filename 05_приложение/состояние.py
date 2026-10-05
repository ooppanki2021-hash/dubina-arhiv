# Работа с синхронизированным состоянием приложения «Шаги к мечте».
# Состояние лежит зашифрованным в репозитории dubina-arhiv, ветка sostoyanie, файл sostoyanie.bin.
# В файлах на GitHub лежит ТЕКСТ base64 от шифровки (двоичное GitHub может перекодировать).
# Пароль и ключи берутся ТОЛЬКО из переменных окружения и нигде не сохраняются:
#   SYNC_PASSWORD — пароль синхронизации (тот, что вводится в приложении)
#   GH_TOKEN      — токен GitHub для чтения/записи (для команд pull/push)
#   APP_TOKEN     — токен, который вшивается в приложение (только для команды seal)
#
# Команды:
#   python3 состояние.py seal            — зашифровать APP_TOKEN паролем и вписать в app/index.html и автономную копию
#   python3 состояние.py pull out.json   — скачать и расшифровать состояние в файл
#   python3 состояние.py summary         — кратко: где мы, сколько галочек по шагам
#   python3 состояние.py push in.json    — зашифровать файл и отправить (updatedAt = сейчас, побеждает как последнее изменение)
#   python3 состояние.py files           — список файлов, которые она загрузила в «Документы» (нужен DOCS_PASSWORD)
#   python3 состояние.py file-get ID out — скачать и расшифровать один такой файл
import os, re, sys, json, time, base64, secrets, hashlib, urllib.request, urllib.error
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

HERE = Path(__file__).resolve().parent
IDX, ALONE = HERE / 'app' / 'index.html', HERE / 'МЕЧТА_автономная_копия.html'
REPO, BRANCH, PATH = 'ooppanki2021-hash/dubina-arhiv', 'sostoyanie', 'sostoyanie.bin'
ITER = 1000000

def salt():
    m = re.search(r"const SYNC_SALT = '([0-9a-f]*)';", IDX.read_text(encoding='utf-8'))
    return bytes.fromhex(m.group(1)) if m and len(m.group(1)) == 32 else None

def key(s):
    pw = os.environ['SYNC_PASSWORD']
    return AESGCM(hashlib.pbkdf2_hmac('sha256', pw.encode('utf-8'), s, ITER, 32))

def enc(k, data):
    iv = secrets.token_bytes(12); return iv + k.encrypt(iv, data, None)

def dec(k, blob):
    return k.decrypt(blob[:12], blob[12:], None)

def docs_key():
    s = re.search(r"const DOCS_SALT = '([0-9a-f]+)';", IDX.read_text(encoding='utf-8')).group(1)
    return AESGCM(hashlib.pbkdf2_hmac('sha256', os.environ['DOCS_PASSWORD'].encode('utf-8'), bytes.fromhex(s), ITER, 32))

def raw_get(path):
    req = urllib.request.Request(f'https://api.github.com/repos/{REPO}/contents/{path}?ref={BRANCH}',
        headers={'Authorization': 'Bearer ' + os.environ['GH_TOKEN'], 'Accept': 'application/vnd.github.raw+json'})
    with urllib.request.urlopen(req) as r: return r.read()

def api(method, body=None, path=PATH):
    url = f'https://api.github.com/repos/{REPO}/contents/{path}' + (f'?ref={BRANCH}' if method == 'GET' else '')
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body else None,
        headers={'Authorization': 'Bearer ' + os.environ['GH_TOKEN'], 'Accept': 'application/vnd.github+json',
                 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req) as r: return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e: return e.code, None

def pull():
    st, j = api('GET')
    if st == 404: return None, None
    assert st == 200, st
    return json.loads(dec(key(salt()), base64.b64decode(base64.b64decode(j['content'])))), j['sha']

def main():
    cmd = sys.argv[1]
    if cmd == 'seal':
        s = salt() or secrets.token_bytes(16)
        blob = base64.b64encode(enc(key(s), os.environ['APP_TOKEN'].encode())).decode()
        for p in (IDX, ALONE):
            t = p.read_text(encoding='utf-8')
            t = re.sub(r"const SYNC_SALT = '[0-9a-f]*';", f"const SYNC_SALT = '{s.hex()}';", t)
            t = re.sub(r"const SYNC_TOKEN_ENC = '[A-Za-z0-9+/=]*';", f"const SYNC_TOKEN_ENC = '{blob}';", t)
            p.write_text(t, encoding='utf-8')
        print('токен вшит, соль', s.hex()[:8] + '…')
    elif cmd == 'pull':
        S, sha = pull()
        Path(sys.argv[2]).write_text(json.dumps(S, ensure_ascii=False, indent=1), encoding='utf-8')
        print('скачано, изменено:', time.strftime('%d.%m.%Y %H:%M', time.localtime((S or {}).get('updatedAt', 0) / 1000)))
    elif cmd == 'summary':
        S, sha = pull()
        if not S: print('состояния на GitHub нет'); return
        print('изменено:', time.strftime('%d.%m.%Y %H:%M', time.localtime(S.get('updatedAt', 0) / 1000)))
        for m in S.get('miles', []):
            sub = m.get('sub') or []; dn = sum(1 for x in sub if x.get('done'))
            mark = '✅' if (m.get('done') or (sub and dn == len(sub))) else ('◐' if dn else '○')
            print(f"{mark} {m.get('n')} — {dn}/{len(sub)}")
        print('заметок:', len(S.get('notes', [])), '| дел:', len(S.get('tasks', [])))
    elif cmd == 'files':
        try: lst = json.loads(dec(docs_key(), base64.b64decode(raw_get('faily/spisok.bin'))))
        except urllib.error.HTTPError: lst = []
        for f in lst: print(f"{f['id']}  {f['date']}  {f['size']//1024} КБ  {f['name']}")
        if not lst: print('загруженных файлов нет')
    elif cmd == 'file-get':
        Path(sys.argv[3]).write_bytes(dec(docs_key(), base64.b64decode(raw_get(f'faily/{sys.argv[2]}.bin')))); print('сохранено', sys.argv[3])
    elif cmd == 'push':
        S = json.loads(Path(sys.argv[2]).read_text(encoding='utf-8'))
        S['updatedAt'] = int(time.time() * 1000)
        _, sha = pull()
        body = {'message': 'Состояние приложения — правка помощника', 'branch': BRANCH,
                'content': base64.b64encode(base64.b64encode(enc(key(salt()), json.dumps(S, ensure_ascii=False).encode()))).decode()}
        if sha: body['sha'] = sha
        st, _ = api('PUT', body); assert st in (200, 201), st
        print('отправлено')

if __name__ == '__main__':
    main()
