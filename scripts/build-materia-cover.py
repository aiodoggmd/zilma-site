# -*- coding: utf-8 -*-
"""
Обложка и товарные фото для статьи о Lebel MATERIA.

Источник — официальный сайт производителя (Takara Belmont / LebeL), страница серии
MATERIA. Берём именно оттуда, а не из поиска картинок: упаковка у бренда по регионам
отличается, и «похожее фото» легко оказывается другим рынком или прошлым дизайном.

  https://www.lebel-takara.com/products/series/materia/

Обложка по стандарту сайта: товар на белом, без градиента и текста (заголовок и так стоит
отдельным <h1> под обложкой). Высота товара ~590 из 630 px, сверху отступ — иначе при
наведении на карточку в ленте (она увеличивается) верхушка тубы выходит за рамку.

Запуск: .venv/Scripts/python.exe scripts/build-materia-cover.py
"""
import io
import pathlib
import urllib.request

from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / 'public/images/articles/2026-09-11-lebel-materia'
BASE = 'https://www.lebel-takara.com/cms/wp-content/uploads/2020/10/'
SOURCES = {
    'tube': 'c_materia.png',
    'oxy3': 'c_materia_oxyw_3.png',
    'oxy6': 'c_materia_oxyw_6.png',
}

W, H = 1200, 630


def fetch(name: str) -> Image.Image:
    req = urllib.request.Request(BASE + SOURCES[name], headers={'User-Agent': 'Mozilla/5.0'})
    data = urllib.request.urlopen(req, timeout=60).read()
    return Image.open(io.BytesIO(data)).convert('RGB')


def trim(img: Image.Image, pad: int = 4) -> Image.Image:
    """Обрезка по реальным границам товара: у официальных фото вокруг много белого поля,
    и без обрезки товар на обложке выглядит мелким."""
    import numpy as np
    a = np.asarray(img)
    mask = a.min(axis=2) < 244
    cols, rows = np.where(mask.any(axis=0))[0], np.where(mask.any(axis=1))[0]
    return img.crop((max(0, cols.min() - pad), max(0, rows.min() - pad),
                     min(img.width, cols.max() + pad), min(img.height, rows.max() + pad)))


def scaled(img: Image.Image, height: int) -> Image.Image:
    return img.resize((round(img.width * height / img.height), height), Image.LANCZOS)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tube, oxy3, oxy6 = (trim(fetch(n)) for n in ('tube', 'oxy3', 'oxy6'))

    # Композиция: туба краски крупнее, два оксиданта рядом — это и есть рабочая пара,
    # без второго состава краска не работает.
    parts = [scaled(tube, 560), scaled(oxy6, 470), scaled(oxy3, 470)]
    gap = 40
    total = sum(p.width for p in parts) + gap * (len(parts) - 1)
    cover = Image.new('RGB', (W, H), 'white')
    x = (W - total) // 2
    for p in parts:
        cover.paste(p, (x, 30 + (560 - p.height) // 2))
        x += p.width + gap
    cover.save(OUT_DIR / 'cover.webp', 'WEBP', quality=88, method=6)

    # Отдельные фото для тела статьи — на белом квадрате, чтобы не прыгали по высоте.
    for name, img, side in (('tube', tube, 700), ('oxy', None, 700)):
        if name == 'tube':
            canvas = Image.new('RGB', (side, side), 'white')
            p = scaled(img, int(side * 0.92))
            canvas.paste(p, ((side - p.width) // 2, (side - p.height) // 2))
        else:
            canvas = Image.new('RGB', (side, side), 'white')
            a, b = scaled(oxy3, int(side * 0.8)), scaled(oxy6, int(side * 0.8))
            w = a.width + b.width + 30
            canvas.paste(a, ((side - w) // 2, (side - a.height) // 2))
            canvas.paste(b, ((side - w) // 2 + a.width + 30, (side - b.height) // 2))
        canvas.save(OUT_DIR / f'{name}.webp', 'WEBP', quality=88, method=6)

    for f in sorted(OUT_DIR.glob('*.webp')):
        print(f'{f.name:12} {f.stat().st_size // 1024} КБ  {Image.open(f).size}')


if __name__ == '__main__':
    main()
