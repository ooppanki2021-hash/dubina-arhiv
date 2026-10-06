# Расшифровка закрытых файлов архива (формулы, ТУ, письма технологам).
# Пароль — тот же, что у «Документов» приложения; спросить у автора. Пароль в архиве НЕ хранится.
# Запуск: pip install cryptography; DOCS_PASSWORD='...' python3 расшифровать.py  → файлы появятся в папке _расшифровано/
# Формат .bin: соль 16 байт | nonce 12 байт | AES-256-GCM; ключ = PBKDF2-SHA256(пароль, соль, 1000000 итераций).
import os, hashlib
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
ITER = 1000000
def main():
    pw = os.environ.get('DOCS_PASSWORD'); assert pw, 'нужен DOCS_PASSWORD'
    here = Path(__file__).parent; out = here / '_расшифровано'
    for f in sorted(here.rglob('*.bin')):
        b = f.read_bytes(); key = AESGCM(hashlib.pbkdf2_hmac('sha256', pw.encode(), b[:16], ITER, 32))
        dst = out / f.relative_to(here).with_suffix(''); dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(key.decrypt(b[16:28], b[28:], None)); print('ok', dst.relative_to(here))
if __name__ == '__main__': main()
