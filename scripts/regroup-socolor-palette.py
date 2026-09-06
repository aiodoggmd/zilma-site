# -*- coding: utf-8 -*-
"""
Пересобирает группы и порядок в matrix-socolor-shades.json.

Было: все 156 оттенков одной плоской группой, отсортированные по алфавиту кода —
«10AV, 10N, 11A, 11N, 11P, 1N, 2N...». Для колориста это шум: рядом стоят оттенки
разной глубины, а самое важное различие вообще не видно.

Стало: три группы, ровно те, что у бренда официально РАЗНЫЕ по технике смешивания —
и это единственная группировка, которая экономит мастеру время:
  * Основная коллекция     — 1:1 с крем-оксидантом Matrix
  * Extra Coverage (5xx)   — 1:1 с 6%, для седины больше 50%
  * Ultra Blond (UL-)      — 1:2 с 9% или 12%
Внутри группы сортировка по глубине тона, затем по буквам — как в карте прядей.

Запуск: .venv/Scripts/python.exe scripts/regroup-socolor-palette.py
"""
import json
import re
from pathlib import Path

PATH = Path(__file__).resolve().parent.parent / 'src' / 'data' / 'matrix-socolor-shades.json'


def classify(code: str) -> str:
    if code.upper().startswith('UL'):
        return 'ultra'
    # Extra Coverage — трёхзначные коды 5xx: 504N, 510G и т.п.
    if re.match(r'^5\d\d', code):
        return 'extra'
    return 'main'


def sort_key(code: str):
    """Глубина тона числом, потом буквенное отражение. UL идёт последним внутри своей группы."""
    m = re.match(r'^(?:UL-)?(\d+)?([A-Za-z+]*)$', code.strip())
    if not m:
        return (999, code)
    depth = m.group(1)
    letters = m.group(2) or ''
    if depth is None:
        return (0, letters)
    d = int(depth)
    # у Extra Coverage глубина зашита в последние две цифры: 504 -> 4, 510 -> 10
    if d >= 500:
        d = d - 500
    return (d, letters)


def main() -> None:
    shades = json.loads(PATH.read_text(encoding='utf-8'))
    for s in shades:
        s['group'] = classify(s['code'])

    order = {'main': 0, 'extra': 1, 'ultra': 2}
    shades.sort(key=lambda s: (order[s['group']], sort_key(s['code'])))

    # col задаёт порядок внутри группы (см. ShadeSwatchGrid: плоские группы сортируются по col)
    counters = {}
    for s in shades:
        g = s['group']
        s['row'] = 0
        s['col'] = counters.get(g, 0)
        counters[g] = s['col'] + 1

    PATH.write_text(json.dumps(shades, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')

    for g, label in (('main', 'Основная коллекция'), ('extra', 'Extra Coverage'), ('ultra', 'Ultra Blond')):
        items = [s for s in shades if s['group'] == g]
        with_price = sum(1 for s in items if s.get('name'))
        print('  %-20s %3d оттенков | в прайсе %3d | первые: %s'
              % (label, len(items), with_price, ', '.join(s['code'] for s in items[:6])))


if __name__ == '__main__':
    main()
