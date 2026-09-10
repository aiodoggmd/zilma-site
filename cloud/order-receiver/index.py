# -*- coding: utf-8 -*-
"""
Приёмник заявок Zilma в Yandex Cloud (серверы в РФ).

ЗАЧЕМ ЭТО ВООБЩЕ ЕСТЬ. С 1 июля 2025 действует новая редакция ч. 5 ст. 18 152-ФЗ:
при сборе персональных данных россиян запрещено записывать их в базы за пределами РФ.
Раньше форма сайта отправляла имя и телефон на serverless-функцию Vercel (заграница),
оттуда в Telegram — то есть первичная запись происходила не там, где положено.

КАК УСТРОЕНО ТЕПЕРЬ:
  браузер  ──POST──▶  эта функция (РФ)  ──▶ заявка в Object Storage (РФ)
                              │
                              └──▶ в Telegram уходит уведомление БЕЗ персональных данных:
                                   «Заявка 20260910-4f2a · 5 позиций · 6 255 ₽» и ссылка.
Имя и телефон в Telegram не попадают вообще, поэтому трансграничной передачи нет и
уведомлять о ней Роскомнадзор не требуется. Продавец открывает ссылку и видит заявку
целиком — страницу отдаёт эта же функция, из РФ, по паролю.

ФАЙЛ-ВЛОЖЕНИЕ НЕ ИДЁТ ЧЕРЕЗ ФУНКЦИЮ. У Cloud Functions потолок тела запроса 3.5 МБ, а
фото с телефона легко весит больше; вдобавок base64 раздувает его ещё на треть. Поэтому
браузер сначала просит у функции временную ссылку на загрузку (presigned PUT) и кладёт
файл прямо в Object Storage, а в заявке остаётся только его ключ. Файл при этом тоже
никуда из РФ не уезжает.

Маршруты (через API Gateway):
  POST /order        — принять заявку
  POST /upload-url   — выдать временную ссылку для загрузки файла
  GET  /view         — показать заявку целиком (по паролю)

Переменные окружения функции:
  BUCKET             имя бакета Object Storage
  S3_KEY_ID/S3_SECRET статический ключ сервисного аккаунта (роль storage.editor)
  TELEGRAM_BOT_TOKEN  тот же бот @wella_news_bot
  TELEGRAM_CHAT_ID    куда слать уведомление
  VIEW_PASSWORD       пароль на просмотр заявки
  PUBLIC_BASE_URL     адрес API Gateway, из него собирается ссылка в уведомлении
"""
import base64
import binascii
import cgi
import datetime
import hmac
import io
import json
import os
import secrets
import urllib.parse
import urllib.request

import boto3

BUCKET = os.environ['BUCKET']
TELEGRAM_TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
TELEGRAM_CHAT = os.environ['TELEGRAM_CHAT_ID']
VIEW_PASSWORD = os.environ['VIEW_PASSWORD']
PUBLIC_BASE_URL = os.environ['PUBLIC_BASE_URL'].rstrip('/')

MAX_ATTACHMENT_BYTES = 8 * 1024 * 1024
ALLOWED_UPLOAD_TYPES = {
    'image/jpeg', 'image/png', 'image/webp', 'image/heic', 'application/pdf',
    'application/msword', 'application/vnd.ms-excel',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
}

s3 = boto3.client(
    's3',
    endpoint_url='https://storage.yandexcloud.net',
    aws_access_key_id=os.environ['S3_KEY_ID'],
    aws_secret_access_key=os.environ['S3_SECRET'],
    region_name='ru-central1',
)


def reply(code, body, content_type='application/json', headers=None):
    h = {
        'Content-Type': content_type,
        # Сайт живёт на другом домене (Vercel), поэтому браузеру нужен явный CORS.
        'Access-Control-Allow-Origin': 'https://www.zilma.pro',
        'Access-Control-Allow-Headers': 'Content-Type',
        'Access-Control-Allow-Methods': 'POST, GET, OPTIONS',
    }
    if headers:
        h.update(headers)
    return {
        'statusCode': code,
        'headers': h,
        'body': body if isinstance(body, str) else json.dumps(body, ensure_ascii=False),
    }


def read_body(event) -> bytes:
    raw = event.get('body') or ''
    if event.get('isBase64Encoded'):
        try:
            return base64.b64decode(raw)
        except binascii.Error:
            return b''
    return raw.encode('utf-8')


