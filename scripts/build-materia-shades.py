# -*- coding: utf-8 -*-
"""
Палитра MATERIA из официальной карты оттенков — фото-свотчи + коды.

**Источник — МЕЖДУНАРОДНАЯ карта** (`Работа/Lebel/materia.pdf`), а не японская из
`color-charts/`. Разница принципиальная и поймана сравнением двух карт: в международной
есть 21-я колонка **Lime (L)**, которой в японской нет вовсе. Оттенки L-8, L-10, L-12 —
настоящие, и брать японскую карту значит потерять три оттенка.

Коды на карте нарисованы, а не набраны текстом, — переписаны с рендера глазами и заданы
здесь таблицей колонок и строк. Проверка: число свотчей в каждой строке печатается при
запуске и должно совпадать с картой.

Страница карты — одна растровая картинка, координат ячеек в PDF нет. Сетка ищется
проекцией непустых пикселей по области свотчей (тот же приём, что для Колестона и Igora):
21 колонка и 13 строк находятся сами, руками заданы только их НАЗВАНИЯ.

Запуск: .venv/Scripts/python.exe scripts/build-materia-shades.py
"""
import json
import pathlib
import re

import fitz
import numpy as np
from PIL import Image, ImageDraw

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = r'D:\Projects\work\Работа\Lebel\materia.pdf'
IMG_DIR = ROOT / 'public/images/shades/lebel-materia'
OUT_JSON = ROOT / 'src/data/lebel-materia-shades.json'
DPI = 300

# Колонки слева направо, как в шапке карты.
TONES = ['CB', 'B', 'WB',
         'PBe', 'OBe', 'Be', 'ABe', 'Gr', 'Ma', 'Pe', 'MT',
         'R', 'K', 'O', 'G', 'M', 'L', 'A', 'CA', 'V', 'P']
# Строки сверху вниз. Уровни 13 и 11 на карте пустые — свотчей там нет, и проекция их не
# находит; в этом списке их тоже нет.
ROW_NAMES = ['makeup', 14, 12, 10, 9, 8, 7, 6, 5, 4, 3, 2, 'mix']

# Контрольная колонка слева (LT, LT-EX, CLRμ) в палитру НЕ идёт, и это осознанно: это не
# оттенки, а осветляющие и разбавитель. На карте у LT и LT-EX вместо цвета показана сила
# осветления — прядь наполовину белая, наполовину коричневая; круглым свотчем рядом с
# настоящими оттенками это читалось бы как брак печати. Про них — текстом в статье.
# CLRμ к тому же помечен синим квадратом, то есть относится к линии MATERIA μ.

BROWN = {'CB', 'B', 'WB'}
TEXTURE = {'PBe', 'OBe', 'Be', 'ABe', 'Gr', 'Ma', 'Pe', 'MT'}


def code_for(tone: str, row) -> str | None:
    if row == 'makeup':
        # У фиолетовой колонки на карте подписано M-RV (Red Violet), а не M-V.
        return 'M-RV' if tone == 'V' else f'M-{tone}'
    if row == 'mix':
        return f'{tone}-mix'
    if row == 2:
        # Единственный оттенок 2 уровня подписан на карте BB, без номера уровня.
        return 'BB' if tone == 'A' else None
    return f'{tone}-{row}'


def group_for(tone: str, row) -> str:
    if row in ('makeup', 'mix'):
        return row
    if tone in BROWN:
        return 'brown'
    return 'texture' if tone in TEXTURE else 'primary'


def runs(mask, min_len: int):
    out, start = [], None
    for i, v in enumerate(mask):
        if v and start is None:
            start = i
        elif not v and start is not None:
            if i - start >= min_len:
                out.append((start, i))
            start = None
    if start is not None and len(mask) - start >= min_len:
        out.append((start, len(mask)))
    return out


def circle(img: Image.Image, size: int = 140) -> Image.Image:
    """Круглый свотч с прозрачными углами — тот же вид, что у остальных линеек."""
    img = img.resize((size, size), Image.LANCZOS).convert('RGBA')
    mask = Image.new('L', (size * 4, size * 4), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size * 4 - 1, size * 4 - 1), fill=255)
    img.putalpha(mask.resize((size, size), Image.LANCZOS))
    return img


def price_index() -> dict:
    """Код оттенка -> позиция прайса. В 1С товар называется «Краска д/волос СТОЙКАЯ <код>»,
    регистр кода гуляет (GR-12 в прайсе против Gr-12 на карте), поэтому ключ в верхнем."""
    items = json.loads((ROOT / 'src/data/priceItems.json').read_text(encoding='utf-8'))
    out = {}
    for it in items:
        m = re.match(r'Краска д/волос СТОЙКАЯ\s+(\S+)', it['name'])
        if m:
            out[m.group(1).upper()] = it
    return out


