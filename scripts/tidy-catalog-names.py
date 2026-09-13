# -*- coding: utf-8 -*-
"""
Причёсывает имена в Price/Каталог.xlsx: единицы измерения, опечатки, сокращения.

ГЛАВНАЯ ГАРАНТИЯ: последнее слово имени НЕ ТРОГАЕТСЯ НИКОГДА.
Сайт считает артикулом последний токен имени (resolve-live-price.ts), и любая
правка там рвёт связь товара с ценой, фото, категорией и кружком оттенка.
Поэтому имя режется на «тело» и «артикул», правится только тело.

ЧТО ДЕЛАЕТ
  1. Единицы измерения к одному виду — слитно, без точки: «300 мл.» -> «300мл».
     Так записано большинство (341 против 152 и 130), и так просил пользователь.
  2. Латинское «ml» -> «мл». Латиница внутри русского имени ломает поиск молча.
  3. Опечатки из заранее выверенного списка.
  4. Сокращения, у которых одно однозначное прочтение. Спорные НЕ трогает,
     а выписывает отдельным списком — решать человеку.
  5. Двойные пробелы и пробел перед запятой.

Запуск: python scripts/tidy-catalog-names.py [--apply]
Без --apply — предпросмотр. Перед записью делается копия файла.
"""
import re
import shutil
import sys
from collections import Counter
from datetime import date
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / 'Price' / 'Каталог.xlsx'

# --- 1. единицы измерения -------------------------------------------------
# Порядок важен: длинные раньше коротких, иначе «мл» разберётся как «л».
UNIT_RE = re.compile(r'(\d)\s*(мл|ml|мг|кг|гр|шт|г|л)\.?(?=$|[\s,;)/]|\d)', re.I)
UNIT_FIX = {'ml': 'мл'}

# --- 2. опечатки ----------------------------------------------------------
TYPOS = [
    (r'пепльный', 'пепельный'),
    (r'\bнормальный волос\b', 'нормальных волос'),
    (r'прикорнивой', 'прикорневой'),
    (r'\bобъма\b', 'объёма'),
    (r'\bобема\b', 'объёма'),
    (r'\bобьема\b', 'объёма'),
    (r'\bобьём\b', 'объём'),
    (r'\bобьем\b', 'объём'),
    (r'\bобъем\b', 'объём'),
    (r'\bобъема\b', 'объёма'),
    (r'\bддя\b', 'для'),
    (r'перлпмутр\.?', 'перламутровый'),
    (r'\bcursl\b', 'curls'),
    (r'\bтеплозащ\b', 'теплозащитный'),
    (r'!!!', ''),
]

# --- 3. сокращения с одним прочтением ------------------------------------
ABBR = [
    # Составные — строго раньше одиночных, иначе «медн.зол» станет «медный зол».
    (r'\bмедн\.зол\b', 'медно-золотистый'),
    (r'\bкоричнево-зол\b', 'коричнево-золотистый'),
    (r'\bзолот-жемчужный\b', 'золотисто-жемчужный'),
    (r'\bд/', 'для '),
    (r'\bоч-оч\.\s*', 'очень-очень '),
    (r'\bоч\.\s*', 'очень '),
    (r'\bсв\.\s*', 'светлый '),
    (r'\bсветл\.\s*', 'светлый '),
    (r'\bтемн\.\s*', 'тёмный '),
    (r'\bинтенс\.\s*', 'интенсивный '),
    (r'\bСпец\.\s*', 'Специальный '),
    (r'\bспец\.\s*', 'специальный '),
    (r'\bмедн\.\s*', 'медный '),
    (r'\bфиол\.\s*', 'фиолетовый '),
    (r'\bжемчуж\.\s*', 'жемчужный '),
    (r'\bперламутр\.\s*', 'перламутровый '),
    (r'\bпепел\.\s*', 'пепельный '),
    (r'\bнатур\.\s*', 'натуральный '),
    (r'\bнат\.кор\.\s*', 'натуральный коричневый '),
    (r'\bпласт\.\s*', 'пластиковый '),
    (r'\bметалл\.\s*', 'металлический '),
    (r'\bочищ\.\s*', 'очищающий '),
    (r'\bстабилиз\.\s*', 'стабилизирующий '),
    (r'\bблонд\.\s*', 'блонд '),
    (r'\bп/э\b', 'полиэтиленовая'),
    (r'\bфиолет\.\s*', 'фиолетовый '),
    (r'\bпепельн\.\s*', 'пепельный '),
    (r'\bнатурал\.\s*', 'натуральный '),
    (r'\bкорич\.\s*', 'коричневый '),
    (r'\bпрозр\.\s*', 'прозрачные '),
    (r'\bгиалур\.\s*', 'гиалуроновой кислотой '),
    (r'\bзолот-', 'золотисто-'),
    (r'\bкоричнев\b(?!ый|ая|ое|ые|о-)', 'коричневый'),
    (r'\bзолот\b', 'золотистый'),
]

