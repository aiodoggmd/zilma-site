# -*- coding: utf-8 -*-
"""
Товары, которых нет в наличии: были в прайсе за последние 90 дней, а сейчас нет.

    .venv/Scripts/python.exe scripts/build-gone-items.py              # обновить журнал и список
    .venv/Scripts/python.exe scripts/build-gone-items.py --backfill   # один раз: журнал из истории git

Зачем (решение пользователя 30.09.2026): товар, которого нет на складе, из каталога исчезал,
и клиент думал, что не нашёл его, а не что его нет. Теперь он виден серым, без цены и без
галочки «в заявку», с пометкой «нет в наличии» — в каталоге и в поиске.

ПОЧЕМУ ОТДЕЛЬНЫЙ ФАЙЛ, а не пометка в priceItems.json. priceItems читают около десяти мест:
акции, палитры, таблицы статей, «повторить заказ», замена оттенков, перенос журналов,
сборщик «под заказ», сверка. Второй сорт товаров («под заказ», 21.09.2026) молча сломал
сразу несколько из них. Серые товары лежат в src/data/gone-items.json, и их читает только
каталог на главной — остальной сайт и весь конвейер прайса о них не знают.

Журнал src/data/price-last-seen.json: «бренд::артикул» -> когда товар видели в последний
раз, с именем, разделом и категорией. Ключ — артикул, а не имя: из 205 «ушедших» имён 25
оказались тем же товаром после переименования, и по имени он показался бы дважды — живой
и серый рядом. Товары «под заказ» в журнал не пишутся (их наличие ведёт бланк LebeL), но
товар, ушедший со склада «под заказ», серым не считается — он на сайте есть.

Имя и раздел серого товара берутся из Price/Каталог.xlsx, если он там есть (у ушедших до
13.09.2026 в истории остались сырые имена 1С), иначе — последние известные.
"""
import datetime as dt
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'src' / 'data'
ITEMS = DATA / 'priceItems.json'
JOURNAL = DATA / 'price-last-seen.json'
GONE = DATA / 'gone-items.json'
PRICES_TS = DATA / 'prices.ts'
WINDOW_DAYS = 90


def article(name: str) -> str:
    """Последнее слово имени; хвост складского LebeL «4263лп» -> «4263» (как в verify-price-sync)."""
    tok = name.strip().split()[-1].rstrip('.').lower() if name.strip() else ''
    m = re.fullmatch(r'(\d{3,10})[а-яё]{1,3}', tok)
    return m.group(1) if m else tok


def key(it: dict) -> str:
    return f'{(it.get("brand") or "").upper()}::{article(it["name"])}'


def price_date() -> str:
    m = re.search(r"date: '(\d{4}-\d{2}-\d{2})'", PRICES_TS.read_text(encoding='utf-8'))
    if not m:
        sys.exit('✗ не нашёл дату прайса в src/data/prices.ts')
    return m.group(1)


def remember(journal: dict, items: list, date: str) -> int:
    n = 0
    for it in items:
        if it.get('preorder'):
            continue
        journal[key(it)] = {'brand': it.get('brand'), 'name': it['name'], 'section': it.get('section'),
                            'category': it.get('category'), 'lastSeen': date}
        n += 1
    return n


def backfill() -> dict:
    """Журнал из всех версий priceItems.json в git — от старых к новым."""
    log = subprocess.run(['git', 'log', '--reverse', '--format=%H %ad', '--date=short', '--', 'src/data/priceItems.json'],
                         cwd=ROOT, capture_output=True, text=True, encoding='utf-8').stdout.split('\n')
    journal = {}
    versions = 0
    for line in filter(None, log):
        sha, date = line.split()
        raw = subprocess.run(['git', 'show', f'{sha}:src/data/priceItems.json'], cwd=ROOT,
                             capture_output=True, text=True, encoding='utf-8').stdout
        try:
            remember(journal, json.loads(raw), date)
            versions += 1
        except json.JSONDecodeError:
            continue
    if versions == 0:
        sys.exit('✗ в истории git не нашлось ни одной версии priceItems.json — журнал не собран')
    print(f'  история: {versions} версий прайса, {len(journal)} товаров в журнале')
    return journal


