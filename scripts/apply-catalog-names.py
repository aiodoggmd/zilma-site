# -*- coding: utf-8 -*-
"""
Ставит в прайс правильные имена товаров из Price/Каталог.xlsx.

ЗАЧЕМ. Имена в прайсе приходят из 1С и для интернет-магазина не годятся:
сокращения («Ср-во д/быстрого роста»), обрезанные названия, оттенки без
описания. Пользователь причесал их вручную — результат лежит в
Price/Каталог.xlsx. Этот скрипт переносит причёсанные имена в прайс.

ПОЧЕМУ ПРАВИМ price-current.xlsx, А НЕ priceItems.json. Цепочка такая:
    Остатки_*.xlsx (1С) -> build_price_current.py -> price-current.xlsx
      -> xlsx-to-price-items.py -> priceItems.json -> сайт
Правка в конце цепочки живёт до следующего обновления прайса, потом её
затирает 1С. Правка в price-current.xlsx идёт дальше сама и попадает
заодно в файл, который клиент скачивает кнопкой «Скачать EXCEL», — иначе
на сайте были бы одни имена, а в скачанном файле другие.

ПРАВИЛО СОПОСТАВЛЕНИЯ (от пользователя, 13.09.2026):
    «сверяй название, и если нет совпадения — тогда артикул».
Проверено на всём каталоге: 877 позиций находятся по имени, 202 добираются
артикулом, 1079 из 1085 однозначно, НИ ОДНОЙ двусмысленности.
Порядок важен: у WELLA артикул 8/38 есть и у Illumina, и у Shinefinity,
а это разные краски, которые смешивать нельзя. По имени они расходятся,
по артикулу — столкнулись бы.

МЕСТО В РИТУАЛЕ ОБНОВЛЕНИЯ ПРАЙСА — сразу после build_price_current.py
и ДО xlsx-to-price-items.py:
    1. build_price_current.py      — собрать прайс из остатков 1С
    2. apply-catalog-names.py      — ЭТОТ скрипт, поставить имена из каталога
    3. xlsx-to-price-items.py      — собрать priceItems.json
    4. migrate-renamed-products.py — перенести журналы на новые имена
    5. verify-price-sync.py        — сверить, что кружки оттенков не осыпались

Запуск: python scripts/apply-catalog-names.py [--apply]
Без --apply — только предпросмотр, файл не трогается.
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / 'Price' / 'Каталог.xlsx'
PRICE_XLSX = ROOT / 'public' / 'prices' / 'price-current.xlsx'
PRICE_ITEMS = ROOT / 'src' / 'data' / 'priceItems.json'
NEW_NAMES_REPORT = ROOT / 'Price' / 'catalog-new-items.md'

# Бренд в каталоге и в прайсе назван по-разному. Товары те же, артикулы те же.
BRAND_ALIASES = {
    'ISKARTES': 'ISKARTES PROFESSIONAL',
}


def norm(s) -> str:
    """Схлопнуть пробелы. Та же нормализация, что в xlsx-to-price-items.py."""
    return re.sub(r'\s+', ' ', str(s).strip())


def key_name(s) -> str:
    """Ключ сравнения имён: пробелы схлопнуты, регистр снят. Больше ничего."""
    return norm(s).casefold()


def article_of(name: str) -> str:
    """Артикул — последний токен имени (та же логика, что в resolve-live-price.ts)."""
    toks = norm(name).split()
    return toks[-1] if toks else ''


def article_candidates(name: str):
    """Артикул с поправкой на хвост вроде «NEW».

    1С дописывает пометки в конец имени: «L-Color окислительная эмульсия 9%
    1000 мл 918 NEW». Тогда последний токен — не артикул, и сверка по артикулу
    молча проваливается. Если в последнем токене нет ни одной цифры, пробуем
    ещё и предпоследний. Поймано 13.09.2026 на единственной такой строке —
    но 1С будет присылать её и дальше.
    """
    toks = norm(name).split()
    if not toks:
        return []
    out = [toks[-1].upper()]
    if len(toks) > 1 and not re.search(r'\d', toks[-1]):
        out.append(toks[-2].upper())
    return out


def brand_variants(b: str):
    """Бренд плюс его псевдонимы — в обе стороны."""
    b = (b or '').upper()
    out = {b}
    if b in BRAND_ALIASES:
        out.add(BRAND_ALIASES[b])
    for short, full in BRAND_ALIASES.items():
        if b == full:
            out.add(short)
    return out


def words(name: str):
    """Слова имени без артикула — для разрешения ничьей по артикулу."""
    body = ' '.join(norm(name).split()[:-1])
    return set(re.findall(r'[0-9A-Za-zА-Яа-яЁё]+', body.casefold()))


def pick_closest(price_name: str, cands):
    """Из нескольких кандидатов по артикулу выбрать того, чьё имя ближе.

    Нужно, потому что артикул не уникален: у OLLIN артикул 0-88 носят и
    «Color 0/88 синий», и «Performanse 8-8» — разные товары. Пока имена
    совпадали дословно, до артикула дело не доходило; после причёсывания
    имён (мл./ml -> мл) совпадение пропало и ничья вылезла наружу.
    Берём кандидата со строго наибольшим пересечением слов. Если чёткого
    победителя нет — возвращаем None, и человек решает сам.
    """
    target = words(price_name)
    scored = sorted(((len(target & words(c['name'])), c) for c in cands),
                    key=lambda t: -t[0])
    if len(scored) < 2 or scored[0][0] > scored[1][0]:
        return scored[0][1] if scored and scored[0][0] else None
    return None


def read_catalog():
    """Каталог: жирный ВЕРХНИЙ регистр = бренд, 11 кегль = категория, 8 = товар.

    Уровни различаются только оформлением — колонка одна. Проверено 13.09.2026:
    14 брендов, 1085 товарных строк, разбор сходится с ручным пересчётом.
    """
    ws = openpyxl.load_workbook(CATALOG)['Sheet1']
    rows, brand, category = [], None, None
    for r in range(5, ws.max_row + 1):
        cell = ws.cell(row=r, column=2)
        if cell.value is None or not str(cell.value).strip():
            continue
        raw = str(cell.value).strip()
        size = cell.font.size if cell.font and cell.font.size else 0
        bold = bool(cell.font and cell.font.bold)
        is_caps = raw == raw.upper() and any(c.isalpha() for c in raw)
        if bold and is_caps and size >= 11:
            brand, category = raw, None
            continue
        if size >= 11:
            category = raw
            continue
        rows.append({'row': r, 'brand': brand, 'category': category,
                     'name': norm(raw)})
    return rows


def rows_from_sheet(ws, known_brands):
    """Товарные строки ЛИСТА прайса вместе с брендом и номером строки.

    Отдельной функцией, потому что вызывается из двух мест: отсюда (по файлу
    с диска) и из Price/build_price_current.py, который ставит имена ещё до
    сохранения — до промо-сайдкара и до колонки категорий, иначе и то и другое
    считается по старым именам 1С (поймано 14.09.2026: 494 строки подсвечивались
    синим в файле, который скачивает клиент).

    Бренд определяем по СПИСКУ известных брендов, а не по заливке ячейки:
    подсветка неразмеченных категорий затирает заливку бренда (поймано 2026-09-05).
    """
    rows, brand = [], ''
    for r in range(6, ws.max_row + 1):
        name = ws.cell(row=r, column=2).value
        price = ws.cell(row=r, column=3).value
        unit = ws.cell(row=r, column=4).value
        if not name:
            continue
        clean = norm(name)
        if price is None and not unit:
            if clean.upper() in known_brands:
                brand = clean.upper()
            continue
        if price is not None:
            rows.append({'row': r, 'brand': brand, 'name': clean})
    return rows


def read_price_rows(known_brands):
    """То же по файлу с диска: возвращает (книгу, лист, строки)."""
    wb = openpyxl.load_workbook(PRICE_XLSX)
    ws = wb.active
    return wb, ws, rows_from_sheet(ws, known_brands)


def resolve_names(catalog, price_rows):
    """{номер строки: имя из каталога} по правилу «имя, потом артикул».

    Единственное место, где живёт это правило. Вызывается и отсюда, и из
    сборщика прайса — чтобы порядок шагов не решал, какие имена попадут
    в промо-сайдкар и в колонку категорий.
    """
    by_name, by_article, by_any = defaultdict(list), defaultdict(list), defaultdict(list)
    for c in catalog:
        by_name[key_name(c['name'])].append(c)
        for a in article_candidates(c['name']):
            by_any[a].append(c)
            for b in brand_variants(c['brand']):
                by_article[(b, a)].append(c)

    out, ambiguous, missing = {}, [], []
    for p in price_rows:
        hits = by_name.get(key_name(p['name']), [])
        if not hits:
            for b in brand_variants(p['brand']):
                for a in article_candidates(p['name']):
                    hits = by_article.get((b, a), [])
                    if hits:
                        break
                if hits:
                    break
        if not hits:
            for a in article_candidates(p['name']):
                cand = by_any.get(a, [])
                if len(cand) == 1:
                    hits = cand
                    break
        if not hits:
            missing.append(p)
            continue
        if len({key_name(h['name']) for h in hits}) > 1:
            best = pick_closest(p['name'], hits)
            if best is None:
                ambiguous.append((p, hits))
                continue
            hits = [best]
        if hits[0]['name'] != p['name']:
            out[p['row']] = hits[0]['name']
    return out, ambiguous, missing


def main() -> None:
    apply = '--apply' in sys.argv

    if not CATALOG.exists():
        sys.exit(f'Нет файла каталога: {CATALOG}')
    if not PRICE_XLSX.exists():
        sys.exit(f'Нет файла прайса: {PRICE_XLSX}')

    catalog = read_catalog()
    known_brands = {i['brand'].upper() for i in
                    json.loads(PRICE_ITEMS.read_text(encoding='utf-8'))}
    wb, ws, price_rows = read_price_rows(known_brands)

    print(f'Каталог: {len(catalog)} товаров, '
          f'{len({c["brand"] for c in catalog})} брендов')
    print(f'Прайс:   {len(price_rows)} товаров')

    by_name = defaultdict(list)
    by_article = defaultdict(list)
    by_article_any_brand = defaultdict(list)
    for c in catalog:
        by_name[key_name(c['name'])].append(c)
        for a in article_candidates(c['name']):
            by_article_any_brand[a].append(c)
            for b in brand_variants(c['brand']):
                by_article[(b, a)].append(c)

    renames, unchanged, ambiguous, not_in_catalog = [], [], [], []
    for p in price_rows:
        hits = by_name.get(key_name(p['name']), [])
        how = 'по имени'
        if not hits:
            for b in brand_variants(p['brand']):
                for a in article_candidates(p['name']):
                    hits = by_article.get((b, a), [])
                    if hits:
                        break
                if hits:
                    break
            how = 'по артикулу'
        if not hits:
            # Бренд в каталоге и в прайсе может называться по-разному
            # (КОРЕЯ против WELLA у филлера). Если артикул уникален на весь
            # каталог, бренд для опознания не нужен.
            for a in article_candidates(p['name']):
                cand = by_article_any_brand.get(a, [])
                if len(cand) == 1:
                    hits = cand
                    how = 'по артикулу (бренд не совпал)'
                    break
        if not hits:
            not_in_catalog.append(p)
            continue
        if len({key_name(h['name']) for h in hits}) > 1:
            best = pick_closest(p['name'], hits)
            if best is None:
                ambiguous.append((p, hits))
                continue
            hits = [best]
            how += ', ничья снята по имени'
        new_name = hits[0]['name']
        if new_name == p['name']:
            unchanged.append(p)
        else:
            renames.append((p, new_name, how))

    print()
    print(f'  имя уже правильное:        {len(unchanged):>5}')
    print(f'  будет переименовано:       {len(renames):>5}')
    print(f'  двусмысленно (не трогаем): {len(ambiguous):>5}')
    print(f'  нет в каталоге (новинки):  {len(not_in_catalog):>5}')

    if renames:
        print('\nПРИМЕРЫ ПЕРЕИМЕНОВАНИЙ (первые 15):')
        for p, new, how in renames[:15]:
            print(f'  стр.{p["row"]:<5} {how}')
            print(f'      было:  {p["name"][:76]}')
            print(f'      стало: {new[:76]}')

    if ambiguous:
        print('\nДВУСМЫСЛЕННЫЕ — решать человеку, скрипт их не трогает:')
        for p, hits in ambiguous:
            print(f'  стр.{p["row"]:<5} {p["name"][:64]}')
            for h in hits[:3]:
                print(f'        -> каталог стр.{h["row"]}: {h["name"][:62]}')

    if not_in_catalog:
        print('\nНЕТ В КАТАЛОГЕ — имя останется как в 1С, впиши его в каталог:')
        for p in not_in_catalog:
            print(f'  {p["brand"]:<12} {p["name"][:70]}')

        lines = ['# Товары, которых нет в `Каталог.xlsx`', '',
                 'Их имена остались такими, как пришли из 1С.',
                 'Допиши их в каталог — и следующее обновление подхватит.', '']
        for p in sorted(not_in_catalog, key=lambda x: (x['brand'], x['name'])):
            lines.append(f'- **{p["brand"]}** — `{p["name"]}`')
        NEW_NAMES_REPORT.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        print(f'\n  список записан: {NEW_NAMES_REPORT.name}')

    if not renames:
        print('\nПереименовывать нечего.')
        return

    if apply:
        for p, new, _ in renames:
            ws.cell(row=p['row'], column=2).value = new
        wb.save(PRICE_XLSX)
        print(f'\nЗаписано в {PRICE_XLSX.name}: {len(renames)} имён.')
        print('Дальше по ритуалу: xlsx-to-price-items.py -> '
              'migrate-renamed-products.py -> verify-price-sync.py')
    else:
        print('\nЭто предпросмотр, файл не изменён. Для записи — с --apply')


if __name__ == '__main__':
    main()
