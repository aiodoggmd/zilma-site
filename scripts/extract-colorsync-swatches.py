# -*- coding: utf-8 -*-
"""
Вырезает круглые фото-свотчи оттенков из официальной карты прядей Matrix SoColor Sync
(NEWS/2026-08-13-color-sync/page-N.png) и раскладывает их в public/images/shades/matrix-sync/.

Почему фото, а не плоский цвет: реальный снимок пряди показывает и оттенок, и то, как он
ложится на волосе — плоский квадрат из усреднённого пикселя этого не передаёт (проверено
на Londa, 2026-08-29).

Коды НЕ распознаются автоматически: на карте они напечатаны подписями под кружками, а OCR
здесь лишний риск. Вместо этого они переписаны вручную по колонкам и рядам (CODES ниже),
а скрипт независимо находит кружки и СВЕРЯЕТ их количество с переписанным списком по каждой
панели. Если числа разойдутся — скрипт падает, а не молча сдвигает подписи на соседний цвет.

Запуск: .venv/Scripts/python.exe scripts/extract-colorsync-swatches.py
"""
import json
import pathlib
import sys

import numpy as np
from PIL import Image

SRC = pathlib.Path(__file__).resolve().parent.parent.parent / 'NEWS' / '2026-08-13-color-sync'
OUT = pathlib.Path(__file__).resolve().parent.parent / 'public' / 'images' / 'shades' / 'matrix-sync'

# Панели идут парами слева направо; коды переписаны по рядам сверху вниз,
# внутри ряда — слева направо, ровно как напечатано на карте.
PAGES = {
    1: {
        'Холодные': ['1A', '4A', '5VV', '8A', '8V', '8P', '10A', '10V', '10P',
                     '11A', '11V', '11P', 'SPA', 'SPV', 'SPP'],
        'Натуральные': ['3N', '5N', '6N', '7NA', '7NV', '8N', '9NA', '10N', '11N', 'SPN'],
    },
    2: {
        'Тёплые': ['3WN', '5WN', '6WN', '7WM', '8WN'],
        'Мокка': ['5M', '5MM', '6M', '7AM', '7VM', '7MV', '7M', '7MM', '8M', '9MM',
                  '10M', '10MM', 'SPM'],
    },
    3: {
        'Коричневые': ['6BC', '8BC'],
        'Бронзовые': ['8G', '9GV', '10G'],
    },
    4: {
        'Пауэр Кулс': ['5AA', '5VA', '7AA', '7VA'],
        'Яркие': ['4RV+', '6RV+', '7CC+', '8RC+'],
    },
    # Коды кислотной технологии помечены префиксом «ac:» намеренно: 5N, 5M, 8A и 8V
    # существуют В ОБЕИХ технологиях и это РАЗНЫЕ продукты с разным цветом пряди.
    # Без префикса кислотные кружки затирали щелочные файлы (поймано на первом прогоне).
    5: {
        'Кислотные': ['ac:2J', 'ac:5A', 'ac:5N', 'ac:5M', 'ac:8AA', 'ac:8A', 'ac:8V',
                      'ac:8AG', 'ac:10PA', 'ac:10PV', 'ac:10PR', 'ac:10PG'],
        'Прозрачный': ['CLEAR'],
    },
}

MIN_R, MAX_R = 60, 130          # ожидаемый радиус кружка в пикселях исходника
ROW_TOLERANCE = 60              # разброс по вертикали, при котором кружки считаются одним рядом


