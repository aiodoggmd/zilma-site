"""Слайды карусели Instagram (1080×1350) в стиле Zilma из простого JSON.

Запуск из work/Site:
    .venv\\Scripts\\python.exe tools\\instagram\\render_carousel.py <slides.json> <папка>

Текст и цифры рисует программа, а не генератор картинок: так коды оттенков и формулы
выходят точными. Картинки (обложка) — готовые из статьи или Kling, без текста.
В любом тексте **так** выделяется код или формула (медный жирный).
Формат JSON — в README.md рядом.
"""
import json
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

W, H = 1080, 1350
M = 90                          # поля
HERE = Path(__file__).parent
BG, CARD, LINE = '#faf6f0', '#ffffff', '#d8cfbf'
INK, MUTED, RED, BLUE = '#2b201c', '#9c948c', '#c8000f', '#38628c'
COPPER, CODE, GREEN, DRED = '#c26a2e', '#8a3f12', '#3d7a4f', '#8a000d'
PINK_BG, GREEN_BG, TAG_BG = '#fbecec', '#eef6ef', '#cbe3fb'
FOOT = 70                       # высота подвала


def font(kind, size, weight=400):
    if kind == 'serif':
        f = ImageFont.truetype(str(HERE / 'fonts' / 'PlayfairDisplay.ttf'), size)
        f.set_variation_by_axes([max(400, weight)])
    else:
        f = ImageFont.truetype(str(HERE / 'fonts' / 'Inter.ttf'), size)
        f.set_variation_by_axes([14, weight])
    return f


def runs(text):
    """«текст **код** текст» -> [(слово, жирный, вплотную)], перенос строки — ('\\n', False, False).
    «Вплотную» — слово без пробела перед ним: «**тон**, а» — запятая прижата к коду."""
    out = []
    parts = re.split(r'\*\*(.+?)\*\*', text)
    for i, part in enumerate(parts):
        bold = i % 2 == 1
        if i and (not parts[i - 1] or parts[i - 1][-1] in ' \n'):
            part = ' ' + part          # стык уже с пробелом — склеивать нечего
        for para_i, para in enumerate(part.split('\n')):
            if para_i:
                out.append(('\n', False, False))
            for j, w in enumerate(para.split(' ')):
                if w:
                    glue = i > 0 and para_i == 0 and j == 0 and bool(out) and out[-1][0] != '\n'
                    out.append((w, bold, glue))
    return out


def layout(text, size, width, weight=400, kind='sans'):
    """Разбить на строки по ширине. -> (строки [[(слово, жирный)]], высота строки)."""
    reg, bold = font(kind, size, weight), font(kind, size, 700)
    space = reg.getlength(' ')
    lines, cur, cur_w = [], [], 0
    for w, b, glue in runs(text):
        if w == '\n':
            lines.append(cur)
            cur, cur_w = [], 0
            continue
        ww = (bold if b else reg).getlength(w)
        if ww > width:
            return None, 0            # одно слово шире строки — уменьшать шрифт
        add = ww if (not cur or glue) else space + ww
        if cur and cur_w + add > width and not glue:
            lines.append(cur)
            cur, cur_w = [(w, b, False)], ww
        else:
            cur.append((w, b, glue and bool(cur)))
            cur_w += add
    lines.append(cur)
    return lines, int(size * 1.38)


def fit(text, width, max_h, size, min_size, weight=400, kind='sans'):
    """Наибольший размер шрифта, при котором текст влезает. Не влез и на минимуме — ошибка."""
    for s in range(size, min_size - 1, -2):
        lines, lh = layout(text, s, width, weight, kind)
        if lines is not None and len(lines) * lh <= max_h:
            return s, lines, lh
    raise SystemExit(f'НЕ ВЛЕЗАЕТ даже шрифтом {min_size}: «{text[:60]}…» — сократите текст')


def draw_lines(d, x, y, size, lines, lh, color=INK, weight=400, kind='sans', bold_color=CODE, align='left', width=0):
    reg, bold = font(kind, size, weight), font(kind, size, 700)
    space = reg.getlength(' ')
    for ln in lines:
        lw = sum((bold if b else reg).getlength(w) + (0 if g or k == 0 else space) for k, (w, b, g) in enumerate(ln))
        cx = x + (width - lw) / 2 if align == 'center' else x
        for k, (w, b, g) in enumerate(ln):
            if k and not g:
                cx += space
            f = bold if b else reg
            d.text((cx, y), w, font=f, fill=bold_color if b else color)
            cx += f.getlength(w)
        y += lh
    return y


def text_block(d, text, x, y, width, max_h, size, min_size, **kw):
    s, lines, lh = fit(text, width, max_h, size, min_size, kw.get('weight', 400), kw.get('kind', 'sans'))
    return draw_lines(d, x, y, s, lines, lh, width=width, **kw)