def order_id() -> str:
    """Дата для человека + случайная часть, чтобы ссылку нельзя было подобрать."""
    return datetime.datetime.now().strftime('%Y%m%d') + '-' + secrets.token_hex(8)


def money(value: float) -> str:
    return f'{value:,.0f}'.replace(',', ' ')


def notify_telegram(oid: str, items_count: int, total: float, has_file: bool):
    """Уведомление БЕЗ персональных данных — в этом весь смысл схемы.

    Ни имени, ни телефона, ни комментария: комментарий клиент пишет свободно и вполне
    может назвать там себя. За границу уходит только номер заявки, счёт позиций, сумма
    и ссылка.
    """
    text = (
        f'Новая заявка {oid}\n'
        f'{items_count} поз. · {money(total)} ₽'
        + ('\nЕсть вложение' if has_file else '')
        + f'\n\nОткрыть: {PUBLIC_BASE_URL}/view?id={oid}'
    )
    data = urllib.parse.urlencode({
        'chat_id': TELEGRAM_CHAT,
        'text': text,
        'disable_web_page_preview': 'true',
    }).encode()
    req = urllib.request.Request(
        f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage', data=data)
    with urllib.request.urlopen(req, timeout=20) as r:
        r.read()


def handle_order(event):
    body = read_body(event)
    ctype = (event.get('headers') or {}).get('Content-Type') or ''
    fp = io.BytesIO(body)
    form = cgi.FieldStorage(fp=fp, environ={
        'REQUEST_METHOD': 'POST',
        'CONTENT_TYPE': ctype,
        'CONTENT_LENGTH': str(len(body)),
    })

    def field(name, limit=2000):
        v = form.getfirst(name, '')
        return str(v).strip()[:limit]

    # Honeypot: настоящий посетитель это поле не видит. Отвечаем «ок», чтобы бот не
    # понял, что его отсеяли, и не начал подбирать другую форму.
    if field('hp_field'):
        return reply(200, {'ok': True})

    name = field('name', 200)
    contact = field('contact', 200)
    if not name or not contact:
        return reply(400, {'error': 'missing_fields'})

    try:
        items = json.loads(form.getfirst('items_json', '') or '[]')
    except json.JSONDecodeError:
        items = []
    total = sum(float(i.get('price', 0)) * int(i.get('qty', 1)) for i in items)

    oid = order_id()
    record = {
        'id': oid,
        'at': datetime.datetime.now().isoformat(timespec='seconds'),
        'name': name,
        'contact': contact,
        'messenger': field('messenger', 50),
        'comment': field('comment', 4000),
        'items': items,
        'total': total,
        'attachment': field('attachment_key', 300),
    }
    s3.put_object(
        Bucket=BUCKET,
        Key=f'orders/{oid}.json',
        Body=json.dumps(record, ensure_ascii=False).encode('utf-8'),
        ContentType='application/json; charset=utf-8',
    )

    # Заявка уже сохранена в РФ. Если Telegram не ответит — это не повод терять заказ,
    # поэтому падение уведомления не превращаем в ошибку для клиента.
    try:
        notify_telegram(oid, len(items), total, bool(record['attachment']))
    except Exception as e:                                    # noqa: BLE001
        print('telegram failed:', e)

    return reply(200, {'ok': True, 'id': oid})


def handle_upload_url(event):
    """Временная ссылка на загрузку файла прямо в Object Storage, минуя функцию."""
    try:
        data = json.loads(read_body(event) or b'{}')
    except json.JSONDecodeError:
        return reply(400, {'error': 'bad_request'})

    content_type = str(data.get('type', ''))[:100]
    size = int(data.get('size', 0) or 0)
    if content_type not in ALLOWED_UPLOAD_TYPES:
        return reply(400, {'error': 'file_type_invalid'})
    if size <= 0 or size > MAX_ATTACHMENT_BYTES:
        return reply(400, {'error': 'file_too_large'})

    key = f'attachments/{datetime.datetime.now():%Y%m%d}/{secrets.token_hex(12)}'
    url = s3.generate_presigned_url(
        'put_object',
        Params={'Bucket': BUCKET, 'Key': key, 'ContentType': content_type},
        ExpiresIn=600,
    )
    return reply(200, {'url': url, 'key': key})


def handle_view(event):
    """Заявка целиком — по паролю. Отдаётся из РФ, наружу ничего не пересылается."""
    params = event.get('queryStringParameters') or {}
    oid = str(params.get('id', ''))[:64]
    given = str(params.get('p', ''))

    if not hmac.compare_digest(given, VIEW_PASSWORD):
        return reply(200, PASSWORD_FORM.replace('{id}', urllib.parse.quote(oid)),
                     content_type='text/html; charset=utf-8')

    try:
        obj = s3.get_object(Bucket=BUCKET, Key=f'orders/{oid}.json')
    except s3.exceptions.NoSuchKey:
        return reply(404, '<p>Заявка не найдена</p>', content_type='text/html; charset=utf-8')

    r = json.loads(obj['Body'].read())
    rows = ''.join(
        f'<tr><td>{i.get("name", "")}</td><td>{i.get("qty", 1)}</td>'
        f'<td>{money(float(i.get("price", 0)))} ₽</td></tr>'
        for i in r.get('items', [])
    )
    file_link = ''
    if r.get('attachment'):
        link = s3.generate_presigned_url(
            'get_object', Params={'Bucket': BUCKET, 'Key': r['attachment']}, ExpiresIn=3600)
        file_link = f'<p><a href="{link}">Скачать вложение</a></p>'

    html = VIEW_PAGE.format(
        id=r['id'], at=r['at'].replace('T', ' '), name=r['name'], contact=r['contact'],
        messenger=r.get('messenger') or '—', comment=r.get('comment') or '—',
        rows=rows, total=money(r.get('total', 0)), file_link=file_link,
    )
    return reply(200, html, content_type='text/html; charset=utf-8')


PASSWORD_FORM = """<!doctype html><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Заявка Zilma</title>
<style>body{font:16px system-ui;margin:0;display:grid;place-items:center;min-height:100vh;
background:#faf6f0;color:#2b201c}form{display:grid;gap:10px;width:min(320px,90vw)}
input,button{font:inherit;padding:10px;border:1px solid #d8cfbf;border-radius:4px}
button{background:#38628c;color:#fff;border-color:#38628c;cursor:pointer}</style>
<form method=get><input type=hidden name=id value="{id}">
<label>Пароль<input type=password name=p autofocus></label>
<button>Открыть заявку</button></form>"""

VIEW_PAGE = """<!doctype html><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Заявка {id}</title>
<style>body{{font:16px system-ui;margin:0;padding:20px;background:#faf6f0;color:#2b201c}}
.card{{max-width:720px;margin:0 auto;background:#fff;border:1px solid #d8cfbf;padding:18px}}
h1{{font-size:1.1rem;margin:0 0 4px}}.meta{{color:#7a6f66;font-size:.85rem;margin:0 0 14px}}
dl{{display:grid;grid-template-columns:auto 1fr;gap:6px 14px;margin:0 0 16px}}
dt{{color:#7a6f66;font-size:.85rem}}dd{{margin:0}}
table{{width:100%;border-collapse:collapse;font-size:.9rem}}
td,th{{border-bottom:1px solid #eee;padding:6px 4px;text-align:left}}
td:nth-child(2),td:nth-child(3){{text-align:right;white-space:nowrap}}
.total{{margin-top:12px;font-weight:700}}a{{color:#38628c}}</style>
<div class=card>
<h1>Заявка {id}</h1><p class=meta>{at}</p>
<dl><dt>Имя</dt><dd>{name}</dd><dt>Контакт</dt><dd>{contact}</dd>
<dt>Чат</dt><dd>{messenger}</dd><dt>Комментарий</dt><dd>{comment}</dd></dl>
<table><thead><tr><th>Товар</th><th>Кол-во</th><th>Цена</th></tr></thead><tbody>{rows}</tbody></table>
<p class=total>Итого: {total} ₽</p>
{file_link}
</div>"""


def handler(event, context):
    method = event.get('httpMethod', 'GET').upper()
    path = (event.get('path') or '/').rstrip('/') or '/'

    if method == 'OPTIONS':
        return reply(204, '')
    if method == 'POST' and path.endswith('/order'):
        return handle_order(event)
    if method == 'POST' and path.endswith('/upload-url'):
        return handle_upload_url(event)
    if method == 'GET' and path.endswith('/view'):
        return handle_view(event)
    return reply(404, {'error': 'not_found'})
