# -*- coding: utf-8 -*-
"""
Дописывает в таблицы «Что заказать» статей позиции, которые поступили в продажу.

ЗАЧЕМ. Таблицу заказа в статье собирают один раз — из того, что есть в прайсе на день
написания. Цену и «нет в наличии» потом обновляет сайт сам (initLivePrices), а вот
оттенок, которого в тот день не было, в таблицу не попадает никогда: строки нет, и
поступления никто не видит. 16.10.2026 так «потерялись» Londa 6/, 7/, 8/.

КАК. Для статьи заводится список всех её позиций — и тех, что есть, и тех, что ждём:
src/data/article-kits/<slug>.json. Скрипт сверяет список с прайсом и в каждую таблицу
дописывает строки товаров, которые есть в прайсе, а в таблице ещё нет.
  - Уже стоящие строки не трогает и НЕ удаляет никогда: распроданный товар остаётся
    строкой, сайт сам покажет «нет в наличии».
  - Оттенок ищется через палитру (код -> имя товара): имя в палитре держит актуальным
    link-palette-shades.py, поэтому запускать ПОСЛЕ него.
  - Строку, уже стоящую в таблице, узнаёт и по имени, и по артикулу (последнее слово
    имени): переименование товара в 1С не даёт дубль.

Заодно сторож палитр: товар в разделе палитры, чьего кода в палитре нет вовсе (как 8/
у Londa) — предупреждение. Новый оттенок с фото добавляется руками.

МЕСТО В РИТУАЛЕ: после привязки палитр (update-price.py, шаг 7/8).
Запуск: python scripts/update-article-kits.py [--apply] [--all]
"""
import html
import importlib.util
import json
import re
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'src' / 'data'
ARTICLES = ROOT / 'src' / 'content' / 'articles'
KITS = DATA / 'article-kits'
META = ROOT / 'Price' / 'promo-meta.json'
WATCH_DAYS = 14     # сторож палитр смотрит только на свежие поступления; весь хвост — ключ --all

# Разбор кодов в именах товаров — тот же, что у привязки палитр, чтобы правила не разошлись.
_spec = importlib.util.spec_from_file_location('lps', ROOT / 'scripts' / 'link-palette-shades.py')
lps = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lps)


def money(x):
    s = f'{x:,.2f}'.replace(',', ' ').replace('.', ',')
    return s[:-3] if s.endswith(',00') else s


def article_no(name):
    """Артикул для колонки: «4652/714» -> 4652 (второе — след ребрендинга), но «0/7» — целиком."""
    last = name.split()[-1]
    first = last.split('/')[0]
    return last if first == '0' else first


def row_html(label, it, meta):
    n, price = it['name'], it['price']
    promo = bool(it.get('promo')) and n in meta
    cell = (f'<s class="kit-old-price">{money(meta[n]["old_price"])} ₽</s><b class="kit-price-now">{money(price)} ₽</b>'
            f'<span class="kit-promo-badge">Акция</span>') if promo else f'{money(price)} ₽'
    return (f'<tr><td>{html.escape(label)}</td><td>{html.escape(article_no(n))}</td><td class="col-price-cell">{cell}</td>'
            f'<td class="col-order-cell"><button type="button" class="cart-add-btn" data-name="{html.escape(n, quote=True)}" '
            f'data-price="{price:g}" data-brand="{it["brand"]}"{" data-promo=\"1\"" if promo else ""}>+ В заявку</button></td></tr>')


ROW_RE = re.compile(r'<tr>.*?</tr>', re.S)
NAME_RE = re.compile(r'data-name="([^"]+)"')


def find_table(text, heading):
    """(начало tbody, конец tbody) таблицы под заголовком «### heading»."""
    m = re.search(r'^### ' + re.escape(heading) + r'\s*\n\s*<div class="kit-table-wrap">', text, re.M)
    if not m:
        return None
    a = text.index('<tbody>', m.end()) + len('<tbody>')
    b = text.index('</tbody>', a)
    return a, b


COMMA_CODE = re.compile(r'\b\d{1,2},\d-\d{1,2}\b')    # Igora «9,5-22»: запятая — часть уровня


