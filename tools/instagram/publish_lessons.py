"""Готовые ролики -> сайт: сжатие для веба, длительность, запись в src/data/lessons.json.

    python tools\\instagram\\publish_lessons.py [--only <id>...]   (из work/Site)

Уроки — в LESSONS ниже: ролик work/NEWS/video/<папка>/film.mp4 сжимается в
public/videos/lessons/<id>.mp4 (720×1280, ~1–2 МБ). Обложки <id>-bubble.webp и <id>-poster.webp
должны уже лежать там же. Порядок в списке = порядок на сайте. Урок попадает на сайт,
только если его id в PUBLISHED: готовый, но не одобренный Олегом ролик ждёт здесь.
"""
import json
import subprocess
from pathlib import Path

NEWS = Path('../NEWS/video')
OUT = Path('public/videos/lessons')
COPPER = '2026-10-15-copper-ginger-peach'
BRASS = '2026-10-15-neutralize-brassiness-toning'
# id, папка ролика, статья, название, подпись, дата
LESSONS = [
    ('copper-01-peach', '2026-10-15-copper-01-peach', COPPER, 'Хотела персик — получила медь', 'Правильный вопрос клиентке и формулы персика для Koleston, Igora, Londa, Matrix', '2026-10-17'),
    ('copper-02-bordo', '2026-10-15-copper-02-bordo', COPPER, 'Медь на тёмной базе ушла в бордовый', 'Когда осветлять, как погасить красный фон и оттенки глубокой меди', '2026-10-17'),
    ('copper-03-flat', '2026-10-15-copper-03-flat', COPPER, 'Ярко, но плоско', 'Почему медь вышла плоским оранжевым и два тона для глубины', '2026-10-17'),
    ('copper-04-translate', '2026-10-15-copper-04-translate', COPPER, '«Хочу медный» — а цветов три', 'Медь, имбирь или персик: один вопрос клиентке и формулы Londa', '2026-10-17'),
    ('copper-05-quiz', '2026-10-15-copper-05-quiz', COPPER, 'Угадай за 3 секунды: где персик?', 'Медь, имбирь и персик на глаз — и формула персика Koleston', '2026-10-17'),
    ('copper-06-ginger', '2026-10-15-copper-06-ginger', COPPER, 'Формула дня: имбирь на семёрке', 'Мягкий и яркий имбирь для Koleston, Igora, Londa, Matrix', '2026-10-17'),
    ('copper-07-grey', '2026-10-15-copper-07-grey', COPPER, 'Медь на седине', 'Сколько натурального тона: Koleston и Igora Royal', '2026-10-17'),
    ('copper-08-fading', '2026-10-15-copper-08-fading', COPPER, 'Медь ушла за две недели', 'Что делать в салоне и дома, чтобы медь держалась', '2026-10-17'),
    ('brass-01-purple', '2026-10-15-brass-01-purple', BRASS, 'Фиолетовый не берёт рыжину', 'Рыжина 5–6 уровня: синие и пепельные оттенки Color Touch, Londa, Super Sync', '2026-10-17'),
    ('brass-02-yellow', '2026-10-15-brass-02-yellow', BRASS, 'Соломенная желтизна после осветления', 'Желтизна 8–9 уровня: фиолетовые оттенки Color Touch, Londa, Super Sync', '2026-10-17'),
    ('brass-03-green', '2026-10-15-brass-03-green', BRASS, 'После тонирования волосы позеленели', 'Почему так вышло, как не допустить и что делать', '2026-10-17'),
    ('brass-04-wella', '2026-10-15-brass-04-wella', BRASS, 'Тепло не уходит: формула Wella', '40 г Color Touch + 5 г Special Mix 0/68 + 90 г эмульсии', '2026-10-17'),
    ('brass-05-icy', '2026-10-15-brass-05-icy', BRASS, 'Ледяной блонд без желтизны', 'Matrix Tonal Control: 1 : 1, 3%, 20 минут и оттенки', '2026-10-17'),
]
# На сайте — только одобренные Олегом. Серия о рыжине ждёт его просмотра (17.10.2026).
PUBLISHED = {l[0] for l in LESSONS if l[0].startswith(('copper-', 'brass-'))}   # рыжина одобрена Олегом 17.10.2026


def dur(f):
    return float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(f)],
                                capture_output=True, text=True, check=True).stdout)


def main():
    out = []
    for lid, folder, article, title, sub, date in LESSONS:
        if lid not in PUBLISHED:
            print(f'{lid}: ждёт одобрения — на сайт не идёт')
            continue
        src = NEWS / folder / 'film.mp4'
        web = OUT / f'{lid}.mp4'
        poster = OUT / f'{lid}-poster.webp'               # постер — кадр самого ролика (с шапкой ZILMA)
        if src.exists() and (not poster.exists() or poster.stat().st_mtime < src.stat().st_mtime):
            subprocess.run(['ffmpeg', '-y', '-v', 'error', '-ss', '1.3', '-i', str(src), '-frames:v', '1',
                            '-vf', 'scale=540:960', '-q:v', '80', str(poster)], check=True)
        for need in (src, OUT / f'{lid}-bubble.webp', OUT / f'{lid}-poster.webp'):
            if not need.exists():
                raise SystemExit(f'нет файла: {need}')
        if not web.exists() or web.stat().st_mtime < src.stat().st_mtime:
            subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', str(src), '-vf', 'scale=720:1280', '-c:v', 'libx264', '-crf', '27',
                            '-preset', 'slow', '-profile:v', 'main', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '96k', '-ac', '1',
                            '-movflags', '+faststart', str(web)], check=True)
        out.append({'id': lid, 'title': title, 'subtitle': sub, 'article': article,
                    'video': f'/videos/lessons/{lid}.mp4', 'poster': f'/videos/lessons/{lid}-poster.webp',
                    'bubble': f'/videos/lessons/{lid}-bubble.webp', 'duration': round(dur(src)), 'date': date})
        print(f'{lid}: {round(dur(src))} с, {web.stat().st_size / 1048576:.1f} МБ')
    Path('src/data/lessons.json').write_text(json.dumps(out, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print('lessons.json: уроков', len(out))


if __name__ == '__main__':
    main()
