# -*- coding: utf-8 -*-
"""
Собирает config.php для приёмника заявок и кладёт его на хостинг ВНЕ public_html.

Почему отдельным скриптом, а не руками через файловый менеджер: в конфиге пароль и
адреса, и он не должен ни попасть в репозиторий, ни пройти через переписку. Значения
берутся из Site/.env.deploy — того же файла, что и доступы к FTP (он в .gitignore).

Нужные строки в .env.deploy:
    FTP_HOST, FTP_USER, FTP_PASSWORD   — доступ к хостингу
    VIEW_PASSWORD=...                  — пароль на просмотр заявок (orders.php)
    EMAIL_TO=aiodoggmd@yandex.ru       — куда слать заявки
    EMAIL_FROM=zakaz@zilma.pro         — от кого (ящик на своём домене)
    SITE_URL=...                       — адрес сайта; на время проверки технический
    MAX_TOKEN=, MAX_CHAT_ID=           — необязательно
    TG_TOKEN=, TG_CHAT_ID=             — необязательно, туда уходит только состав заказа

Запуск: .venv/Scripts/python.exe scripts/deploy-config.py
"""
import ftplib
import io
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

TEMPLATE = """<?php
// Собран автоматически (scripts/deploy-config.py). Лежит ВНЕ public_html: из браузера
// его не открыть. В Git не попадает — здесь пароль и адреса.
return [
    'data_dir' => '{data_dir}',

    'email_to'   => '{email_to}',
    'email_from' => '{email_from}',

    // Встроенная mail() на этом хостинге заблокирована — письма уходят только через
    // SMTP с авторизацией, от имени ящика на домене.
    'smtp_host' => '{smtp_host}',
    'smtp_port' => {smtp_port},
    'smtp_user' => '{smtp_user}',
    'smtp_pass' => '{smtp_pass}',
    'smtp_helo' => 'zilma.pro',

    'max_token'   => '{max_token}',
    'max_chat_id' => '{max_chat_id}',

    'telegram_bot_token' => '{tg_token}',
    'telegram_chat_id'   => '{tg_chat}',

    'view_password' => '{view_password}',
    'site_url'      => '{site_url}',

    'max_file_bytes' => 8 * 1024 * 1024,
    'allowed_mime' => [
        'image/jpeg', 'image/png', 'image/webp', 'image/heic',
        'application/pdf',
        'application/msword',
        'application/vnd.ms-excel',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    ],
];
"""


def creds() -> dict:
    f = ROOT / '.env.deploy'
    if not f.is_file():
        sys.exit('Нет Site/.env.deploy')
    out = {}
    for line in f.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            out[k.strip()] = v.strip()
    return out


def main() -> None:
    c = creds()
    missing = [k for k in ('FTP_HOST', 'FTP_USER', 'FTP_PASSWORD', 'VIEW_PASSWORD',
                           'SMTP_USER', 'SMTP_PASS') if not c.get(k)]
    if missing:
        sys.exit('В .env.deploy не хватает: ' + ', '.join(missing))

    body = TEMPLATE.format(
        data_dir=c.get('DATA_DIR', '/home/z/zilmapro/zilma-data'),
        email_to=c.get('EMAIL_TO', 'aiodoggmd@yandex.ru'),
        email_from=c.get('EMAIL_FROM', c.get('SMTP_USER', 'zakaz@zilma.pro')),
        smtp_host=c.get('SMTP_HOST', 'smtp.sweb.ru'),
        smtp_port=c.get('SMTP_PORT', '465'),
        smtp_user=c.get('SMTP_USER', ''),
        smtp_pass=c.get('SMTP_PASS', ''),
        max_token=c.get('MAX_TOKEN', ''),
        max_chat_id=c.get('MAX_CHAT_ID', ''),
        tg_token=c.get('TG_TOKEN', ''),
        tg_chat=c.get('TG_CHAT_ID', ''),
        view_password=c['VIEW_PASSWORD'],
        site_url=c.get('SITE_URL', 'https://www.zilma.pro'),
    )

    ftp = ftplib.FTP(c['FTP_HOST'], timeout=60)
    ftp.login(c['FTP_USER'], c['FTP_PASSWORD'])
    ftp.set_pasv(True)
    # Корень FTP-аккаунта = /home/z/zilmapro, то есть ВЫШЕ public_html. Ровно то, что нужно:
    # конфиг и заявки лежат там, куда веб-сервер не пускает.
    ftp.storbinary('STOR config.php', io.BytesIO(body.encode('utf-8')))
    try:
        ftp.mkd('zilma-data')
    except ftplib.error_perm:
        pass          # папка уже есть
    print('config.php положен в корень аккаунта, папка zilma-data готова')
    print('содержимое корня:', ftp.nlst())
    ftp.quit()


if __name__ == '__main__':
    main()
