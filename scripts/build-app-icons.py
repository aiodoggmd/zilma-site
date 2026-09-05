# -*- coding: utf-8 -*-
"""
Сборка иконок приложения (экран загрузки PWA + ярлык на телефоне) из фирменного логотипа.

Повод: пользователь попросил заменить иконку приложения на настоящий логотип Zilma
(голова из парикмахерских инструментов), которую прислал как D:\\Projects\\work\\logo.psd.

ПОЧЕМУ ИСТОЧНИК НЕ PSD. В самом PSD логотип занимает всего 259x260 пикселей — это
макет экрана целиком, логотип на нём маленький. Растягивать его до 512 значит получить
мыло. Тот же логотип уже лежит в проекте как public/images/logo.jpg в 901x718 —
втрое крупнее, и именно он показан в хиро сайта. Берём его: рисунок один и тот же,
разрешение честное.

Что делает скрипт:
  * вырезает светлый рисунок из logo.jpg по его границам;
  * кладёт на фирменный красный радиальный фон (цвета сняты пипеткой с самого logo.jpg,
    не подобраны на глаз: центр #cc0115, край #8a000d);
  * собирает два набора, как того требует Android:
      - круглый (purpose: any)      — то, что видно на экране загрузки и в шторке;
      - квадратный (purpose: maskable) с запасом ~12% по краям — Android накладывает
        на него СВОЮ маску, и без запаса срезает края рисунка.
    Без maskable-набора Android скругляет уже скруглённую картинку и по краям остаются
    белые огрызки — на это уже наступали в августе, см. CLAUDE.md.

Запуск: .venv/Scripts/python.exe scripts/build-app-icons.py
"""
from PIL import Image, ImageDraw
import numpy as np
import os

SRC = 'public/images/logo.jpg'
OUT = 'public'

# Цвета сняты с logo.jpg: центр ярче, край темнее — тот же радиальный переход,
# что на оригинале. Хардкодить «примерно красный» нельзя, у бренда он конкретный.
RED_CENTER = (204, 1, 21)
RED_EDGE = (138, 0, 13)


def artwork() -> Image.Image:
    """Светлый рисунок с прозрачным фоном, обрезанный по своим границам."""
    im = Image.open(SRC).convert('RGB')
    a = np.array(im).astype(int)
    # Рисунок — светлые линии на красном. Порог по всем трём каналам: только красный
    # канал не годится, у фона он тоже высокий.
    light = (a[:, :, 0] > 200) & (a[:, :, 1] > 170) & (a[:, :, 2] > 150)
    ys, xs = np.where(light)
    box = (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1)

    # Альфу берём не по жёсткому порогу, а по «насколько пиксель светлее красного» —
    # так сохраняются сглаженные края линий, иначе рисунок получается зубчатым.
    g = np.array(im.convert('L')).astype(float)
    lo, hi = 90.0, 235.0
    alpha = np.clip((g - lo) / (hi - lo), 0, 1) * 255

    rgba = Image.new('RGBA', im.size, (252, 246, 238, 0))
    rgba.putalpha(Image.fromarray(alpha.astype('uint8')))
    return rgba.crop(box)


def red_field(size: int) -> Image.Image:
    """Радиальный красный фон — как на оригинале логотипа."""
    yy, xx = np.mgrid[0:size, 0:size]
    cx = cy = (size - 1) / 2
    dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) / (size / 2 * 1.25)
    dist = np.clip(dist, 0, 1)[..., None]
    field = np.array(RED_CENTER) * (1 - dist) + np.array(RED_EDGE) * dist
    return Image.fromarray(field.astype('uint8'), 'RGB').convert('RGBA')


def compose(size: int, art_ratio: float, circle: bool) -> Image.Image:
    """Иконка: красное поле + рисунок по центру. circle=True — обрезать в круг."""
    icon = red_field(size)
    art = artwork()
    w = int(size * art_ratio)
    h = int(art.height * w / art.width)
    icon.alpha_composite(art.resize((w, h), Image.LANCZOS), ((size - w) // 2, (size - h) // 2))

    if circle:
        mask = Image.new('L', (size * 4, size * 4), 0)   # рисуем крупнее и уменьшаем —
        ImageDraw.Draw(mask).ellipse([0, 0, size * 4 - 1, size * 4 - 1], fill=255)
        mask = mask.resize((size, size), Image.LANCZOS)  # так край круга без «лесенки»
        icon.putalpha(mask)
    return icon


def favicons() -> list:
    """Иконка вкладки браузера — тот же логотип, что и у приложения.

    Решение пользователя 2026-09-05, принято с открытыми глазами: я показал ему
    сравнение четырёх вариантов в реальных размерах и честно предупредил, что в 16
    пикселях тонкие линии логотипа сливаются в красный круг. Он выбрал единство знака
    важнее читаемости мелкой иконки — это его бренд и его право.

    Единственная уступка размеру: в 16 и 32 пикселях рисунок кладём КРУПНЕЕ (0.78
    против 0.62). Мельче он превращается в шум быстрее. Это не новая графика, а тот же
    рисунок в другом масштабе.
    """
    made = []
    for s, ratio in ((16, 0.78), (32, 0.78)):
        p = f'{OUT}/favicon-{s}x{s}.png'
        compose(s * 8, ratio, circle=True).resize((s, s), Image.LANCZOS).save(p)
        made.append(p)

    # Настоящий multi-size ICO, а не PNG с переименованным расширением: старые версии
    # Windows/Edge читают именно .ico и на подделку реагируют пустым квадратом.
    ico = compose(256, 0.72, circle=True)
    ico.save(f'{OUT}/favicon.ico', sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
    made.append(f'{OUT}/favicon.ico')

    # SVG с вложенным PNG: рисунок фотографический (тонкие линии, градиент),
    # честная векторная трассировка тут не даёт ничего, кроме потери деталей.
    import base64, io as _io
    buf = _io.BytesIO()
    compose(256, 0.72, circle=True).save(buf, 'PNG', optimize=True)
    b64 = base64.b64encode(buf.getvalue()).decode()
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256">'
        f'<image width="256" height="256" href="data:image/png;base64,{b64}"/></svg>'
    )
    with open(f'{OUT}/favicon.svg', 'w', encoding='utf-8') as f:
        f.write(svg)
    made.append(f'{OUT}/favicon.svg')
    return made


def main() -> None:
    made = []
    # Круглые (purpose: any) — рисунок покрупнее, поле круглое.
    for s in (192, 512):
        p = f'{OUT}/icon-{s}.png'
        compose(s, 0.62, circle=True).save(p)
        made.append(p)

    # Квадратные maskable — рисунок мельче: Android срежет края своей маской,
    # запас по краям обязателен.
    for s in (192, 512):
        p = f'{OUT}/icon-{s}-maskable.png'
        compose(s, 0.50, circle=False).save(p)
        made.append(p)

    # iOS: маску накладывает сама система, поэтому квадрат без скругления.
    p = f'{OUT}/apple-touch-icon.png'
    compose(180, 0.58, circle=False).convert('RGB').save(p)
    made.append(p)

    made += favicons()

    for p in made:
        kb = os.path.getsize(p) // 1024
        if p.endswith('.svg'):
            print(f'  {p}: SVG с вложенным PNG, {kb} КБ')
            continue
        im = Image.open(p)
        print(f'  {p}: {im.size[0]}x{im.size[1]} {im.mode}, {kb} КБ')


if __name__ == '__main__':
    main()