def palette_watch(items, since=None):
    """Товары раздела палитры, чьего кода в палитре нет вовсе. since — только появившиеся
    в прайсе с этой даты (по price-first-seen.json); None — все."""
    seen = json.loads((DATA / 'price-first-seen.json').read_text(encoding='utf-8'))
    name_sec = {i['name']: (i.get('brand'), i.get('section')) for i in items}
    out = []
    owner = Counter()
    pals = {}
    for f in lps.palette_files():
        shades = json.loads(f.read_text(encoding='utf-8'))
        if not isinstance(shades, list):
            continue
        votes = Counter(name_sec[s['name']] for s in shades if s.get('name') in name_sec)
        if votes:
            sec = votes.most_common(1)[0][0]
            pals[f.name] = (sec, {lps.norm_code(s['code']) for s in shades if s.get('code')},
                            {s.get('name') for s in shades})
            owner[sec] += 1
    for fname, (sec, codes, names) in pals.items():
        if owner[sec] > 1:          # раздел делят две палитры — товар не приписать
            continue
        for it in items:
            if (it.get('brand'), it.get('section')) != sec or it['name'] in names:
                continue
            if since and seen.get(it['name'], '') < since:
                continue
            got = lps.codes_in(it['name']) | {c.replace(',', '').replace('-', '') for c in COMMA_CODE.findall(it['name'])}
            if got and not (got & {c.replace(',', '') for c in codes}):
                out.append((fname, it['name']))
    return out


def main():
    apply = '--apply' in sys.argv
    items = json.loads((DATA / 'priceItems.json').read_text(encoding='utf-8'))
    by_name = {i['name']: i for i in items}
    by_art = {}
    for i in items:
        by_art.setdefault(i['name'].split()[-1], i)
    meta = json.loads(META.read_text(encoding='utf-8')) if META.exists() else {}

    plans, problems = [], []
    for kit_file in sorted(KITS.glob('*.json')):
        kit = json.loads(kit_file.read_text(encoding='utf-8'))
        art = ARTICLES / f"{kit['article']}.md"
        if not art.exists():                       # статья в черновиках — пропускаем молча
            continue
        text = art.read_text(encoding='utf-8')
        added = []
        for t in kit['tables']:
            pos = find_table(text, t['heading'])
            if not pos:
                problems.append(f"{kit['article']}: нет таблицы под заголовком «{t['heading']}»")
                continue
            a, b = pos
            body = text[a:b]
            have = set(NAME_RE.findall(body))
            have_art = {html.unescape(n).split()[-1] for n in have}
            pal = {}
            if t.get('palette'):
                pal = {s['code']: s for s in json.loads((DATA / f"{t['palette']}-shades.json").read_text(encoding='utf-8'))}
            wanted = []                            # (подпись, имя товара в палитре/списке)
            for c in t.get('codes', []):
                s = pal.get(c)
                if s is None:
                    problems.append(f"{kit['article']}: кода {c} нет в палитре {t['palette']}")
                    continue
                wanted.append((t['label'].format(c=c), s.get('name')))
            wanted += [(lab, n) for lab, n in t.get('extras', [])]
            rows = ROW_RE.findall(body)
            new_rows = list(rows)
            for k, (lab, n) in enumerate(wanted):
                it = by_name.get(n) if n else None
                if it is None and n:
                    it = by_art.get(n.split()[-1])     # товар переименовали в 1С
                if it is None:
                    continue                           # пока нет в продаже
                if html.escape(it['name'], quote=True) in have or it['name'].split()[-1] in have_art:
                    continue                           # уже в таблице
                # встать перед ближайшей следующей позицией списка, которая уже стоит в таблице
                at = len(new_rows)
                for lab2, n2 in wanted[k + 1:]:
                    if not n2:
                        continue
                    hit = next((j for j, r in enumerate(new_rows) if n2.split()[-1] in
                                {html.unescape(x).split()[-1] for x in NAME_RE.findall(r)}), None)
                    if hit is not None:
                        at = hit
                        break
                new_rows.insert(at, row_html(lab, it, meta))
                have_art.add(it['name'].split()[-1])
                added.append(f"{t['heading']}: {lab}")
            if len(new_rows) != len(rows):
                text = text[:a] + '\n' + '\n'.join(new_rows) + '\n' + text[b:]
        if added:
            plans.append((art, text, added))

    for p in problems:
        print('! ' + p)
    if not plans:
        print('Таблицы статей: дописывать нечего — всё, что есть в прайсе из списков статей, уже стоит.')
    for art, _, added in plans:
        print(f'{art.name}: появятся {len(added)}')
        for a in added:
            print('   + ' + a)

    since = None if '--all' in sys.argv else (date.today() - timedelta(days=WATCH_DAYS)).isoformat()
    watch = palette_watch(items, since)
    if watch:
        what = 'все товары' if since is None else f'поступили за {WATCH_DAYS} дней'
        print(f'\n! Оттенков нет в палитрах ({len(watch)}, {what}) — добавить с фото руками:')
        for f, n in watch:
            print(f'   {f:<34}{n}')

    if problems:
        sys.exit('СТОП: списки статей разошлись со статьями или палитрами — ничего не записано.')
    if apply:
        for art, text, _ in plans:
            art.write_text(text, encoding='utf-8')
        print(f'Записано статей: {len(plans)}.' if plans else '')
    elif plans:
        print('Это предпросмотр, статьи не изменены. Для записи — с --apply')


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
