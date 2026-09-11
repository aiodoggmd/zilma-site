# -*- coding: utf-8 -*-
"""
Утренняя проверка живого сайта — одна команда вместо десятка «а вдруг».

Запуск:  .venv/Scripts/python.exe scripts/morning-check.py
         (можно и обычным python — нужен только стандартный набор)

Что проверяет и ПОЧЕМУ именно это (каждый пункт — из реально случившегося, а не «на всякий
случай»):

  Страницы     все адреса из карты сайта открываются и отдаются сжатыми. Заодно проверяет
               саму карту сайта: если она пустая или битая, поисковики перестают обходить.
  Прайс        файл для скачивания реально лежит на сервере. Имя прайса меняется с каждым
               обновлением (в нём дата) — проверяем ровно тот, что подставлен в prices.ts,
               иначе кнопка «Скачать EXCEL» ведёт в пустоту и об этом никто не узнает.
  Заявки       приёмник отвечает. Запрос уходит с заполненной ловушкой для ботов (hp_field),
               поэтому order.php отвечает «ок» и выходит ДО сохранения заявки, писем и
               счётчика частоты — ни одного побочного действия. При этом проверка честная:
               config.php и mailer.php подключаются в самом начале файла, и если их нет,
               ответ будет 500. Ровно этот случай чуть не устроила выкладка 11.09.2026.
  Защита       страница заявок закрыта паролем, конфиг и папка с заказами не открываются
               из интернета. Проверяем каждый раз, потому что сломать это может любая
               правка .htaccess, и внешне сайт при этом выглядит здоровым.
  Сертификат   сколько дней осталось. Он продлевается сам, но если продление однажды не
               сработает, узнать об этом хочется заранее, а не от клиента.
  Домен        сколько дней осталось (по реестру, не по памяти). Автопродление включено, но
               оно ничего не спишет с пустого счёта — предупреждаем за два месяца.

Проверка НИЧЕГО не чинит и не пишет на сервер. Ответ короткий: либо «всё в порядке», либо
что именно не так и что с этим делать. Код возврата 1, если есть проблема, 0 — если чисто.
"""
import json
import re
import socket
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = 'https://www.zilma.pro'
DOMAIN = 'zilma.pro'
RDAP = 'https://rdap.identitydigital.services/rdap/domain/zilma.pro'

# За сколько дней начинать беспокоиться. Сертификат живёт 90 дней и продлевается сам за 30 —
# 20 значит «продление уже должно было пройти, но не прошло». Домен продлевается раз в год
# вручную деньгами на счёте, поэтому предупреждаем сильно заранее.
CERT_WARN_DAYS = 20
DOMAIN_WARN_DAYS = 60

TIMEOUT = 20
UA = 'ZilmaMorningCheck/1.0'


class Problem(Exception):
    """Проверка не прошла. Текст — то, что человек увидит в отчёте."""


def plural(n: int, one: str, few: str, many: str) -> str:
    """«22 страницы», а не «22 страниц» — отчёт читают глазами каждый день."""
    tail, tens = n % 10, n % 100
    if tail == 1 and tens != 11:
        form = one
    elif 2 <= tail <= 4 and not 12 <= tens <= 14:
        form = few
    else:
        form = many
    return f'{n} {form}'


def fetch(url: str, data: bytes | None = None, headers: dict | None = None,
          compressed: bool = False):
    """Возвращает (код ответа, заголовки, тело). Ошибочный код — это тоже ответ, а не сбой:
    часть проверок как раз ждёт 401 или 403.

    По умолчанию просим НЕсжатый ответ: сжатие на сервере — brotli, а его распаковки нет в
    стандартном наборе Python, и тело пришло бы нечитаемой кашей (на этом первый прогон и
    споткнулся: «в карте сайта 0 адресов» при исправной карте). Сжатие проверяется отдельно,
    по заголовку ответа, — для этого и нужен compressed=True."""
    # Имя файла прайса приходит из prices.ts и теоретически может оказаться с кириллицей —
    # без экранирования urllib падает с UnicodeEncodeError вместо понятного отчёта.
    url = urllib.parse.quote(url, safe=":/?&=%~+.,-_")
    req = urllib.request.Request(url, data=data, method='POST' if data else 'GET')
    req.add_header('User-Agent', UA)
    req.add_header('Accept-Encoding', 'br, gzip' if compressed else 'identity')
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()
    except (urllib.error.URLError, socket.timeout, ssl.SSLError) as e:
        raise Problem(f'{url} — не отвечает ({e})') from e


