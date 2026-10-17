"""Анимация сцены: оживает то, что в кадре появилось нового.

Сравниваем кадр сцены с кадром предыдущей сцены. Если заголовок тот же (раскрытие внутри сцены),
новое — это разница двух кадров (новая карточка, вторая прядь, правильный вопрос): она въезжает
снизу с пружинным отскоком и проявляется, остальное стоит. Если сцена новая — проявляется всё
содержимое со сдвигом. Если изменилась большая часть кадра (подсветка ответа) — только проявление.
Плюс по желанию круг пропорции в углу («wheel»: доля краски в %, «wheel_label»: «1 : 1»).

anim_frames(...) пишет PNG-кадры анимации в папку и возвращает их число.
"""
import math
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

W, H = 1080, 1350
BG = (250, 246, 240)
ANIM = 0.6        # длительность въезда, с
SHIFT = 60        # на сколько пикселей снизу въезжает новое


def ease_out_back(x, s=1.6):
    x -= 1
    return 1 + (s + 1) * x ** 3 + s * x ** 2


def ease_out(x):
    return 1 - (1 - x) ** 3


def changed_layers(cur, prev):
    """Куски «что появилось/изменилось»: отдельные области, где текущий кадр отличается от прежнего.
    Каждая область — свой слой: заголовок сменится проявлением, новая прядь или карточка въедет."""
    diff = ImageChops.difference(cur.convert('RGB'), prev.convert('RGB')).convert('L')
    mask = diff.point(lambda v: 255 if v > 3 else 0).filter(ImageFilter.MaxFilter(9))  # белая карточка на бежевом фоне отличается всего на ~9
    # для поиска областей маску раздуваем сильнее: строки одной карточки (зазор ~20 px) сливаются
    # в один блок, а соседние карточки (зазор 24 px) остаются отдельными — иначе куски одной
    # карточки въезжали с разной задержкой и наезжали друг на друга (проба 17.10.2026)
    group = diff.point(lambda v: 255 if v > 3 else 0).filter(ImageFilter.MaxFilter(21))
    small = group.resize((W // 8, H // 8)).point(lambda v: 255 if v > 127 else 0)
    sw, sh = small.size
    px = small.load()
    seen = set()
    boxes = []
    for y in range(sh):                       # области связности на уменьшенной маске
        for x in range(sw):
            if px[x, y] and (x, y) not in seen:
                stack, x0, y0, x1, y1 = [(x, y)], x, y, x, y
                seen.add((x, y))
                while stack:
                    cx, cy = stack.pop()
                    x0, y0, x1, y1 = min(x0, cx), min(y0, cy), max(x1, cx), max(y1, cy)
                    for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                        if 0 <= nx < sw and 0 <= ny < sh and px[nx, ny] and (nx, ny) not in seen:
                            seen.add((nx, ny))
                            stack.append((nx, ny))
                boxes.append((x0 * 8, y0 * 8, min(W, (x1 + 1) * 8), min(H, (y1 + 1) * 8)))
    layers = []
    rgba = cur.convert('RGBA')
    for b in boxes:
        lay = rgba.crop(b)
        lay.putalpha(mask.crop(b))
        area = (b[2] - b[0]) * (b[3] - b[1]) / (W * H)
        layers.append((lay, b, area))
    return layers


def wheel_spot(img):
    """Свободное место под круг пропорции: правый верхний угол, иначе правый нижний; None — места нет."""
    for cx, cy in ((W - 90 - 62, 90 + 62), (W - 90 - 62, H - 70 - 62 - 60)):
        box = (cx - 80, cy - 80, cx + 80, cy + 110)
        region = img.convert('RGB').crop(box)
        lo, hi = region.convert('L').getextrema()
        if hi - lo < 12:                       # однотонный фон — свободно
            return cx, cy
    return None


def wheel(img, pct, label, k, spot):
    """Круг пропорции: заполняется до pct за время анимации (k 0..1)."""
    if spot is None:
        return
    cx, cy = spot
    d = ImageDraw.Draw(img)
    r = 62
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(203, 227, 251), outline=(56, 98, 140), width=4)
    a = 360 * pct / 100 * ease_out(k)
    if a > 0.5:
        d.pieslice([cx - r + 4, cy - r + 4, cx + r - 4, cy + r - 4], -90, -90 + a, fill=(194, 106, 46))
    if label:
        from render_carousel import font
        f = font('sans', 30, 700)
        d.text((cx, cy + r + 26), label, font=f, fill=(56, 98, 140), anchor='mm')


STYLES = ('up', 'pop', 'left', 'right', 'wipe', 'drop')


def pick_style(scene):
    """Вид появления: задан в сцене («anim») или выбран по ролику и номеру сцены — у каждого ролика
    свой порядок, внутри ролика виды чередуются (Олег, 17.10.2026: «не делай у всех однообразной»).
    Две пряди рядом лучше открывать шторкой."""
    if scene.get('anim') in STYLES:
        return scene['anim']
    if scene.get('type') == 'versus':
        return 'wipe'
    import zlib
    seed = scene.get('_seed', '')
    video = zlib.crc32(seed.rsplit('-', 1)[0].encode())
    n = int(seed.rsplit('-', 1)[-1] or 0)
    order = sorted(STYLES, key=lambda s: zlib.crc32(f'{video}{s}'.encode()))   # свой порядок у ролика
    return order[n % len(order)]


def place(fr, layer, box, kk, style):
    """Наложить кусок с прогрессом kk (0..1) выбранным способом."""
    lay = layer
    x, y = box[0], box[1]
    alpha = min(1.0, kk * 1.8)
    if style == 'fade':
        alpha = ease_out(kk)
    elif style == 'up':
        y += int(SHIFT * (1 - ease_out_back(kk)))
    elif style == 'drop':
        y -= int(SHIFT * (1 - ease_out_back(kk)))
    elif style in ('left', 'right'):
        sgn = -1 if style == 'left' else 1
        x += int(sgn * 120 * (1 - ease_out_back(kk, 1.2)))
    elif style == 'pop':
        s = 0.8 + 0.2 * ease_out_back(kk, 2.2)
        w, h = max(1, int(layer.width * s)), max(1, int(layer.height * s))
        lay = layer.resize((w, h), Image.LANCZOS)
        x += (layer.width - w) // 2
        y += (layer.height - h) // 2
    elif style == 'wipe':                          # шторка слева направо
        alpha = 1.0
        wv = int(layer.width * ease_out(kk))
        if wv <= 0:
            return
        lay = layer.crop((0, 0, wv, layer.height))
    lay = lay.copy()
    lay.putalpha(lay.getchannel('A').point(lambda v, a=alpha: int(v * a)))
    fr.alpha_composite(lay, (x, y))


def anim_frames(cur_png, prev_png, scene, out_dir, fps=30):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cur = Image.open(cur_png).convert('RGBA')
    spot = wheel_spot(cur) if scene.get('wheel') is not None else None
    style = pick_style(scene)
    same = prev_png is not None and scene.get('_same_as_prev')
    n = int(ANIM * fps)
    if same:
        base = Image.open(prev_png).convert('RGBA')
    else:
        base = Image.new('RGBA', (W, H), BG + (255,))
        ImageDraw.Draw(base).rectangle([0, 0, W, 12], fill=(200, 0, 15))
    layers = changed_layers(cur, base)
    # куски, которые в прежнем кадре были не пустыми (сменился текст), — сначала гасим старое
    old = [(base.crop(b), b) for lay, b, a in layers if same]
    for i in range(n + 1):
        k = i / n
        fr = base.copy()
        for patch, b in old:                       # закрыть прежнее содержимое изменившихся мест фоном
            cover = Image.new('RGBA', (b[2] - b[0], b[3] - b[1]), BG + (int(255 * min(1.0, k * 2.5)),))
            fr.alpha_composite(cover, (b[0], b[1]))
        for idx, (layer, box, area) in enumerate(layers):
            kk = max(0.0, min(1.0, k * 1.25 - idx * 0.12))   # куски — друг за другом
            big = area > 0.45 or box[1] < 230                  # крупное или заголовок — только проявление
            if big and same:                                   # сменился текст: новое — после того, как ушло старое
                kk = max(0.0, (k - 0.4) / 0.6)
            place(fr, layer, box, kk, 'fade' if big else style)
        if scene.get('wheel') is not None:
            wheel(fr, scene['wheel'], scene.get('wheel_label'), k, spot)
        fr.convert('RGB').save(out_dir / f'{i:03d}.png')
    # последний кадр сцены (с полным кругом) — для паузы после анимации
    last = cur.copy()
    if scene.get('wheel') is not None:
        wheel(last, scene['wheel'], scene.get('wheel_label'), 1.0, spot)
    last.convert('RGB').save(out_dir / 'still.png')
    return n + 1
