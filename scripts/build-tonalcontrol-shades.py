# -*- coding: utf-8 -*-
"""
Собирает палитру Matrix Tonal Control: src/data/matrix-tonal-control-shades.json + свотчи.

Источник один и он актуальный — официальная страница палитры бренда
(matrix.ru/palitra-krasok-dlya-volos/tonal-control): 38 оттенков, сгруппированных
по цвету тюбика. Старая «кислотная» страница карты прядей SoColor Sync для этой
линии не годится: там 12 кодов, с прайсом совпадают два.

Коды в прайсе идут с приставкой «0-» в артикуле (0-10AG), но сам оттенок пишется
без неё — сопоставляем по коду без приставки.

Запуск: .venv/Scripts/python.exe scripts/build-tonalcontrol-shades.py
"""
import json
import pathlib
import re

import numpy as np
from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parent.parent
LIST = ROOT / 'scripts' / '_tonalcontrol-official.txt'
RAW = ROOT / 'scripts' / '_tc-raw'
OUT_IMG = ROOT / 'public' / 'images' / 'shades' / 'matrix-tonal-control'
OUT_JSON = ROOT / 'src' / 'data' / 'matrix-tonal-control-shades.json'
PRICE = ROOT / 'src' / 'data' / 'priceItems.json'

# Порядок групп: сначала холодные (ими нейтрализуют), потом натуральные, потом тёплые.
# Это порядок работы колориста, а не порядок с сайта бренда — там группы идут вперемешку.
GROUP_ORDER = ['Голубые', 'Фиолетовые', 'Коричневые', 'Нефритовый',
               'Золотые', 'Розовые', 'Прозрачный']


def depth_key(code: str):
    m = re.match(r'^(\d{1,2})', code)
    return (int(m.group(1)) if m else 99, code)


def to_square(path: pathlib.Path) -> Image.Image:
    """160×160 на белой подложке: часть файлов с прозрачным фоном, иначе он станет чёрным."""
    im = Image.open(path)
    if im.mode in ('RGBA', 'LA', 'P'):
        im = im.convert('RGBA')
        bg = Image.new('RGBA', im.size, (255, 255, 255, 255))
        im = Image.alpha_composite(bg, im)
    return im.convert('RGB').resize((160, 160), Image.LANCZOS)


def main() -> None:
    OUT_IMG.mkdir(parents=True, exist_ok=True)
    price = json.loads(PRICE.read_text(encoding='utf-8'))

    by_code = {}
    for item in price:
        m = re.match(r'^Color Sync Тонер с Кислым Ph\s+(\S+)\s', item['name'])
        if m:
            by_code[m.group(1).upper()] = item

    shades = []
    for line in LIST.read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        code, group, path = line.split('|')
        ext = path.rsplit('.', 1)[-1]
        src = RAW / (code.lower() + '.' + ext)
        if not src.exists():
            print('нет свотча:', src.name)
            continue
        img = to_square(src)
        fname = f'tc-{code.lower()}.webp'
        img.save(OUT_IMG / fname, 'WEBP', quality=88, method=6)
        arr = np.asarray(img).reshape(-1, 3)
        entry = {
            'code': code,
            'group': group,
            'row': 0, 'col': 0,
            'hex': '#%02x%02x%02x' % tuple(int(v) for v in np.median(arr, axis=0)),
            'image': f'/images/shades/matrix-tonal-control/{fname}',
        }
        item = by_code.get(code)
        if item:
            entry['name'] = item['name']
            entry['price'] = item['price']
        shades.append(entry)

    shades.sort(key=lambda s: (GROUP_ORDER.index(s['group']), depth_key(s['code'])))
    counters = {}
    for s in shades:
        g = s['group']
        s['col'] = counters.get(g, 0)
        counters[g] = s['col'] + 1

    OUT_JSON.write_text(json.dumps(shades, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')

    matched = sum(1 for s in shades if 'name' in s)
    print(f'оттенков: {len(shades)} | с ценой: {matched}')
    missing = sorted(set(by_code) - {s['code'] for s in shades})
    print(f'в прайсе, но без свотча: {", ".join(missing) or "—"}')
    for g in GROUP_ORDER:
        items = [s for s in shades if s['group'] == g]
        m = sum(1 for s in items if 'name' in s)
        print(f'  {g:<12} {len(items):>2} шт., в прайсе {m:>2}: '
              + ', '.join(s['code'] for s in items))


if __name__ == '__main__':
    main()
