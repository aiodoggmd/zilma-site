#!/usr/bin/env python3
"""
Достаёт товарные фото из архива старого сайта (D:\\Work\\Инет) и раскладывает их
под текущий прайс.

Как это работает и почему именно так:

1. Имя файла в архиве = номерной артикул, который стоит в названии товара в прайсе
   (проверено на живых совпадениях: «...CARE WORKS CMC 500 мл. 3372» -> 3372.psd,
   «Блондирующий крем масленный 7+ 200 мл 6289/x9225» -> 6289.psd). Поэтому ищем
   в названии ВСЕ числовые токены, а не только последний: у части позиций артикул
   стоит в середине, а хвост — составной («4765/10559», первая часть актуальная).

2. Водяной знак MILENACLUB.RU лежит в PSD ОТДЕЛЬНЫМ слоем (широкая тонкая полоса
   ~490x50, у всех проверенных файлов это «Слой 1»). Поэтому чистое фото получается
   простым отключением этого слоя и пересборкой композита — без ретуши, без замазывания
   и без потери качества. Голый JPG берём только если PSD нет (тогда знак остаётся,
   такие файлы скрипт помечает и НЕ сохраняет — лучше без фото, чем с чужим логотипом).

3. Фон у всех кадров белый, товар по центру. Обрезаем по реальным границам товара и
   кладём на квадратный белый холст с полем — иначе в списке товары «прыгают» по размеру.

Запуск:
    .venv/Scripts/python.exe scripts/extract-archive-photos.py [--limit N] [--dry-run]

Результат:
    public/images/products/<бренд>-<артикул>.webp
    src/data/product-photos.json   — журнал «артикул товара -> файл», по нему сайт
                                     и подставляет фото; пересобирается при каждом прогоне.
"""
import argparse
import collections
import json
import os
import re
import sys

from PIL import Image
from psd_tools import PSDImage

ARCHIVE = r'D:\Work\Инет'
SITE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRICE = os.path.join(SITE, 'src', 'data', 'priceItems.json')
OUT_DIR = os.path.join(SITE, 'public', 'images', 'products')
JOURNAL = os.path.join(SITE, 'src', 'data', 'product-photos.json')

# Папка архива на бренд прайса. Схема старого магазина шире нынешнего прайса
# (75 папок), поэтому связь задана явно, а не угадывается по имени.
BRAND_FOLDERS = {
    'WELLA': ['Wella', 'Wella_SP'],
    'LONDA': ['Londa'],
    'SCHWARZKOPF': ['Schwarzkopf'],
    'MATRIX': ['Matrix'],
    'LEBEL': ['Lebel'],
    'OLLIN': ['Ollin'],
    'KAPOUS': ['Kapous'],
    'CONCEPT': ['Concept'],
    'ESTEL': ['Estel'],
    'DIKSON': ['Dikson'],
    "L'OREAL": ['LOreal'],
    'CAREPROST': ['Careprost'],
    'REFECTOCIL': ['Refectocil'],
    'ОДНОРАЗОВАЯ ПРОДУКЦИЯ': ['Одноразка'],
}

CANVAS = 400          # итоговый квадрат
MARGIN = 0.06         # поле вокруг товара, доля от холста
WEBP_QUALITY = 86
WHITE_CUTOFF = 246    # пиксель светлее — считаем фоном


def slug(text: str) -> str:
    """Латиница/цифры в kebab-case для имени файла."""
    table = str.maketrans({'/': '-', '\\': '-', ' ': '-', '.': '-', ',': '-', "'": '', '"': ''})
    s = text.lower().translate(table)
    s = re.sub(r'[^a-z0-9\-]', '', s)
    return re.sub(r'-+', '-', s).strip('-')


def code_variants(token: str) -> set:
    """
    Написания одного артикула: как есть и без ведущих нулей (в архиве «0178»,
    в прайсе то же число могло попасть как «178»).
    """
    t = token.strip().lower()
    if not t.isdigit():          # «0-56», «01-607» — не артикул, ноль не срезаем
        return {t} if t else set()
    return {v for v in (t, t.lstrip('0') or '0') if v}


def codes_in_name(name: str) -> list:
    """
    Артикулы из названия товара.

    Только целые числа из 3-10 цифр, ОТДЕЛЬНЫМ токеном (границы (?<!\\d)/(?!\\d)).
    Без границ регэксп вырывал кусок из середины: «бальзам-маска ... 3026/18»
    читалось как код «026-18» и подтягивало чужое фото (реальный промах, поймано
    сверкой картинки с названием). Коды оттенков (6-16, 10/05) намеренно НЕ ищем:
    они дают единицы совпадений и много ложных, а у красителей и так есть кружок
    реального цвета — показать не тот флакон хуже, чем не показать никакого.
    """
    return re.findall(r'(?<!\d)\d{3,10}(?!\d)', name)


def family_key(name: str) -> str:
    """
    Название без объёма/веса и без артикула — «семейство» товара.
    «Шампунь FIBER INFUSION 250 мл 5084» и «... 1000 мл 5085» дают один ключ,
    значит им подойдёт одно и то же фото.
    """
    n = re.sub(r'(?<!\d)\d{3,10}(?!\d)\.?\s*$', '', name.strip())      # хвостовой артикул
    n = re.sub(r'\b\d+[.,]?\d*\s*(мл|л|гр|г|шт|мг|ml|kg|кг)\b', ' ', n, flags=re.I)
    n = re.sub(r'[^\w\s]', ' ', n)
    return re.sub(r'\s+', ' ', n).strip().lower()