def check_pages() -> str:
    status, _, body = fetch(f'{SITE}/sitemap-0.xml')
    if status != 200:
        raise Problem(f'карта сайта отдаёт {status} — поисковики перестанут обходить сайт')
    urls = re.findall(r'<loc>([^<]+)</loc>', body.decode('utf-8', 'replace'))
    if len(urls) < 10:
        raise Problem(f'в карте сайта всего {len(urls)} адресов — похоже, сборка неполная')

    def one(u: str):
        st, _, b = fetch(u)
        if st != 200:
            return f'{u} → {st}'
        # Тело намеренно проверяем по содержимому, а не по длине: страница может ответить
        # 200 и отдать пустой каркас — снаружи это выглядит как рабочий сайт.
        if b'</html>' not in b[-400:] and b'</html>' not in b:
            return f'{u} — ответ без конца страницы (оборван)'
        return None

    with ThreadPoolExecutor(max_workers=8) as pool:
        bad = [x for x in pool.map(one, urls) if x]
    if bad:
        raise Problem('; '.join(bad[:3]) + (f' и ещё {len(bad) - 3}' if len(bad) > 3 else ''))

    # Сжатие задаётся в .htaccess по типам файлов, поэтому достаточно одной страницы —
    # но проверять его надо: без него главная весит 2,5 МБ вместо 120 КБ, и на мобильном
    # интернете это разница между «открылось» и «человек ушёл».
    _, hdrs, body = fetch(SITE + '/', compressed=True)
    if not hdrs.get('Content-Encoding'):
        raise Problem('страницы отдаются без сжатия — проверь .htaccess на сервере '
                      '(главная весит 2,5 МБ вместо ~120 КБ)')
    return (f'{plural(len(urls), "страница", "страницы", "страниц")}, все открываются, '
            f'сжатие работает ({len(body) // 1024} КБ главная)')


def check_price() -> str:
    """Имя файла берём из src/data/prices.ts — источника правды для кнопки на сайте."""
    src = (ROOT / 'src/data/prices.ts').read_text(encoding='utf-8')
    m = re.search(r"file:\s*'([^']+)'", src)
    if not m:
        raise Problem('не нашёл имя файла прайса в src/data/prices.ts — проверь формат файла')
    path = m.group(1)
    status, _, body = fetch(SITE + path)
    if status != 200:
        raise Problem(f'{path} отдаёт {status} — кнопка «Скачать EXCEL» ведёт в пустоту')
    # xlsx — это zip, любой настоящий файл начинается с PK. Так ловится случай, когда
    # вместо файла сервер отдал страницу с ошибкой (она тоже приходит с кодом 200).
    if not body.startswith(b'PK'):
        raise Problem(f'{path} скачивается, но это не xlsx — вероятно, отдалась страница ошибки')
    return f'{path.rsplit("/", 1)[-1]}, {len(body) // 1024} КБ, скачивается'


def check_orders() -> str:
    """Побочных действий нет: заполненная ловушка для ботов заставляет order.php ответить
    и выйти до сохранения заявки, писем и счётчика частоты."""
    data = urllib.parse.urlencode({'hp_field': 'morning-check'}).encode()
    status, _, body = fetch(f'{SITE}/order.php', data=data,
                            headers={'Content-Type': 'application/x-www-form-urlencoded'})
    if status == 500:
        raise Problem('приёмник заявок отвечает 500 — скорее всего пропал config.php или '
                      'mailer.php на сервере; заявки не примутся')
    if status != 200:
        raise Problem(f'приёмник заявок отвечает {status} — заявки с сайта не дойдут')
    try:
        ok = json.loads(body.decode('utf-8')).get('ok') is True
    except ValueError:
        ok = False
    if not ok:
        raise Problem('приёмник заявок ответил не так, как должен — проверь order.php')
    return 'приёмник отвечает (config.php и mailer.php на месте)'


