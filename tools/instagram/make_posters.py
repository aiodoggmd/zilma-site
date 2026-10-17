"""Обложки уроков 9:16 (как у Shorts/Reels): фото на весь кадр, затемнение снизу, крупное название,
кнопка «плей» по центру, логотип ZILMA сверху. Постер ролика = обложка карточки на /lessons/.

    python tools\\instagram\\make_posters.py        (из work/Site)

Раньше постером был первый кадр ролика — почти пустой бежевый фон, и казалось, что ролик
не загрузился (Олег, 17.10.2026).
"""
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageOps

sys.path.insert(0, str(Path(__file__).parent))
from render_carousel import font, fit, draw_lines  # noqa: E402

W, H = 540, 960
OUT = Path('public/videos/lessons')
C = 'public/images/articles/2026-10-15-copper-ginger-peach/'
B = 'public/images/articles/2026-10-15-neutralize-brassiness-toning/cover-kling.webp'
# фото и точка фокуса по горизонтали (0..1) для каждого урока
PHOTO = {
    'copper-01-peach': (C + 'family-peach.webp', 0.5),
    'copper-02-bordo': (C + 'family-copper.webp', 0.5),
    'copper-03-flat': (C + 'cover.webp', 0.35),
    'copper-04-translate': (C + 'cover.webp', 0.55),
    'copper-05-quiz': (C + 'family-strawberry.webp', 0.5),
    'copper-06-ginger': (C + 'family-ginger.webp', 0.5),
    'copper-07-grey': (C + 'bowls.webp', 0.5),
    'copper-08-fading': (C + 'fading.webp', 0.5),
    'brass-01-purple': (B, 0.15),
    'brass-02-yellow': (B, 0.35),
    'brass-03-green': (B, 0.55),
    'brass-04-wella': (B, 0.78),
    'brass-05-icy': (B, 0.92),
}


def poster(lesson):
    src, fx = PHOTO[lesson['id']]
    img = ImageOps.fit(Image.open(src).convert('RGB'), (W, H), centering=(fx, 0.5))
    # затемнение снизу — чтобы белый текст читался на любой фотографии
    grad = Image.new('L', (1, H))
    for y in range(H):
        grad.putpixel((0, y), int(235 * max(0.0, (y - H * 0.42) / (H * 0.58)) ** 1.3))
    dark = Image.new('RGB', (W, H), (20, 12, 10))
    img = Image.composite(dark, img, grad.resize((W, H)))
    top = Image.new('L', (1, H))
    for y in range(H):
        top.putpixel((0, y), int(150 * max(0.0, 1 - y / 160)))
    img = Image.composite(dark, img, top.resize((W, H)))
    d = ImageDraw.Draw(img)
    # логотип
    f = font('serif', 40, 700)
    t = 'ZILMA'
    sp = 5
    tw = sum(f.getlength(c) for c in t) + sp * (len(t) - 1)
    x = (W - tw) / 2
    for c in t:
        d.text((x, 26), c, font=f, fill='#ffffff')
        x += f.getlength(c) + sp
    # кнопка «плей»
    cx, cy, r = W // 2, int(H * 0.40), 52
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(200, 0, 15))
    d.polygon([(cx - 16, cy - 26), (cx - 16, cy + 26), (cx + 28, cy)], fill='#ffffff')
    # длительность и название
    m = 30
    lab = font('sans', 22, 700)
    dur = f"УРОК · {lesson['duration'] // 60}:{lesson['duration'] % 60:02d}"
    d.text((m, H - 300), dur, font=lab, fill='#f2b27a')
    s, lines, lh = fit(lesson['title'], W - 2 * m, 230, 48, 30, 700, 'serif')
    draw_lines(d, m, H - 262, s, lines, lh, color='#ffffff', weight=700, kind='serif', width=W - 2 * m)
    return img


def main():
    lessons = json.loads(Path('src/data/lessons.json').read_text(encoding='utf-8'))
    for l in lessons:
        poster(l).save(OUT / f"{l['id']}-poster.webp", quality=82)
        print(l['id'], 'ok')


if __name__ == '__main__':
    main()
