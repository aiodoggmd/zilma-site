# -*- coding: utf-8 -*-
"""
Привязывает оттенки палитр к товарам прайса по КОДУ ОТТЕНКА внутри раздела.

ЗАЧЕМ. resolve-live-price.ts берёт артикул товара из ИМЕНИ оттенка. У оттенка,
которого в прайсе никогда не было, имени нет — значит нет и артикула, и когда
товар появляется в продаже, палитра этого не замечает никогда. Ограничение
честно описано в самом резолвере; этот скрипт его закрывает.

ПОЧЕМУ НЕ ВЫВЕСТИ АРТИКУЛ ИЗ КОДА. Пробовали, замерили — правило у каждой
линейки своё и часто нерегулярное:
    Koleston     9/04 -> 9-04        Color Touch  9/0  -> ct9-0
    Igora Royal  9-0  -> и90         Londa Demi   10/0 -> 0-10
    Materia G    A-6  -> 0092  (связи с кодом нет вовсе)
Общего правила не существует, поэтому ищем не артикул, а сам КОД внутри имени
товара — так, как его читает человек: «Краска колестон 4/07 Сакура 60мл 4-07».

ПОЧЕМУ ИСКАТЬ ВНУТРИ РАЗДЕЛА, А НЕ ПО ВСЕМУ БРЕНДУ. Это и есть главное правило
проекта: у WELLA код 8/38 есть и у Illumina, и у Shinefinity, а это разные
краски, смешивать их нельзя. Раньше такие случаи приходилось отбрасывать как
неоднозначные. После разбивки каталога по разделам Illumina и Shinefinity лежат
в РАЗНЫХ разделах, поэтому столкновения просто не возникает — правило соблюдено
структурой, а не оговоркой. Замер на всех палитрах: 0 неоднозначных совпадений.

ЧТО ДЕЛАЕТ. Дописывает оттенку `name` (и `price`) найденного товара. Дальше всё
идёт как раньше: resolve-live-price.ts на каждой сборке пересчитывает цену по
артикулу из этого имени. Скрипт идемпотентен — повторный прогон ничего не меняет.

МЕСТО В РИТУАЛЕ: после xlsx-to-price-items.py, перед сборкой сайта.

Запуск: python scripts/link-palette-shades.py [--apply]
"""
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'src' / 'data'
PRICE_ITEMS = DATA / 'priceItems.json'

# Токены имени, похожие на код оттенка: «4/07», «9-0», «UL-M», «8T», «A-6».
# Хвостовой «+» — ЧАСТЬ КОДА, а не украшение: у Matrix Socolor «UL-N» и «UL-N+» —
# два разных оттенка. Без него разбор обрубал «UL-N+» до «UL-N» и привязывал
# отсутствующий в прайсе оттенок к чужому товару (поймано на проверке 14.09.2026).
CODE_TOKEN_RE = re.compile(
    r'\b\d{1,3}[/\-.]\d{1,3}\+?|\b[A-Za-zА-Яа-я]{1,3}-?\d{1,3}\+?|\b[A-Z]{2,3}-[A-Z]{1,3}\+?')


def norm_code(c) -> str:
    """Код без разделителей и регистра: «9/04», «9-04», «904» — одно и то же."""
    return re.sub(r'[/\-.\s]', '', str(c)).upper()


def codes_in(name: str):
    return {norm_code(t) for t in CODE_TOKEN_RE.findall(name)}


def palette_files():
    return sorted(DATA.glob('*-shades.json'))