def check_protection() -> str:
    checks = [
        ('/orders.php', (401,), 'страница заявок открылась БЕЗ пароля'),
        ('/config.php', (403, 404), 'config.php отдаётся из интернета — там пароли и доступы'),
        ('/zilma-data/orders/', (403, 404), 'папка с заказами открыта из интернета'),
    ]
    bad = []
    for path, expected, message in checks:
        status, _, _ = fetch(SITE + path)
        if status not in expected:
            bad.append(f'{message} (ответ {status})')
    if bad:
        raise Problem('; '.join(bad))
    return 'заявки под паролем, конфиг и папка с заказами закрыты'


def check_cert() -> str:
    ctx = ssl.create_default_context()
    with socket.create_connection((f'www.{DOMAIN}', 443), timeout=TIMEOUT) as sock:
        with ctx.wrap_socket(sock, server_hostname=f'www.{DOMAIN}') as ssock:
            expires = datetime.strptime(ssock.getpeercert()['notAfter'],
                                        '%b %d %H:%M:%S %Y %Z').replace(tzinfo=timezone.utc)
    days = (expires - datetime.now(timezone.utc)).days
    text = f'ещё {days} дн. (до {expires:%d.%m.%Y})'
    if days < CERT_WARN_DAYS:
        raise Problem(f'сертификат истекает через {days} дн. — автопродление не сработало, '
                      f'выпусти вручную в панели SpaceWeb')
    return text


def check_domain() -> str:
    status, _, body = fetch(RDAP, headers={'Accept': 'application/json'})
    if status != 200:
        raise Problem(f'реестр доменов отвечает {status} — проверить срок не вышло '
                      f'(сайт при этом работает, это проверка про будущее)')
    events = json.loads(body.decode('utf-8')).get('events', [])
    iso = next((e['eventDate'] for e in events if e.get('eventAction') == 'expiration'), None)
    if not iso:
        raise Problem('в ответе реестра нет даты окончания — проверь вручную в cp.sweb.ru')
    expires = datetime.fromisoformat(iso.replace('Z', '+00:00'))
    days = (expires - datetime.now(timezone.utc)).days
    text = f'ещё {days} дн. (до {expires:%d.%m.%Y})'
    if days < DOMAIN_WARN_DAYS:
        raise Problem(f'домен заканчивается через {days} дн. — положи деньги на счёт '
                      f'в cp.sweb.ru: автопродление с пустого счёта ничего не спишет')
    return text


CHECKS = [
    ('Сайт', check_pages),
    ('Прайс', check_price),
    ('Заявки', check_orders),
    ('Защита', check_protection),
    ('Сертификат', check_cert),
    ('Домен', check_domain),
]


def main() -> None:
    print(f'\nZilma — утренняя проверка · {datetime.now():%d.%m.%Y %H:%M}\n')
    problems = []
    for label, fn in CHECKS:
        try:
            print(f'  ✓ {label:<11} {fn()}')
        except Problem as e:
            problems.append((label, str(e)))
            print(f'  ✗ {label:<11} {e}')
        except Exception as e:                     # noqa: BLE001 — лучше показать, чем упасть
            problems.append((label, f'проверка сломалась: {e}'))
            print(f'  ? {label:<11} проверка сломалась: {e}')

    if problems:
        print(f'\n  Проблем: {len(problems)}. Ничего само не чинится — покажи этот список мне.\n')
        sys.exit(1)
    print('\n  Всё в порядке.\n')


if __name__ == '__main__':
    main()