def catalog_names() -> dict:
    """«бренд::артикул» -> (имя, раздел) из Price/Каталог.xlsx; пусто, если каталога нет."""
    path = ROOT / 'scripts' / 'apply-catalog-names.py'
    if not (ROOT / 'Price' / 'Каталог.xlsx').exists():
        return {}
    spec = importlib.util.spec_from_file_location('acn', path)
    acn = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(acn)
    out = {}
    for c in acn.read_catalog():
        out[f'{c["brand"].upper()}::{article(c["name"])}'] = (c['name'], c.get('category'))
    return out


NO_SECTION_FOLDER = 'Нет в наличии'


def place(gone: list, items: list) -> None:
    """Раздел для серого товара без раздела. Без этого 85 серых легли россыпью над папками
    бренда (замечание пользователя 30.09.2026: «позиции вне папки»).
    1) По родне: живые товары того же бренда с тем же началом имени (3, затем 2 слова) —
       если у всей родни один раздел, берём его. Тот же приём, что в add-to-catalog.py.
    2) Родни нет, а у бренда есть разделы — в отдельную папку «Нет в наличии» в конце бренда.
       У брендов совсем без разделов (CONCEPT, CAREPROST) серые остаются общим списком,
       как и их живые товары."""
    by_brand: dict = {}
    for i in items:
        by_brand.setdefault((i.get('brand') or '').upper(), []).append(i)
    for g in gone:
        if g['section']:
            continue
        live = by_brand.get((g['brand'] or '').upper(), [])
        words = g['name'].lower().split()
        for k in (3, 2):
            if len(words) <= k:
                continue
            prefix = ' '.join(words[:k])
            kin = {i.get('section') for i in live if i['name'].lower().startswith(prefix)}
            if len(kin) == 1 and None not in kin:
                g['section'] = kin.pop()
                break
        if not g['section'] and any(i.get('section') for i in live):
            g['section'] = NO_SECTION_FOLDER


def main() -> None:
    items = json.loads(ITEMS.read_text(encoding='utf-8'))
    if not items:
        sys.exit('✗ priceItems.json пуст — список серых не строю')
    date = price_date()

    if '--backfill' in sys.argv:
        journal = backfill()
    else:
        journal = json.loads(JOURNAL.read_text(encoding='utf-8')) if JOURNAL.exists() else {}
    stock_now = remember(journal, items, date)

    present = {key(i) for i in items}  # включая «под заказ»: ушедший туда товар на сайте есть
    live_names = {i['name'] for i in items}
    # Бренд из истории может быть ложным: 16.09.2026 заголовок линейки WELLA (Illumina, KP Me+/CT)
    # сборщик принял за бренд, и в старых версиях прайса у 243 позиций «бренд» — линейка. Без
    # этой отсечки первый прогон объявил 161 живой товар ушедшим: ключ «бренд::артикул» не
    # совпадал, а сам товар стоял на сайте под настоящим брендом.
    live_brands = {(i.get('brand') or '').upper() for i in items}
    today = dt.date.fromisoformat(date)
    cat = catalog_names()
    gone = []
    for k, e in journal.items():
        if k in present or e['name'] in live_names or (e.get('brand') or '').upper() not in live_brands:
            continue
        if (today - dt.date.fromisoformat(e['lastSeen'])).days > WINDOW_DAYS:
            continue
        name, section = cat.get(k, (e['name'], e.get('section')))
        gone.append({'brand': e['brand'], 'name': name, 'section': section or e.get('section'),
                     'category': e.get('category'), 'lastSeen': e['lastSeen']})
    place(gone, items)
    gone.sort(key=lambda g: ((g['brand'] or ''), g['name'].lower()))

    # Проверка ДО записи: серый товар не должен совпасть с живым по имени (имя могло прийти
    # из каталога и совпасть с живым товаром другого артикула).
    clash = [g['name'] for g in gone if g['name'] in live_names]
    if clash:
        sys.exit(f'✗ СТОП: {len(clash)} серых совпали по имени с живыми товарами, например {clash[:3]}')

    JOURNAL.write_text(json.dumps(dict(sorted(journal.items())), ensure_ascii=False, indent=1), encoding='utf-8')
    GONE.write_text(json.dumps(gone, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'Прайс от {date}: складских {stock_now}, в журнале {len(journal)}, '
          f'нет в наличии (за {WINDOW_DAYS} дней): {len(gone)}')


if __name__ == '__main__':
    main()
