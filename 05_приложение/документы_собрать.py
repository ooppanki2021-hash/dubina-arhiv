# Сборка зашифрованных документов для вкладки «Документы» приложения.
# Пароль берётся ТОЛЬКО из переменной окружения DOCS_PASSWORD и нигде не сохраняется.
# Запуск: DOCS_PASSWORD='...' python3 документы_собрать.py
# Результат: app/docs/docs.bin (все тексты) и app/docs/w-N.bin (файлы Word),
# соль прописывается в app/index.html и автономную копию; в автономную копию
# тексты встраиваются целиком (файлы Word там недоступны).
import os, re, json, base64, secrets, hashlib
from pathlib import Path
import markdown
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ITER = 310000
HERE = Path(__file__).resolve().parent
H = Path('/home/user')
PRODUCTS = [
 ('Гель для душа v5.3', 'ТЕХНОЛОГУ_пакет_04-10-2026', [
   ('Рецептурная карта', '01_ФОРМУЛА_гель_ДУБИНА_v5.3_беловая.md', '2_Рецептурная_карта_гель_ДУБИНА.docx'),
   ('Проект ТУ', '02_ТУ_гель_ДУБИНА_проект_беловой.md', '3_Проект_ТУ_гель_ДУБИНА.docx'),
   ('Письмо технологу', '03_ПИСЬМО_технологу.md', '1_Письмо_технологу.docx')]),
 ('Мыло-синдет v1.1', 'ТЕХНОЛОГУ_синдет', [
   ('Рецептурная карта', '01_ФОРМУЛА_синдет_ДУБИНА_v1.1_беловая.md', '2_Рецептурная_карта_синдет_ДУБИНА.docx'),
   ('Проект ТУ', '02_ТУ_синдет_ДУБИНА_проект_беловой.md', '3_Проект_ТУ_синдет_ДУБИНА.docx'),
   ('Письмо технологу', '03_ПИСЬМО_технологу_синдет.md', '1_Письмо_технологу_синдет.docx')]),
 ('Порошок универсальный v1.1', 'ТЕХНОЛОГУ_порошок', [
   ('Рецептурная карта', '01_ФОРМУЛА_порошок_ДУБИНА_v1.1_беловая.md', '01_ФОРМУЛА_порошок_ДУБИНА_v1.1_беловая.docx'),
   ('Проект ТУ', '02_ТУ_порошок_ДУБИНА_проект_беловой.md', '02_ТУ_порошок_ДУБИНА_проект_беловой.docx'),
   ('Письмо технологу', '03_ПИСЬМО_технологу_порошок.md', '03_ПИСЬМО_технологу_порошок.docx')]),
 ('Дезодорант-ролик v2.2', 'ТЕХНОЛОГУ_дезодорант', [
   ('Рецептурная карта', '01_ФОРМУЛА_дезодорант_ДУБИНА_v2.2_беловая.md', '01_ФОРМУЛА_дезодорант_ДУБИНА_v2.2_беловая.docx'),
   ('Проект ТУ', '02_ТУ_дезодорант_ДУБИНА_проект_беловой.md', '02_ТУ_дезодорант_ДУБИНА_проект_беловой.docx'),
   ('Письмо технологу', '03_ПИСЬМО_технологу_дезодорант.md', '03_ПИСЬМО_технологу_дезодорант.docx')]),
 ('Влажные салфетки v1.1', 'ТЕХНОЛОГУ_салфетки', [
   ('Рецептурная карта', '01_ФОРМУЛА_салфетки_ДУБИНА_v1.1_беловая.md', '01_ФОРМУЛА_салфетки_ДУБИНА_v1.1_беловая.docx'),
   ('Проект ТУ', '02_ТУ_салфетки_ДУБИНА_проект_беловой.md', '02_ТУ_салфетки_ДУБИНА_проект_беловой.docx'),
   ('Письмо производителю', '03_ПИСЬМО_производителю_салфетки.md', '03_ПИСЬМО_производителю_салфетки.docx')]),
]

def md_html(text):
    out, prev = [], ''
    for line in text.split('\n'):
        is_list = re.match(r'\s*(- |\d+\. )', line)
        if is_list and prev.strip() and not re.match(r'\s*(- |\d+\. )', prev):
            out.append('')
        out.append(line); prev = line
    return markdown.markdown('\n'.join(out), extensions=['tables', 'sane_lists'])

def main():
    pw = os.environ.get('DOCS_PASSWORD')
    assert pw and len(pw) >= 12, 'нужен DOCS_PASSWORD (не короче 12 знаков)'
    idx = HERE / 'app' / 'index.html'
    alone = HERE / 'МЕЧТА_автономная_копия.html'
    t = idx.read_text(encoding='utf-8')
    m = re.search(r"const DOCS_SALT = '([0-9a-f]*)';", t)
    salt = bytes.fromhex(m.group(1)) if m and len(m.group(1)) == 32 else secrets.token_bytes(16)
    key = AESGCM(hashlib.pbkdf2_hmac('sha256', pw.encode('utf-8'), salt, ITER, 32))
    enc = lambda b: (lambda iv: iv + key.encrypt(iv, b, None))(secrets.token_bytes(12))
    out = HERE / 'app' / 'docs'; out.mkdir(parents=True, exist_ok=True)
    for f in out.glob('*.bin'): f.unlink()
    bundle, n = {'products': []}, 0
    for name, folder, docs in PRODUCTS:
        items = []
        for title, md, dx in docs:
            src = H / folder / md; word = H / folder / 'для_печати' / dx
            n += 1; wname = f'w-{n}.bin'
            (out / wname).write_bytes(enc(word.read_bytes()))
            items.append({'title': title, 'html': md_html(src.read_text(encoding='utf-8')), 'w': wname, 'fname': dx})
        bundle['products'].append({'name': name, 'docs': items})
    blob = enc(json.dumps(bundle, ensure_ascii=False).encode('utf-8'))
    (out / 'docs.bin').write_bytes(blob)
    b64 = base64.b64encode(blob).decode()
    for p, inline in ((idx, ''), (alone, b64)):
        s = p.read_text(encoding='utf-8')
        s = re.sub(r"const DOCS_SALT = '[0-9a-f]*';", f"const DOCS_SALT = '{salt.hex()}';", s)
        s = re.sub(r"const DOCS_INLINE = '[A-Za-z0-9+/=]*';", f"const DOCS_INLINE = '{inline}';", s)
        p.write_text(s, encoding='utf-8')
    print('документов:', n, '| docs.bin, байт:', len(blob))

if __name__ == '__main__':
    main()
