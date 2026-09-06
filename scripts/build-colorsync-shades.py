# -*- coding: utf-8 -*-
"""
Собирает src/data/matrix-sync-shades.json — данные интерактивной палитры Color Sync.

Берёт вырезанные фото-свотчи (scripts/_colorsync-raw.json от extract-colorsync-swatches.py)
и сопоставляет коды оттенков с реальным прайсом по имени товара в 1С.

Сопоставление ТОЛЬКО точное, по коду в начале названия. Никаких «похожих» совпадений:
подставить цену не того оттенка хуже, чем не подставить никакой — человек закажет не то.
Оттенки без совпадения остаются в палитре с фото, но без цены и без кнопки заказа.

Запуск: .venv/Scripts/python.exe scripts/build-colorsync-shades.py
"""
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW = ROOT / 'scripts' / '_colorsync-raw.json'
PRICE = ROOT / 'src' / 'data' / 'priceItems.json'
OUT = ROOT / 'src' / 'data' / 'matrix-sync-shades.json'

# Порядок панелей на официальной карте прядей — он же порядок групп в палитре.
# Кислотная технология сюда НЕ входит: в прайсе Zilma кислотные тонеры — это уже
# другой, обновлённый набор оттенков (Tonal Control), и старая карта им не соответствует.
GROUPS = ['Натуральные', 'Холодные', 'Тёплые', 'Мокка', 'Коричневые',
          'Бронзовые', 'Пауэр Кулс', 'Яркие', 'Прозрачный']


def depth_key(code: str):
    """Сортировка внутри группы: сначала по глубине тона, потом по буквам.

    Пастельные SP-оттенки и CLEAR глубины не имеют — отправляем их в конец группы.
    """
    m = re.match(r'^(\d{1,2})([A-Z+]*)$', code)
    if m:
        return (int(m.group(1)), m.group(2))
    return (99, code)


def main() -> None:
    raw = json.loads(RAW.read_text(encoding='utf-8'))
    price = json.loads(PRICE.read_text(encoding='utf-8'))

    # индекс прайса: код оттенка -> товар
    by_code = {}
    for item in price:
        m = re.match(r'^Color Sync\s+(\d{1,2}[A-Z+]*|SP[A-Z]|CLEAR|HD-[A-Z]{2})(\s|$)', item['name'])
        if m:
            by_code[m.group(1)] = item

    shades = []
    for code, info in raw.items():
        if code.startswith('ac:'):        # кислотная технология — см. комментарий к GROUPS
            continue
        entry = {
            'code': code,
            'hex': info['hex'],
            'group': info['panel'],
            'row': 0,
            'col': 0,
            'image': f"/images/shades/matrix-sync/{info['file']}",
        }
        match = by_code.get(code)
        if match:
            entry['name'] = match['name']
            entry['price'] = match['price']
        shades.append(entry)

    shades.sort(key=lambda s: (GROUPS.index(s['group']), depth_key(s['code'])))
    counters = {}
    for s in shades:
        g = s['group']
        s['col'] = counters.get(g, 0)
        counters[g] = s['col'] + 1

    OUT.write_text(json.dumps(shades, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')

    matched = sum(1 for s in shades if 'name' in s)
    print(f'оттенков в палитре: {len(shades)}')
    print(f'сматчено с прайсом: {matched}')
    print(f'без совпадения:     {len(shades) - matched}')
    print()
    for g in GROUPS:
        items = [s for s in shades if s['group'] == g]
        if items:
            m = sum(1 for s in items if 'name' in s)
            print(f'  {g:<14} {len(items):>2} шт., в прайсе {m:>2}: '
                  + ', '.join(s['code'] for s in items))

    # Что есть в прайсе, но чего нет на карте прядей — это новые оттенки линии.
    extra = sorted(set(by_code) - {s['code'] for s in shades})
    print(f'\nв прайсе есть, на карте прядей НЕТ ({len(extra)}):')
    print('  ' + ', '.join(extra))


if __name__ == '__main__':
    main()
