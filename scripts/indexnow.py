r"""Сообщить Яндексу (и Bing) о новых и изменённых страницах через IndexNow — вместо переобхода в Вебмастере.
Ключ не секретный: протокол требует, чтобы он лежал на сайте открыто (public/<ключ>.txt).
Запуск после публикации: python scripts/indexnow.py /articles/2026-10-12-foil-techniques-compared/ /articles/
Шлём на общий приёмник api.indexnow.org — он пересылает адреса Яндексу. Прямой yandex.com/indexnow
12.10.2026 рвал соединение (выход через VPN, NL), общий принял с первого раза.
Ответ 200 или 202 — адреса приняты в очередь; сам обход Яндекс делает в течение нескольких дней.
"""
import json
import sys
import urllib.request

HOST = 'www.zilma.pro'
KEY = '1a6f0d99e6ec6144a54c2319e50fd77f'


def main() -> None:
    paths = sys.argv[1:]
    if not paths:
        sys.exit('Укажи адреса страниц: /articles/... (можно полными ссылками)')
    urls = [p if p.startswith('http') else f'https://{HOST}{p}' for p in paths]
    body = json.dumps({'host': HOST, 'key': KEY, 'keyLocation': f'https://{HOST}/{KEY}.txt',
                       'urlList': urls}).encode()
    req = urllib.request.Request('https://api.indexnow.org/indexnow', data=body,
                                 headers={'Content-Type': 'application/json; charset=utf-8'})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            print(f'IndexNow: {r.status} — принято адресов: {len(urls)}')
    except urllib.error.HTTPError as e:
        sys.exit(f'IndexNow отказал: {e.code} {e.read().decode(errors="replace")[:300]}')


if __name__ == '__main__':
    main()
