#!/usr/bin/env python3
"""
Уменьшает картинку до реального размера показа на сайте и сохраняет рядом как .webp
(оригинал не трогает и не удаляет — удалить/закоммитить решает тот, кто запускает).

Использование:
  python scripts/optimize-image.py <категория> <файл1> [файл2 ...]

Категории (см. также раздел «Оптимизация картинок» в README.md):
  cover    — обложка статьи (карточка в ленте / шапка статьи), макс. 1200px по длинной стороне
  product  — товарное фото в теле статьи (показывается высотой 320/240px), макс. 700px
  palette  — палитра оттенков (показывается высотой 480/320px на всю ширину колонки), макс. 1600px
  icon     — мелкие иконки/фото шагов (напр. аллерготест), макс. 400px
"""
import sys
import os
from PIL import Image

RULES = {
    "cover": (1200, 84),
    "product": (700, 86),
    "palette": (1600, 82),
    "icon": (400, 86),
}


def optimize(category: str, path: str) -> None:
    max_side, quality = RULES[category]
    if not os.path.exists(path):
        print(f"ПРОПУСК (нет файла): {path}")
        return

    im = Image.open(path)
    w, h = im.size
    longer = max(w, h)
    if longer > max_side:
        scale = max_side / longer
        im = im.resize((round(w * scale), round(h * scale)), Image.LANCZOS)
    if im.mode == "P":
        im = im.convert("RGBA")

    dst = os.path.splitext(path)[0] + ".webp"
    im.save(dst, "WEBP", quality=quality, method=6)

    before_kb = os.path.getsize(path) / 1024
    after_kb = os.path.getsize(dst) / 1024
    saved = 100 * (1 - after_kb / before_kb) if before_kb else 0
    print(f"{path} -> {dst}: {w}x{h} {before_kb:.0f}KB -> {im.size[0]}x{im.size[1]} {after_kb:.0f}KB ({saved:.0f}% меньше)")


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] not in RULES:
        print(__doc__)
        sys.exit(1)
    category = sys.argv[1]
    for path in sys.argv[2:]:
        optimize(category, path)
