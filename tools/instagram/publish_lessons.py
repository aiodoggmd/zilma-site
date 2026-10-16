"""Готовые ролики -> сайт: сжатие для веба, длительность, запись в src/data/lessons.json.

    python tools\\instagram\\publish_lessons.py            (из work/Site)

Берёт уроки из LESSONS ниже: ролик work/NEWS/video/<папка>/film.mp4 сжимается в
public/videos/lessons/<id>.mp4 (720×1280, ~2 МБ). Обложки <id>-bubble.webp и <id>-poster.webp
должны уже лежать там же. Порядок в списке = порядок на сайте.
"""
import json
import subprocess
from pathlib import Path

NEWS = Path('../NEWS/video')
OUT = Path('public/videos/lessons')
ARTICLE = '2026-10-15-copper-ginger-peach'
LESSONS = [
    ('copper-01-peach', 'Хотела персик — получила медь', 'Правильный вопрос клиентке и формулы персика для Koleston, Igora, Londa, Matrix'),
    ('copper-02-bordo', 'Медь на тёмной базе ушла в бордовый', 'Когда осветлять, как погасить красный фон и оттенки глубокой меди'),
    ('copper-03-flat', 'Ярко, но плоско', 'Почему медь вышла плоским оранжевым и два тона для глубины'),
    ('copper-04-translate', '«Хочу медный» — а цветов три', 'Медь, имбирь или персик: один вопрос клиентке и формулы Londa'),
    ('copper-05-quiz', 'Угадай за 3 секунды: где персик?', 'Медь, имбирь и персик на глаз — и формула персика Koleston'),
    ('copper-06-ginger', 'Формула дня: имбирь на семёрке', 'Мягкий и яркий имбирь для Koleston, Igora, Londa, Matrix'),
    ('copper-07-grey', 'Медь на седине', 'Сколько натурального тона: Koleston и Igora Royal'),
    ('copper-08-fading', 'Медь ушла за две недели', 'Что делать в салоне и дома, чтобы медь держалась'),
]


def dur(f):
    return float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(f)],
                                capture_output=True, text=True, check=True).stdout)


def main():
    out = []
    for lid, title, sub in LESSONS:
        src = NEWS / lid.replace('copper-', '2026-10-15-copper-') / 'film.mp4'
        web = OUT / f'{lid}.mp4'
        for need in (src, OUT / f'{lid}-bubble.webp', OUT / f'{lid}-poster.webp'):
            if not need.exists():
                raise SystemExit(f'нет файла: {need}')
        if not web.exists() or web.stat().st_mtime < src.stat().st_mtime:
            subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', str(src), '-vf', 'scale=720:1280', '-c:v', 'libx264', '-crf', '27',
                            '-preset', 'slow', '-profile:v', 'main', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '96k', '-ac', '1',
                            '-movflags', '+faststart', str(web)], check=True)
        out.append({'id': lid, 'title': title, 'subtitle': sub, 'article': ARTICLE,
                    'video': f'/videos/lessons/{lid}.mp4', 'poster': f'/videos/lessons/{lid}-poster.webp',
                    'bubble': f'/videos/lessons/{lid}-bubble.webp', 'duration': round(dur(src)), 'date': '2026-10-17'})
        print(f'{lid}: {round(dur(src))} с, {web.stat().st_size / 1048576:.1f} МБ')
    Path('src/data/lessons.json').write_text(json.dumps(out, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print('lessons.json: уроков', len(out))


if __name__ == '__main__':
    main()
