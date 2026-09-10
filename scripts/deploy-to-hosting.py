# -*- coding: utf-8 -*-
"""
Выкладка собранного сайта на российский хостинг по FTP — замена автодеплоя Vercel.

Зачем скрипт, а не «перетащить папку в файловом менеджере»: в сборке около двух тысяч
файлов, руками это и долго, и легко забыть один. Скрипт заливает только изменившееся
(сравнивает размер) и в конце показывает, что именно поехало.

Доступы читаются из файла Site/.env.deploy (он в .gitignore, в репозиторий не попадёт)
или из переменных окружения. Файл удобнее: пароль вписывается один раз в блокноте и не
проходит ни через чат, ни через историю команд.

    FTP_HOST=77.222.40.65
    FTP_USER=логин
    FTP_PASSWORD=пароль
    FTP_DIR=public_html

Запуск:
    npx astro build
    .venv/Scripts/python.exe scripts/deploy-to-hosting.py            # показать план
    .venv/Scripts/python.exe scripts/deploy-to-hosting.py --apply    # залить
"""
import argparse
import ftplib
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DIST = ROOT / 'dist'
# Файлы, которые лежат на хостинге постоянно и сборкой не создаются — их не трогаем,
# иначе выкладка каждый раз затирала бы приём заявок и настройки сервера.
KEEP = {'.htaccess', 'order.php', 'orders.php', 'config.php'}


def load_credentials() -> dict:
    """Сначала файл .env.deploy рядом с проектом, потом переменные окружения.

    Пароль намеренно НЕ передаётся аргументом командной строки: команда с ним осела бы
    в истории терминала и в логе сессии.
    """
    creds = {}
    env_file = ROOT / '.env.deploy'
    if env_file.is_file():
        for line in env_file.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            creds[key.strip()] = value.strip()
    for key in ('FTP_HOST', 'FTP_USER', 'FTP_PASSWORD', 'FTP_DIR'):
        if os.environ.get(key):
            creds[key] = os.environ[key]
    return creds


def walk_local():
    for p in DIST.rglob('*'):
        if p.is_file():
            yield p.relative_to(DIST).as_posix(), p.stat().st_size


def remote_sizes(ftp: ftplib.FTP, base: str) -> dict:
    """Карта «путь -> размер» на сервере. MLSD есть не везде, поэтому с запасным вариантом."""
    sizes = {}

    def scan(path: str):
        try:
            entries = list(ftp.mlsd(path))
        except (ftplib.error_perm, AttributeError):
            return
        for name, facts in entries:
            if name in ('.', '..'):
                continue
            full = f'{path}/{name}'
            if facts.get('type') == 'dir':
                scan(full)
            elif facts.get('type') == 'file':
                sizes[full[len(base) + 1:]] = int(facts.get('size', -1))

    scan(base)
    return sizes


def ensure_dir(ftp: ftplib.FTP, path: str, made: set):
    if path in made or not path:
        return
    parent = path.rsplit('/', 1)[0] if '/' in path else ''
    ensure_dir(ftp, parent, made)
    try:
        ftp.mkd(path)
    except ftplib.error_perm:
        pass          # уже есть — это нормальная ситуация, а не ошибка
    made.add(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true', help='реально заливать, иначе только план')
    args = ap.parse_args()

    if not DIST.is_dir():
        sys.exit('Нет папки dist — сначала `npx astro build`')

    creds = load_credentials()
    host = creds.get('FTP_HOST')
    user = creds.get('FTP_USER')
    password = creds.get('FTP_PASSWORD')
    base = creds.get('FTP_DIR', 'public_html').rstrip('/')
    if not (host and user and password):
        sys.exit('Не хватает доступов. Заполни Site/.env.deploy: FTP_HOST, FTP_USER, FTP_PASSWORD')

    local = dict(walk_local())
    print(f'в сборке файлов: {len(local)}')

    ftp = ftplib.FTP(host, timeout=60)
    ftp.login(user, password)
    ftp.set_pasv(True)
    remote = remote_sizes(ftp, base)
    print(f'на сервере файлов: {len(remote)}')

    to_upload = [f for f, size in local.items() if remote.get(f) != size]
    to_delete = [f for f in remote if f not in local and f.rsplit('/', 1)[-1] not in KEEP]

    print(f'\nзалить: {len(to_upload)}')
    for f in to_upload[:15]:
        print('  ', f)
    if len(to_upload) > 15:
        print(f'   … и ещё {len(to_upload) - 15}')
    print(f'удалить лишние: {len(to_delete)}')
    for f in to_delete[:10]:
        print('  ', f)

    if not args.apply:
        print('\nЭто был план. Для заливки — запустить с --apply')
        ftp.quit()
        return

    made = set()
    for i, f in enumerate(to_upload, 1):
        target = f'{base}/{f}'
        ensure_dir(ftp, target.rsplit('/', 1)[0], made)
        with (DIST / f).open('rb') as fh:
            ftp.storbinary(f'STOR {target}', fh)
        if i % 100 == 0 or i == len(to_upload):
            print(f'  залито {i}/{len(to_upload)}')

    for f in to_delete:
        try:
            ftp.delete(f'{base}/{f}')
        except ftplib.error_perm as e:
            print('  не удалось удалить', f, e)

    ftp.quit()
    print('\nГотово. Проверить: сжатие, тестовая заявка, каталог, скачивание прайса.')


if __name__ == '__main__':
    main()
