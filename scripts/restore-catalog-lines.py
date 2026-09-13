# -*- coding: utf-8 -*-
"""
Возвращает в Price/Каталог.xlsx названия линеек, потерянные при ручной правке.

ЗАЧЕМ. Причёсывая имена, пользователь срезал приставки-линейки: «ST Soft Care
Кондиционер...» стал просто «Кондиционер...». Имя читается лучше, но клиент,
который знает свою линейку и ищет «Soft Care», не находит ничего. Линейка —
не мусор из 1С, а часть того, как товар называют в салоне.

КАК. Берём имя из прайса (там линейка цела), берём имя из каталога, находим
ведущие слова прайсового имени, которых в каталожном нет, и возвращаем их
на место. Идём слева направо и останавливаемся на первом слове, которое в
каталожном имени есть, — дальше начинается общая часть.

ЧЕГО НЕ ДЕЛАЕМ САМИ. Если потерянное слово частично совпадает с оставшимся
(«Цера-бальзам» против «Бальзам»), приставка сплавлена со словом, и
механическая склейка дала бы «Цера-бальзам Бальзам». Такие случаи скрипт
не трогает, а выписывает списком — решать человеку.

ГАРАНТИЯ ТА ЖЕ: последнее слово имени (артикул) не трогается.

Запуск: python scripts/restore-catalog-lines.py [--apply]
"""
import json
import re
import shutil
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))

import importlib.util
_spec = importlib.util.spec_from_file_location(
    'acn', ROOT / 'scripts' / 'apply-catalog-names.py')
acn = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(acn)

CATALOG = acn.CATALOG


def norm(s):
    return re.sub(r'\s+', ' ', str(s).strip())


def wordset(name):
    return {w.casefold() for w in re.findall(r'[0-9A-Za-zА-Яа-яЁё]+', name)}


# Название линейки пишется латиницей («ST Soft Care», «BEAUTY curls») либо
# капсом. Обычное русское слово в начале — это не линейка, а расшифрованное
# сокращение («Ср-во» -> «Средство») или переставленное слово («кератин
# бальзам» -> «Бальзам с кератином»). Такие приставки возвращать нельзя.
LINE_TOKEN = re.compile(r"^[A-Za-z][A-Za-z0-9\-+&'\.]*$")


def is_line_token(t):
    if LINE_TOKEN.match(t):
        return True
    letters = [c for c in t if c.isalpha()]
    return len(letters) >= 2 and all(c.isupper() for c in letters)


def lost_prefix(price_name, cat_name):
    """Ведущие слова прайсового имени, которых нет в каталожном.

    Возвращает (приставка, надёжно_ли). Ненадёжно — когда потерянное слово
    содержит внутри себя слово из каталожного имени: значит приставка сплавлена
    («Цера-бальзам»), и приклеивать её нельзя.
    """
    cat_words = wordset(cat_name)
    toks = norm(price_name).split()
    taken = []
    for t in toks:
        parts = {w.casefold() for w in re.findall(r'[0-9A-Za-zА-Яа-яЁё]+', t)}
        if parts & cat_words:
            break
        taken.append(t)
    if not taken or len(taken) >= len(toks) - 1 or len(taken) > 3:
        return '', True
    if not all(is_line_token(t) for t in taken):
        return '', True          # не линейка — молча пропускаем
    fused = any(
        any(cw in t.casefold() and cw != t.casefold() for cw in cat_words if len(cw) > 3)
        for t in taken)
    return ' '.join(taken), not fused


def main():
    apply = '--apply' in sys.argv

    catalog = acn.read_catalog()
    known = {i['brand'].upper()
             for i in json.loads(acn.PRICE_ITEMS.read_text(encoding='utf-8'))}
    _wb, _ws, price = acn.read_price_rows(known)

    by_name, by_art, by_any = defaultdict(list), defaultdict(list), defaultdict(list)
    for c in catalog:
        by_name[acn.key_name(c['name'])].append(c)
        for a in acn.article_candidates(c['name']):
            by_any[a].append(c)
            for b in acn.brand_variants(c['brand']):
                by_art[(b, a)].append(c)

    def resolve(p):
        hits = by_name.get(acn.key_name(p['name']), [])
        if not hits:
            for b in acn.brand_variants(p['brand']):
                for a in acn.article_candidates(p['name']):
                    hits = by_art.get((b, a), [])
                    if hits:
                        break
                if hits:
                    break
        if not hits:
            for a in acn.article_candidates(p['name']):
                cand = by_any.get(a, [])
                if len(cand) == 1:
                    hits = cand
                    break
        if hits and len({acn.key_name(h['name']) for h in hits}) > 1:
            best = acn.pick_closest(p['name'], hits)
            hits = [best] if best else []
        return hits[0] if hits else None

    fixes, manual = [], []
    for p in price:
        c = resolve(p)
        if not c:
            continue
        prefix, safe = lost_prefix(p['name'], c['name'])
        if not prefix:
            continue
        if not safe:
            manual.append((c, p['name'], prefix))
            continue
        new = f"{prefix} {c['name']}"
        if new.split()[-1] != c['name'].split()[-1]:
            manual.append((c, p['name'], prefix))
            continue
        fixes.append((c, new, p['name']))

    print(f'Вернуть линейку: {len(fixes)}')
    for c, new, old_price in fixes:
        print(f'  стр.{c["row"]:<5} {c["brand"]}')
        print(f'      в прайсе:  {old_price[:74]}')
        print(f'      сейчас:    {c["name"][:74]}')
        print(f'      станет:    {new[:74]}')

    if manual:
        print(f'\nРУЧНОЕ РЕШЕНИЕ — приставка сплавлена со словом ({len(manual)}):')
        for c, old_price, prefix in manual:
            print(f'  стр.{c["row"]:<5} потеряно «{prefix}»')
            print(f'      в прайсе: {old_price[:74]}')
            print(f'      сейчас:   {c["name"][:74]}')

    if not fixes:
        return

    names = [c['name'] for c in catalog]
    after = set()
    for n in names:
        after.add(n.casefold())
    for c, new, _ in fixes:
        after.discard(c['name'].casefold())
        after.add(new.casefold())
    print(f'\nПРОВЕРКА: имён {len(names)}, различных после правки {len(after)}'
          f'  ({"ок" if len(after) == len(names) else "ДУБЛИ!"})')
    if len(after) != len(names):
        sys.exit('Проверка не прошла — ничего не записано.')

    if apply:
        wb = openpyxl.load_workbook(CATALOG)
        ws = wb['Sheet1']
        backup = CATALOG.with_name(f'Каталог-до-линеек-{date.today():%Y-%m-%d}.xlsx')
        if not backup.exists():
            shutil.copy2(CATALOG, backup)
        for c, new, _ in fixes:
            ws.cell(row=c['row'], column=2).value = new
        wb.save(CATALOG)
        print(f'\nЗаписано: {len(fixes)}. Копия: {backup.name}')
    else:
        print('\nЭто предпросмотр. Для записи — с --apply')


if __name__ == '__main__':
    main()