def build_index(folders):
    """код -> {'psd': путь, 'jpg': путь}"""
    idx = collections.defaultdict(dict)
    for folder in folders:
        d = os.path.join(ARCHIVE, folder)
        if not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            base, ext = os.path.splitext(fn)
            ext = ext.lower()
            if ext not in ('.psd', '.jpg', '.jpeg', '.png'):
                continue
            kind = 'psd' if ext == '.psd' else 'jpg'
            code = base.replace(' копия', '').strip()
            for key in code_variants(code):
                idx[key].setdefault(kind, os.path.join(d, fn))
    return idx


def render_clean(psd_path: str):
    """Композит PSD без слоя водяного знака."""
    psd = PSDImage.open(psd_path)
    removed = []
    for layer in psd:
        if not layer.visible:
            continue
        w, h = layer.size
        # знак — широкая и очень низкая полоса; товар такой формы не бывает
        if h and w and h <= 70 and w >= psd.width * 0.6:
            layer.visible = False
            removed.append(layer.name)
    if not removed:
        return None, removed            # знак не нашёлся — не рискуем
    img = psd.composite(force=True)
    return img.convert('RGB'), removed


def fit_square(img: Image.Image) -> Image.Image:
    """Обрезать по товару и положить по центру белого квадрата."""
    gray = img.convert('L')
    mask = gray.point(lambda p: 255 if p < WHITE_CUTOFF else 0)
    box = mask.getbbox()
    if box:
        img = img.crop(box)
    inner = int(CANVAS * (1 - 2 * MARGIN))
    w, h = img.size
    scale = min(inner / w, inner / h)
    img = img.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)
    canvas = Image.new('RGB', (CANVAS, CANVAS), 'white')
    canvas.paste(img, ((CANVAS - img.width) // 2, (CANVAS - img.height) // 2))
    return canvas


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=0, help='обработать не больше N товаров')
    ap.add_argument('--dry-run', action='store_true', help='только посчитать, ничего не писать')
    args = ap.parse_args()

    items = json.load(open(PRICE, encoding='utf-8'))
    os.makedirs(OUT_DIR, exist_ok=True)

    journal = {}
    stats = collections.Counter()
    skipped_jpg_only = []
    done_files = {}

    for brand, folders in BRAND_FOLDERS.items():
        idx = build_index(folders)
        if not idx:
            continue
        for it in items:
            if it['brand'].upper() != brand:
                continue
            if args.limit and stats['saved'] >= args.limit:
                break

            hit = None
            for code in codes_in_name(it['name']):
                for key in code_variants(code):
                    if key in idx:
                        hit = (code, idx[key])
                        break
                if hit:
                    break
            if not hit:
                stats['без фото'] += 1
                continue

            code, rec = hit
            if 'psd' not in rec:
                skipped_jpg_only.append((it['name'], rec.get('jpg')))
                stats['только jpg — пропущено'] += 1
                continue

            name = f'{slug(brand)}-{slug(code)}.webp'
            dst = os.path.join(OUT_DIR, name)
            journal[it['name']] = f'/images/products/{name}'
            stats['saved'] += 1

            if args.dry_run or dst in done_files:
                continue
            try:
                img, removed = render_clean(rec['psd'])
                if img is None:
                    stats['знак не найден — пропущено'] += 1
                    del journal[it['name']]
                    stats['saved'] -= 1
                    continue
                fit_square(img).save(dst, 'WEBP', quality=WEBP_QUALITY, method=6)
                done_files[dst] = True
            except Exception as exc:                        # noqa: BLE001
                stats['ошибка чтения psd'] += 1
                journal.pop(it['name'], None)
                stats['saved'] -= 1
                print(f'  ! {os.path.basename(rec["psd"])}: {type(exc).__name__} {exc}')

    # Второй проход: один снимок — на все объёмы одного товара (идея пользователя).
    # В прайсе «Шампунь FIBER INFUSION 250 мл 5084» и тот же шампунь на 1000 мл — разные
    # позиции с разными артикулами, но это один и тот же флакон, и на архивном фото часто
    # сняты сразу оба размера. Поэтому если у товара своего фото нет, а у его «родственника»
    # (тот же бренд, то же название без объёма и артикула) есть — берём его.
    shared = 0
    by_family = collections.defaultdict(list)
    for it in items:
        by_family[(it['brand'].upper(), family_key(it['name']))].append(it)
    for group in by_family.values():
        donor = next((journal[i['name']] for i in group if i['name'] in journal), None)
        if not donor:
            continue
        for i in group:
            if i['name'] not in journal:
                journal[i['name']] = donor
                shared += 1

    if not args.dry_run:
        with open(JOURNAL, 'w', encoding='utf-8') as fh:
            json.dump(journal, fh, ensure_ascii=False, indent=2, sort_keys=True)

    print()
    print(f'товаров с фото : {len(journal)}  (своё фото: {stats["saved"]}, по другому объёму: {shared})')
    print(f'файлов создано : {len(done_files)}')
    print(f'без совпадения : {stats["без фото"]}')
    for k in ('только jpg — пропущено', 'знак не найден — пропущено', 'ошибка чтения psd'):
        if stats[k]:
            print(f'{k}: {stats[k]}')
    if skipped_jpg_only:
        print('\nбез PSD (остались бы с чужим водяным знаком, поэтому не берём):')
        for n, p in skipped_jpg_only[:10]:
            print(f'  {n[:60]}  <- {os.path.basename(p or "")}')
    if not args.dry_run:
        print(f'\nжурнал: {os.path.relpath(JOURNAL, SITE)}')
        print(f'файлы : {os.path.relpath(OUT_DIR, SITE)}')


if __name__ == '__main__':
    sys.exit(main())