# Точка, слипшаяся со следующим словом или числом: «CLEAR.90мл», «прозр.100шт».
GLUED_RE = re.compile(r'([А-Яа-яA-Za-z])\.(?=[0-9А-ЯA-Z])')

# Запятая прямо перед объёмом: «...для укрепления волос, 1000мл».
COMMA_BEFORE_UNIT_RE = re.compile(
    r',\s*(?=\d+\s*(?:мл|ml|гр|г|л|кг|мг|шт)\b)', re.I)

# Слово (или пара слов) подряд дважды: «для всех типов волос волос»,
# «Светло-коричневый коричневый». Два из трёх случаев пришли из 1С, один —
# из ручной правки. Схлопываем в одно.
REPEAT_RE = re.compile(r'\b(\w+(?:\s+\w+)?)\s+\1\b', re.I)

# Десятичные дроби и коды оттенков: «1,9%», «рн 3,5», «IR 9,5-1».
# Ни одна правка не имеет права их разорвать.
DECIMAL_RE = re.compile(r'\d+,\d+')

# Спорные — их НЕ трогаем, только показываем.
UNSURE = re.compile(
    r'\b(гиалур\.|vol\.|медн\.зол|шампуня/масок|зол\b|фикс\.|см\.|'
    r'св\.шатен|оч\.светлый|проф\.|восстан\.)', re.I)


def split_article(name: str):
    """Тело имени и артикул. Артикул — последний токен, его не трогаем."""
    toks = name.split()
    if len(toks) < 2:
        return name, ''
    return ' '.join(toks[:-1]), toks[-1]


# Размеры — не объём: «35x70 см» читается лучше, чем «35x70см».
# Поэтому у сантиметров убираем только точку, пробел оставляем.
CM_RE = re.compile(r'(\d)\s*см\.', re.I)


def fix_units(s: str) -> str:
    def rep(m):
        unit = m.group(2)
        unit = UNIT_FIX.get(unit.lower(), unit.lower())
        return m.group(1) + unit
    s = CM_RE.sub(r'\1 см', s)
    return UNIT_RE.sub(rep, s)


def tidy(name: str):
    """Возвращает (новое имя, что именно применили)."""
    body, article = split_article(name)
    applied = []

    before = body
    body = fix_units(body)
    if body != before:
        applied.append('единицы')

    for pat, to in TYPOS:
        new = re.sub(pat, to, body, flags=re.I)
        if new != body:
            applied.append('опечатка')
            body = new

    for pat, to in ABBR:
        new = re.sub(pat, to, body)
        if new != body:
            applied.append('сокращение')
            body = new

    before = body
    body = GLUED_RE.sub(r'\1 ', body)
    if body != before:
        applied.append('слипшаяся точка')

    # Запятая перед объёмом — мусор, и ставится он хаотично: «для укрепления
    # волос, 1000мл» рядом с такими же именами без запятой.
    before = body
    body = REPEAT_RE.sub(r'\1', body)
    if body != before:
        applied.append('повтор слова')

    before = body
    body = COMMA_BEFORE_UNIT_RE.sub(' ', body)
    if body != before:
        applied.append('запятая перед объёмом')

    body = re.sub(r'\s+', ' ', body)
    body = re.sub(r'\s+([,;])', r'\1', body)
    # Пробел после запятой — ТОЛЬКО если дальше не цифра. Иначе рвутся
    # десятичные дроби и коды оттенков: «1,9%» -> «1, 9%», «IR 9,5-1» ->
    # «IR 9, 5-1». Поймано 13.09.2026 на собственной правке: проверки на
    # артикулы и дубли этого не видели.
    body = re.sub(r'([,;])(?=[^\s\d])', r'\1 ', body)
    body = body.strip(' ,;')

    out = (body + ' ' + article).strip() if article else body
    out = re.sub(r'\s+', ' ', out).strip()
    return out, sorted(set(applied))