def base(n, total):
    im = Image.new('RGB', (W, H), BG)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, 12], fill=RED)
    f = font('sans', 30, 500)
    d.text((M, H - FOOT + 10), 'zilma.pro', font=f, fill=MUTED)
    if total:                                     # 0 — кадры видео: счётчик «3 / 10» не нужен
        t = f'{n} / {total}'
        d.text((W - M - f.getlength(t), H - FOOT + 10), t, font=f, fill=MUTED)
    return im, d


def title(d, text, y=80, size=66):
    return text_block(d, text, M, y, W - 2 * M, 260, size, 44, kind='serif', weight=700) + 24


def s_cover(im, d, s, root):
    img = Image.open(root / s['image']).convert('RGB')
    top_h = int(H * 0.58)
    img = ImageOps.fit(img, (W, top_h), centering=(0.5, 0.5))
    fade = Image.new('L', (1, top_h))
    for yy in range(top_h):                      # мягкий переход в фон снизу картинки
        fade.putpixel((0, yy), 255 if yy < top_h - 160 else int(255 * (top_h - yy) / 160))
    im.paste(Image.new('RGB', (W, top_h), BG), (0, 0))
    im.paste(img, (0, 0), fade.resize((W, top_h)))
    d.rectangle([0, 0, W, 12], fill=RED)
    y = text_block(d, s['title'], M, top_h - 20, W - 2 * M, 300, 76, 48, kind='serif', weight=700) + 16
    if s.get('subtitle'):
        text_block(d, s['subtitle'], M, y, W - 2 * M, H - FOOT - y - 20, 40, 30, color=MUTED)


def s_text(im, d, s, root):
    y = title(d, s['title'])
    text_block(d, s['body'], M, y + 20, W - 2 * M, H - FOOT - y - 50, 58, 34)


def card_box(d, x, y, w, h, top=COPPER):
    d.rounded_rectangle([x, y, x + w, y + h], 24, fill=CARD, outline=LINE, width=2)
    d.rounded_rectangle([x, y, x + w, y + 14], 8, fill=top)
    d.rectangle([x, y + 7, x + w, y + 14], fill=CARD)
    d.line([x + 20, y + 3, x + w - 20, y + 3], fill=top, width=6)