def main() -> None:
    apply = '--apply' in sys.argv
    items = json.loads(PRICE_ITEMS.read_text(encoding='utf-8'))

    by_section = defaultdict(list)
    for i in items:
        by_section[(i.get('brand'), i.get('section'))].append(i)

    # Раздел каждой палитры определяем по товарам, которые в ней УЖЕ подписаны —
    # так карта не нуждается в ручном ведении и не разъезжается с каталогом.
    name_to_section = {i['name']: (i.get('brand'), i.get('section')) for i in items}
    pal_section, claims = {}, Counter()
    for f in palette_files():
        shades = json.loads(f.read_text(encoding='utf-8'))
        if not isinstance(shades, list):
            continue
        votes = Counter()
        for s in shades:
            key = name_to_section.get(s.get('name') or '')
            if key and key[1]:
                votes[key] += 1
        if votes:
            pal_section[f.name] = votes.most_common(1)[0][0]
            claims[votes.most_common(1)[0][0]] += 1

    # Один раздел на две палитры — различить линейки нечем, обе пропускаем.
    # Сейчас это LONDA «Безаммиачный краситель»: туда попадают и Color Tune,
    # и Londa Demi. Разведёт их только правка разделов в Price/Каталог.xlsx.
    shared = {k for k, n in claims.items() if n > 1}

    total_nameless = total_linked = total_amb = 0
    changes = []
    skipped = []

    print(f"{'палитра':<34}{'без имени':>10}{'привяжется':>12}{'неоднозн.':>11}")
    print('-' * 68)
    for f in palette_files():
        shades = json.loads(f.read_text(encoding='utf-8'))
        if not isinstance(shades, list):
            continue
        key = pal_section.get(f.name)
        nameless = [s for s in shades if not s.get('name') and s.get('code')]
        if not key:
            if nameless:
                skipped.append((f.name, 'раздел не определён — нет ни одного подписанного оттенка'))
            continue
        if key in shared:
            skipped.append((f.name, f'раздел делят две палитры: {key[0]} / {key[1]}'))
            continue

        idx = defaultdict(list)
        for it in by_section[key]:
            for c in codes_in(it['name']):
                idx[c].append(it)

        linked = amb = 0
        for s in nameless:
            hits = idx.get(norm_code(s['code']), [])
            uniq = {h['id']: h for h in hits}
            if len(uniq) == 1:
                it = next(iter(uniq.values()))
                changes.append((f, s, it))
                linked += 1
            elif len(uniq) > 1:
                amb += 1
        total_nameless += len(nameless)
        total_linked += linked
        total_amb += amb
        print(f'{f.name:<34}{len(nameless):>10}{linked:>12}{amb:>11}')

    print('-' * 68)
    print(f"{'ИТОГО':<34}{total_nameless:>10}{total_linked:>12}{total_amb:>11}")

    if skipped:
        print('\nПРОПУЩЕНО:')
        for n, why in skipped:
            print(f'  {n:<34} {why}')

    if changes:
        print('\nЧТО ПРИВЯЖЕТСЯ:')
        for f, s, it in changes[:25]:
            print(f'  {f.name[:26]:<27} код {str(s["code"]):<10} -> {it["name"][:52]}')
        if len(changes) > 25:
            print(f'  ... и ещё {len(changes) - 25}')

    if not changes:
        print('\nПривязывать нечего — все оттенки, что есть в прайсе, уже подписаны.')
        return

    if apply:
        per_file = defaultdict(list)
        for f, s, it in changes:
            per_file[f].append((s, it))
        for f, pairs in per_file.items():
            shades = json.loads(f.read_text(encoding='utf-8'))
            by_code = {norm_code(x.get('code')): x for x in shades if x.get('code')}
            for s, it in pairs:
                target = by_code.get(norm_code(s['code']))
                if target is None or target.get('name'):
                    continue
                target['name'] = it['name']
                # Цена ЧИСЛОМ: в ShadeSwatchGrid поле объявлено price?: number,
                # и по нему же считается недоступность (s.price == null).
                # Строка сюда не ломает вид, но делает тип разнородным и
                # отравляет любое сравнение (поймано на ревью 14.09.2026).
                target['price'] = it['price']
            f.write_text(json.dumps(shades, ensure_ascii=False, indent=1) + '\n',
                         encoding='utf-8')
            print(f'  {f.name}: дописано {len(pairs)}')
        print(f'\nЗаписано в {len(per_file)} палитр, оттенков: {len(changes)}.')
    else:
        print('\nЭто предпросмотр, файлы не изменены. Для записи — с --apply')


if __name__ == '__main__':
    main()