def find_circles(img: Image.Image):
    """Ищет кружки-пряди: всё, что заметно отличается от розового фона панели и от белого."""
    a = np.asarray(img.convert('RGB')).astype(np.int16)
    r, g, b = a[:, :, 0], a[:, :, 1], a[:, :, 2]

    # Фон панели — очень светлый розовый, поля — белые. Кружок темнее любого из них.
    # Порог по светлоте, а не по «непохоже на конкретный цвет»: часть оттенков сама
    # почти белая (10P, 11V), и сравнение с фоном по цвету их бы потеряло.
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    mask = lum < 235

    # Подписи-коды и заголовки — тоже тёмные. Отсечём их размером компоненты ниже.
    visited = np.zeros(mask.shape, dtype=bool)
    h, w = mask.shape
    circles = []

    ys, xs = np.nonzero(mask)
    for y0, x0 in zip(ys, xs):
        if visited[y0, x0]:
            continue
        # BFS по компоненте (scipy не ставим — пакеты только внутри проекта)
        stack = [(y0, x0)]
        visited[y0, x0] = True
        pts = []
        while stack:
            y, x = stack.pop()
            pts.append((y, x))
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not visited[ny, nx]:
                    visited[ny, nx] = True
                    stack.append((ny, nx))
        if len(pts) < MIN_R * MIN_R:
            continue
        pa = np.array(pts)
        y1, y2 = pa[:, 0].min(), pa[:, 0].max()
        x1, x2 = pa[:, 1].min(), pa[:, 1].max()
        bw, bh = x2 - x1, y2 - y1
        if not (2 * MIN_R <= bw <= 2 * MAX_R and 2 * MIN_R <= bh <= 2 * MAX_R):
            continue
        if abs(bw - bh) > 0.18 * max(bw, bh):     # круг, а не строка текста
            continue
        fill = len(pts) / (bw * bh)
        if fill < 0.6:
            continue
        circles.append({'x1': int(x1), 'y1': int(y1), 'x2': int(x2), 'y2': int(y2),
                        'cx': int((x1 + x2) / 2), 'cy': int((y1 + y2) / 2)})
    return circles


def panel_split(img: Image.Image) -> int:
    """Находитx-границу между левой и правой панелями по их розовому фону.

    Делить пополам нельзя: панели занимают не по половине ширины, и правая колонка
    кружков ЛЕВОЙ панели заходит за середину листа — при делении пополам она уезжала
    в чужую панель, и счёт кружков расходился с переписанными кодами.
    """
    a = np.asarray(img.convert('RGB')).astype(np.int16)
    r, g, b = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    pink = (r >= 245) & (r - g >= 6) & (r - g <= 34) & (r - b >= 2)
    per_col = pink.sum(axis=0)
    strong = per_col > per_col.max() * 0.35
    runs, start = [], None
    for x, v in enumerate(strong):
        if v and start is None:
            start = x
        elif not v and start is not None:
            runs.append((start, x - 1))
            start = None
    if start is not None:
        runs.append((start, len(strong) - 1))
    runs = [r_ for r_ in runs if r_[1] - r_[0] > 200]
    if len(runs) < 2:
        return img.width // 2
    return (runs[0][1] + runs[1][0]) // 2


def order_reading(circles):
    """Сортирует кружки по рядам сверху вниз, внутри ряда — слева направо."""
    rows = []
    for c in sorted(circles, key=lambda c: c['cy']):
        for row in rows:
            if abs(row[0]['cy'] - c['cy']) <= ROW_TOLERANCE:
                row.append(c)
                break
        else:
            rows.append([c])
    out = []
    for row in rows:
        out.extend(sorted(row, key=lambda c: c['cx']))
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    result = {}
    problems = []

    for page, panels in PAGES.items():
        img = Image.open(SRC / f'page-{page}.png')
        circles = find_circles(img)
        mid = panel_split(img)
        halves = {'left': [c for c in circles if c['cx'] < mid],
                  'right': [c for c in circles if c['cx'] >= mid]}

        for (panel_name, codes), side in zip(panels.items(), ('left', 'right')):
            found = order_reading(halves[side])
            if len(found) != len(codes):
                problems.append(
                    f'стр. {page}, панель «{panel_name}»: кружков найдено {len(found)}, '
                    f'кодов переписано {len(codes)}'
                )
                continue
            for code, c in zip(codes, found):
                pad = 4
                crop = img.crop((c['x1'] + pad, c['y1'] + pad, c['x2'] - pad, c['y2'] - pad))
                crop = crop.convert('RGB').resize((160, 160), Image.LANCZOS)
                fname = code.replace('+', 'plus').replace('ac:', 'acid-').replace('/', '-').lower() + '.webp'
                crop.save(OUT / fname, 'WEBP', quality=88, method=6)
                # средний цвет — запасной вариант для мест, где фото не выводится
                arr = np.asarray(crop).reshape(-1, 3)
                hexv = '#%02x%02x%02x' % tuple(int(v) for v in np.median(arr, axis=0))
                result[code] = {'panel': panel_name, 'page': page, 'file': fname, 'hex': hexv}
            print(f'стр. {page} · {panel_name}: {len(found)} шт.')

    if problems:
        print('\nРАСХОЖДЕНИЯ — ничего не записано в JSON:')
        for p in problems:
            print('  ' + p)
        sys.exit(1)

    (pathlib.Path(__file__).resolve().parent / '_colorsync-raw.json').write_text(
        json.dumps(result, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'\nвсего оттенков: {len(result)}')


if __name__ == '__main__':
    main()