def read_rows(ws):
    rows, brand = [], None
    for r in range(5, ws.max_row + 1):
        cell = ws.cell(row=r, column=2)
        if cell.value is None or not str(cell.value).strip():
            continue
        raw = str(cell.value).strip()
        size = cell.font.size if cell.font and cell.font.size else 0
        bold = bool(cell.font and cell.font.bold)
        is_caps = raw == raw.upper() and any(c.isalpha() for c in raw)
        if bold and is_caps and size >= 11:
            brand = raw
            continue
        if size >= 11:
            continue
        rows.append({'row': r, 'brand': brand, 'name': ' '.join(raw.split())})
    return rows


def main() -> None:
    apply = '--apply' in sys.argv
    wb = openpyxl.load_workbook(CATALOG)
    ws = wb['Sheet1']
    rows = read_rows(ws)
    print(f'Товарных строк: {len(rows)}')

    changes, kinds = [], Counter()
    for x in rows:
        new, applied = tidy(x['name'])
        if new != x['name']:
            changes.append((x, new, applied))
            for a in applied:
                kinds[a] += 1

    print(f'К правке: {len(changes)}')
    for k, n in kinds.most_common():
        print(f'  {k:<12} {n}')

    # --- ПРОВЕРКИ БЕЗОПАСНОСТИ ---
    bad_article = [(x, new) for x, new, _ in changes
                   if x['name'].split()[-1] != new.split()[-1]]
    after = [dict(x, name=new) for x, new, _ in changes] + \
            [x for x in rows if all(x['row'] != c[0]['row'] for c in changes)]
    dup = [n for n, c in Counter(a['name'].casefold() for a in after).items() if c > 1]

    # Дроби и коды оттенков должны уцелеть целиком. Без этой проверки правка
    # «1,9%» -> «1, 9%» проходит незамеченной: артикул на месте, дублей нет.
    broken = []
    for x, new, _ in changes:
        was = DECIMAL_RE.findall(x['name'])
        now = DECIMAL_RE.findall(new)
        if was != now:
            broken.append((x, new, was, now))

    print('\nПРОВЕРКИ:')
    print(f'  артикул изменился:      {len(bad_article)}   (должно быть 0)')
    print(f'  имена стали одинаковы:  {len(dup)}   (должно быть 0)')
    print(f'  разорваны дроби/коды:   {len(broken)}   (должно быть 0)')
    print(f'  строк было/стало:       {len(rows)}/{len(after)}')
    for x, new in bad_article[:5]:
        print(f'    ! стр.{x["row"]}: {x["name"]}  ->  {new}')
    for d in dup[:5]:
        print(f'    ! дубль: {d[:70]}')
    for x, new, was, now in broken[:5]:
        print(f'    ! стр.{x["row"]}: было {was} стало {now}')
        print(f'      {new[:74]}')
    if bad_article or dup or broken or len(after) != len(rows):
        sys.exit('\nПроверки не прошли — ничего не записано.')

    print('\nПРИМЕРЫ (первые 20):')
    for x, new, applied in changes[:20]:
        print(f'  стр.{x["row"]:<5} [{", ".join(applied)}]')
        print(f'      было:  {x["name"][:76]}')
        print(f'      стало: {new[:76]}')

    # Считаем по ИСПРАВЛЕННЫМ именам, иначе список врёт: показывает сокращения,
    # которые скрипт уже раскрыл.
    left = []
    for x in rows:
        new, _ = tidy(x['name'])
        body, _ = split_article(new)
        if UNSURE.search(body):
            left.append((x['row'], new))
    if left:
        print(f'\nСПОРНЫЕ СОКРАЩЕНИЯ — НЕ ТРОНУТЫ, решай сам ({len(left)}):')
        for r, n in left:
            print(f'  стр.{r:<5} {n[:74]}')

    if not changes:
        print('\nПравить нечего.')
        return

    if apply:
        backup = CATALOG.with_name(f'Каталог-до-правок-{date.today():%Y-%m-%d}.xlsx')
        if not backup.exists():
            shutil.copy2(CATALOG, backup)
        for x, new, _ in changes:
            ws.cell(row=x['row'], column=2).value = new
        wb.save(CATALOG)
        print(f'\nЗаписано: {len(changes)} имён. Копия до правок: {backup.name}')
    else:
        print('\nЭто предпросмотр, файл не изменён. Для записи — с --apply')


if __name__ == '__main__':
    main()
