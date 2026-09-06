# -*- coding: utf-8 -*-
"""
Собирает палитру Matrix Super Sync: src/data/matrix-sync-shades.json + фото-свотчи.

Два источника, и порядок между ними важен:

1. ОСНОВНОЙ — актуальная официальная палитра Super Sync с matrix.ru
   (scripts/_supersync-official.txt + скачанные фото в scripts/_ss-raw/).
   Super Sync — это реновация SoColor Sync, у неё свой, обновлённый набор оттенков
   и своя группировка по отражениям.

2. ЗАПАСНОЙ — старая карта прядей SoColor Sync (scripts/_colorsync-raw.json).
   Нужна только для оттенков, которые ЕСТЬ В ПРАЙСЕ Zilma, но которых уже нет
   в новой палитре бренда: у остатков на складе покупатель всё равно должен
   видеть цвет. Такие оттенки помечаются группой «Прежняя палитра».

Коды в прайсе и на сайте бренда пишутся по-разному: 6RC+ против 6RC, HD-RR против HDRR.
Сопоставление идёт по нормализованному коду (без плюсов и дефисов), а в палитре
показывается тот вариант, который написан в прайсе — по нему мастер и ищет.

Запуск: .venv/Scripts/python.exe scripts/build-supersync-shades.py
"""
import json
import pathlib
import re

import numpy as np
from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / 'scripts'
OFFICIAL = SCRIPTS / '_supersync-official.txt'
RAW_DIR = SCRIPTS / '_ss-raw'
OLD_RAW = SCRIPTS / '_colorsync-raw.json'
OLD_DIR = ROOT / 'public' / 'images' / 'shades' / 'matrix-sync'
OUT_IMG = ROOT / 'public' / 'images' / 'shades' / 'matrix-sync'
OUT_JSON = ROOT / 'src' / 'data' / 'matrix-sync-shades.json'
PRICE = ROOT / 'src' / 'data' / 'priceItems.json'

# Порядок групп — как на официальной странице: от холодных к тёплым, служебные в конце.
GROUP_ORDER = [
    'Натуральный', 'Глубокий натуральный', 'Глубокий натуральный золотистый',
    'Глубокий натуральный пепельный', 'Натуральный пепельный', 'Теплый натуральный',
    'Натуральный красный', 'Пепельный', 'Пепельно-золотистый', 'Перламутровый',
    'Перламутрово-золотистый', 'Золотисто-перламутровый', 'Золотистый перламутровый',
    'Жемчужный', 'Глубокий перламутровый', 'Мокка', 'Мокка мокка', 'Золотистый',
    'Медный золотистый', 'Глубокий медный', 'Коричнево-медный', 'Коричнево-красный',
    'Красно-медный', 'Красно-перламутровый+', 'Глубокий красный', 'Яркие оттенки',
    'Silver living', 'Прозрачный оттенок', 'Прежняя палитра',
]


def norm(code: str) -> str:
    """Код без плюсов и дефисов — общий знаменатель для прайса и сайта бренда."""
    return re.sub(r'[^A-Z0-9]', '', code.upper())


def depth_key(code: str):
    m = re.match(r'^(\d{1,2})', code)
    return (int(m.group(1)) if m else 99, code)


def circle_crop(path: pathlib.Path) -> Image.Image:
    """Приводит свотч к квадрату 160×160 на белом фоне.

    У части файлов прозрачный фон (RGBA): без подложки он станет чёрным при
    сохранении в webp, и светлые блонды превратятся в тёмные пятна.
    """
    im = Image.open(path)
    if im.mode in ('RGBA', 'LA', 'P'):
        im = im.convert('RGBA')
        bg = Image.new('RGBA', im.size, (255, 255, 255, 255))
        im = Image.alpha_composite(bg, im)
    return im.convert('RGB').resize((160, 160), Image.LANCZOS)


def main() -> None:
    OUT_IMG.mkdir(parents=True, exist_ok=True)
    price = json.loads(PRICE.read_text(encoding='utf-8'))

    # прайс: нормализованный код -> товар
    by_code = {}
    for item in price:
        m = re.match(r'^Color Sync\s+(\d{1,2}[A-Z+]*|SP[A-Z]|CLEAR|HD-[A-Z]{2})(\s|$)', item['name'])
        if m:
            by_code[norm(m.group(1))] = (m.group(1), item)

    shades, used = [], set()

    # --- источник 1: актуальная палитра бренда
    for line in OFFICIAL.read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        code, group, path = line.split('|')
        ext = path.rsplit('.', 1)[-1]
        src = RAW_DIR / (code.lower().replace('+', '_') + '.' + ext)
        if not src.exists():
            print('нет файла свотча:', src.name)
            continue
        fname = f'ss-{norm(code).lower()}.webp'
        circle_crop(src).save(OUT_IMG / fname, 'WEBP', quality=88, method=6)

        n = norm(code)
        entry = {'code': code, 'group': group, 'row': 0, 'col': 0,
                 'image': f'/images/shades/matrix-sync/{fname}'}
        arr = np.asarray(circle_crop(src)).reshape(-1, 3)
        entry['hex'] = '#%02x%02x%02x' % tuple(int(v) for v in np.median(arr, axis=0))
        if n in by_code:
            price_code, item = by_code[n]
            entry['code'] = price_code          # показываем код так, как он в прайсе
            entry['name'] = item['name']
            entry['price'] = item['price']
            used.add(n)
        shades.append(entry)

    # --- источник 2: старая карта, только для того, что есть в прайсе и потерялось
    old = json.loads(OLD_RAW.read_text(encoding='utf-8'))
    for code, info in old.items():
        if code.startswith('ac:'):
            continue
        n = norm(code)
        if n in used or n not in by_code:
            continue
        price_code, item = by_code[n]
        shades.append({
            'code': price_code,
            'group': 'Прежняя палитра',
            'row': 0, 'col': 0,
            'hex': info['hex'],
            'image': f"/images/shades/matrix-sync/{info['file']}",
            'name': item['name'],
            'price': item['price'],
        })
        used.add(n)

    order = {g: i for i, g in enumerate(GROUP_ORDER)}
    shades.sort(key=lambda s: (order.get(s['group'], 99), depth_key(s['code'])))
    counters = {}
    for s in shades:
        g = s['group']
        s['col'] = counters.get(g, 0)
        counters[g] = s['col'] + 1

    OUT_JSON.write_text(json.dumps(shades, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')

    matched = sum(1 for s in shades if 'name' in s)
    print(f'оттенков в палитре: {len(shades)}')
    print(f'из них с ценой:     {matched}')
    missing = sorted(c for n, (c, _) in by_code.items() if n not in used)
    print(f'\nв прайсе, но без свотча ({len(missing)}): {", ".join(missing) or "—"}')
    for g in GROUP_ORDER:
        items = [s for s in shades if s['group'] == g]
        if items:
            m = sum(1 for s in items if 'name' in s)
            print(f'  {g:<32} {len(items):>2} шт., в прайсе {m:>2}')


if __name__ == '__main__':
    main()