def main() -> None:
    doc = fitz.open(SRC)
    pix = doc[0].get_pixmap(dpi=DPI)
    sheet = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
    doc.close()

    a = np.asarray(sheet).astype(int)
    ink = a.min(axis=2) < 230
    H, W = ink.shape

    col_runs = runs(ink[int(H * 0.14):int(H * 0.90), :].mean(axis=0) > 0.06, 40)
    row_runs = runs(ink[:, int(W * 0.03):int(W * 0.99)].mean(axis=1) > 0.05, 30)
    # Первые две найденные «строки» — полосы заголовков групп и плашки тонов, последняя —
    # легенда внизу. Строки со свотчами лежат между ними.
    row_runs = row_runs[2:2 + len(ROW_NAMES)]
    if len(col_runs) != len(TONES) or len(row_runs) != len(ROW_NAMES):
        raise SystemExit(f'сетка не сошлась: колонок {len(col_runs)} (ждали {len(TONES)}), '
                         f'строк {len(row_runs)} (ждали {len(ROW_NAMES)})')

    IMG_DIR.mkdir(parents=True, exist_ok=True)
    for old in IMG_DIR.glob('*.webp'):
        old.unlink()

    prices = price_index()
    shades, skipped, matched = [], 0, 0

    def take(code: str, group: str, row, col_idx: int, x0: int, x1: int, y0: int, y1: int):
        nonlocal skipped, matched
        cell = np.asarray(sheet.crop((x0, y0, x1, y1))).astype(int)
        if (cell.min(axis=2) < 235).mean() < 0.30:
            skipped += 1
            return
        # Цвет — медиана непустых пикселей центра: края пряди светлее из-за бликов.
        h, w, _ = cell.shape
        core = cell[int(h * 0.2):int(h * 0.8), int(w * 0.1):int(w * 0.65)].reshape(-1, 3)
        core = core[core.min(axis=1) < 235]
        r, g, b = np.median(core, axis=0).astype(int)

        # Прядь на карте — трапеция: слева широкая, справа сходит на нет. Квадрат во всю
        # высоту ячейки цепляет белые углы, и у круглого свотча срезается правый край.
        # Берём квадрат поуже и по центру высоты — он целиком внутри пряди.
        side = int((y1 - y0) * 0.78)
        top = y0 + ((y1 - y0) - side) // 2
        left = x0 + int((x1 - x0) * 0.08)
        slug = code.lower().replace('/', '-')
        circle(sheet.crop((left, top, left + side, top + side))).save(
            IMG_DIR / f'{slug}.webp', 'WEBP', quality=92, method=6)

        # В `row` идёт РЕАЛЬНЫЙ уровень яркости, а не номер строки на карте: сетка
        # (ShadeSwatchGrid) сортирует по нему по убыванию, чтобы светлые стояли первыми —
        # как на самой карте. С номером строки порядок получался зеркальным.
        # У Make-up Line и mix-tone уровня нет, они сортируются по колонке.
        shade = {'code': code, 'hex': f'#{r:02x}{g:02x}{b:02x}', 'group': group,
                 'row': row if isinstance(row, int) else 0, 'col': col_idx,
                 'image': f'/images/shades/lebel-materia/{slug}.webp'}
        live = prices.get(code.upper())
        if live:
            # Снимок на момент сборки: на каждой сборке сайта цена и название всё равно
            # пересчитываются из прайса (resolveLiveShades).
            shade['name'], shade['price'] = live['name'], live['price']
            matched += 1
        shades.append(shade)

    for row, (ry0, ry1) in zip(ROW_NAMES, row_runs):
        # Подпись с кодом идёт сразу под прядью и попадает в ту же полосу — отрезаем низ.
        y1 = ry0 + int((ry1 - ry0) * 0.82)
        for col_idx, tone in enumerate(TONES):
            code = code_for(tone, row)
            if code:
                cx0, cx1 = col_runs[col_idx]
                take(code, group_for(tone, row), row, col_idx, cx0, cx1, ry0, y1)

    OUT_JSON.write_text(json.dumps(shades, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    print(f'оттенков: {len(shades)}, пустых ячеек пропущено: {skipped}')
    per_row = {}
    for s in shades:
        per_row.setdefault(s['group'] if s['group'] in ('makeup', 'mix') else s['row'], []).append(s['code'])
    for row, codes in per_row.items():
        print(f'  {str(row):>6}: {len(codes):2d}  {" ".join(codes)}')
    print(f'\nсопоставлено с прайсом: {matched} из {len(prices)} позиций MATERIA')
    missing = sorted(set(prices) - {s['code'].upper() for s in shades})
    if missing:
        print('ЕСТЬ В ПРАЙСЕ, НО НЕТ НА КАРТЕ:', missing)


if __name__ == '__main__':
    main()