def s_cards(im, d, s, root):
    y = title(d, s['title'])
    if s.get('note'):                              # строка под заголовком: пропорция, оксид, время
        y = text_block(d, s['note'], M, y - 10, W - 2 * M, 120, 40, 28, color=BLUE, weight=600) + 14
    cards = s['cards']
    avail = H - FOOT - y - 30
    gap = 24
    ch = (avail - gap * (len(cards) - 1)) // len(cards)
    pad = 34

    def need(c):                                   # высота карточки по содержимому
        tw = W - 2 * M - 2 * pad - (220 if c.get('tag') else 0)
        s1, l1, h1 = fit(c['title'], tw, 130, 50, 32, 700, 'serif')
        s2, l2, h2 = fit(c['body'], W - 2 * M - 2 * pad, ch - 60 - len(l1) * h1, 50, 28)
        return 30 + len(l1) * h1 + 12 + len(l2) * h2 + 36

    hs = [min(ch, need(c)) for c in cards]
    y += max(0, (avail - sum(hs) - gap * (len(cards) - 1)) // 2)   # стопку — по центру
    show = s.get('show', len(cards))               # для видео: раскладка на все, рисуем первые show
    for k, (c, ch) in enumerate(zip(cards, hs)):
        if k >= show:
            break
        card_box(d, M, y, W - 2 * M, ch, c.get('color', COPPER))
        ty = y + 30
        tag_w = 0
        if c.get('tag'):
            tf = font('sans', 32, 600)
            tag_w = tf.getlength(c['tag']) + 40
            tx = W - M - pad - tag_w
            d.rounded_rectangle([tx, ty, tx + tag_w, ty + 50], 25, fill=TAG_BG)
            d.text((tx + 20, ty + 7), c['tag'], font=tf, fill=BLUE)
        ty = text_block(d, c['title'], M + pad, ty, W - 2 * M - 2 * pad - tag_w - 20, 130, 50, 32, kind='serif', weight=700) + 12
        text_block(d, c['body'], M + pad, ty, W - 2 * M - 2 * pad, y + ch - ty - 24, 50, 28)
        y += ch + gap


def s_fix(im, d, s, root):
    y = title(d, s['title'])
    items = s['items']
    gap = 24
    rh = (H - FOOT - y - 30 - gap * (len(items) - 1)) // len(items)
    half = (W - 2 * M) // 2
    for it in items:
        d.rounded_rectangle([M, y, M + half, y + rh], 20, fill=PINK_BG)
        d.rectangle([M, y, M + 8, y + rh], fill=DRED)
        d.rounded_rectangle([M + half, y, W - M, y + rh], 20, fill=GREEN_BG)
        d.rectangle([M + half, y, M + half + 8, y + rh], fill=GREEN)
        iw = half - 60
        by = text_block(d, it['bad'], M + 34, y + 26, iw, rh // 2, 46, 28, weight=700) + 10
        if it.get('why'):
            text_block(d, it['why'], M + 34, by, iw, y + rh - by - 20, 38, 24, color=MUTED)
        text_block(d, it['good'], M + half + 34, y + 26, iw, rh - 50, 44, 26)
        y += rh + gap


def s_keys(im, d, s, root):
    y = title(d, s['title'])
    items = s['items']
    gap = 28
    ih = (H - FOOT - y - 30 - gap * (len(items) - 1)) // len(items)
    nf = font('serif', 40, 700)
    for i, t in enumerate(items, 1):
        d.ellipse([M, y + 4, M + 70, y + 74], fill=BLUE)
        d.text((M + 35, y + 38), str(i), font=nf, fill='#ffffff', anchor='mm')
        text_block(d, t, M + 100, y, W - 2 * M - 100, ih, 54, 30)
        y += ih + gap


def s_end(im, d, s, root):
    cx = W // 2                                   # закладка — простая фигура, без эмодзи
    d.polygon([(cx - 70, 360), (cx + 70, 360), (cx + 70, 560), (cx, 500), (cx - 70, 560)], fill=COPPER)
    y = text_block(d, s['title'], M, 620, W - 2 * M, 260, 72, 48, kind='serif', weight=700, align='center') + 20
    if s.get('body'):
        text_block(d, s['body'], M, y, W - 2 * M, H - FOOT - y - 40, 42, 30, color=MUTED, align='center')


def s_versus(im, d, s, root):
    """Две картинки рядом с подписями: «Заказали» / «Получили». reveal=false — правая ещё не видна."""
    y = title(d, s['title'], size=70) + 10
    gap = 30
    w = (W - 2 * M - gap) // 2
    h = H - FOOT - y - 170
    for k, side in enumerate(('left', 'right')):
        x = M + k * (w + gap)
        sd = s[side]
        if side == 'right' and s.get('reveal') is False:
            d.rounded_rectangle([x, y, x + w, y + h], 28, outline=LINE, width=3)   # пустое место под ответ
            continue
        img = ImageOps.fit(Image.open(root / sd['image']).convert('RGB'), (w, h), centering=(0.5, 0.5))
        mask = Image.new('L', (w, h), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], 28, fill=255)
        im.paste(img, (x, y), mask)
        col = GREEN if sd.get('tone') == 'good' else DRED if sd.get('tone') == 'bad' else INK
        lf = font('sans', 46, 700)
        d.text((x + w / 2, y + h + 34), sd['label'], font=lf, fill=col, anchor='ma')
        if sd.get('sub'):
            sf = font('sans', 36, 500)
            d.text((x + w / 2, y + h + 96), sd['sub'], font=sf, fill=MUTED, anchor='ma')


def s_question(im, d, s, root):
    """Неправильный вопрос зачёркнут, правильный — крупно. new=false — правильного ещё нет."""
    y = title(d, s['title'])
    y += 60
    of = font('sans', 54, 500)
    bad = s['bad']
    lines, lh = layout(bad, 54, W - 2 * M)[0], 74
    for ln in lines:
        t = ' '.join(w for w, b, g in ln)
        tw = of.getlength(t)
        x = (W - tw) / 2
        d.text((x, y), t, font=of, fill=MUTED)
        d.line([x - 10, y + 40, x + tw + 10, y + 34], fill=DRED, width=7)
        y += lh
    if s.get('new') is False:
        return
    y += 70
    d.polygon([(W / 2 - 34, y), (W / 2 + 34, y), (W / 2, y + 44)], fill=GREEN)
    y += 90
    sz, ln, lh2 = fit(s['good'], W - 2 * M - 100, H - FOOT - y - 160, 64, 40, 700)
    box_h = len(ln) * lh2 + 100
    d.rounded_rectangle([M, y, W - M, y + box_h], 28, fill=GREEN_BG, outline=GREEN, width=3)
    draw_lines(d, M + 50, y + 50, sz, ln, lh2, weight=700, align='center', width=W - 2 * M - 100)


KINDS = {'versus': s_versus, 'question': s_question, 'cover': s_cover, 'text': s_text, 'cards': s_cards, 'fix': s_fix, 'keys': s_keys, 'end': s_end}


def main():
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    slides = json.loads(src.read_text(encoding='utf-8'))
    root = Path.cwd()
    out.mkdir(parents=True, exist_ok=True)
    files = []
    for n, s in enumerate(slides, 1):           # сначала всё нарисовать — при ошибке ничего не пишем
        im, d = base(n, 0 if any('say' in x for x in slides) else len(slides))
        KINDS[s['type']](im, d, s, root)
        files.append(im)
    for n, im in enumerate(files, 1):
        im.save(out / f'{n:02d}.png')
    cols = 5
    th = [im.resize((216, 270)) for im in files]
    rows = (len(th) + cols - 1) // cols
    sheet = Image.new('RGB', (cols * 226 + 10, rows * 280 + 10), '#ddd6cc')
    for i, t in enumerate(th):
        sheet.paste(t, (10 + (i % cols) * 226, 10 + (i // cols) * 280))
    sheet.save(out / 'contact-sheet.png')
    print(f'слайдов: {len(files)} -> {out}')


if __name__ == '__main__':
    main()
