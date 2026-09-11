#!/usr/bin/env python3
"""Сводка по синхронизации прайса со статьями — прогонять сразу после
xlsx-to-price-items.py, перед пушем (ничего не чинит и не пишет файлы).

Зачем: цены/акции/наличие в статьях подтягиваются из src/data/priceItems.json
САМИ, без ручных правок — двумя независимыми механизмами:
  1. Палитры оттенков (ShadeSwatchGrid) — resolveLiveShade() в
     src/lib/resolve-live-price.ts, срабатывает на каждой СБОРКЕ сайта
     (import priceItems.json как обычный JS-модуль).
  2. Товарные таблицы статей (.kit-table, кнопки "+ В заявку") — initLivePrices()
     в src/pages/articles/[id].astro, срабатывает в БРАУЗЕРЕ при каждой загрузке
     страницы (сверяет data-name/data-price с #price-lookup-data, тем же
     priceItems.json, встроенным в страницу при сборке).

Этот скрипт не подменяет ни один из механизмов — он просто заранее показывает,
к чему они приведут (сколько оттенков станет недоступно, что реально пропало
из прайса и т.п.), чтобы не выяснять это руками через grep/DevTools каждый раз
и не пугаться "расхождений", которые сайт и так исправит сам.

Запуск: python scripts/verify-price-sync.py   (из папки Site, без аргументов)
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARTICLE_PAGE = ROOT / "src/pages/articles/[id].astro"
DATA_DIR = ROOT / "src/data"
ARTICLES_DIR = ROOT / "src/content/articles"


def article_of(name: str) -> str:
    """Тот же приём, что в src/lib/article-key.ts: последний пробельный токен
    1С-имени — это артикул."""
    toks = name.strip().split()
    return toks[-1].rstrip(".") if toks else ""


def base_article(token: str) -> str:
    """Составной код («4669-3891») — след ребрендинга, актуален первый номер.
    Обе части не короче трёх цифр: «010-7» у OLLIN — это код оттенка, не ребрендинг.
    Порт с src/lib/article-key.ts, держать в согласии с ним."""
    m = re.fullmatch(r"(\d{3,10})[-/]\d{3,10}", token)
    return m.group(1) if m else token


def build_price_index(items):
    """(бренд, артикул) -> товар, либо AMBIGUOUS если внутри бренда два товара
    делят один ключ. Возвращает ФУНКЦИЮ поиска: точные совпадения проверяются
    раньше запасных (по первой части составного кода), как в article-key.ts."""
    AMBIGUOUS = object()
    exact: dict = {}
    alias: dict = {}

    def put(store, brand, key, item):
        store.setdefault(brand, {})
        store[brand][key] = AMBIGUOUS if key in store[brand] else item

    for it in items:
        brand = it["brand"].upper()
        token = article_of(it["name"])
        put(exact, brand, token, it)
        base = base_article(token)
        if base != token:
            put(alias, brand, base, it)

    def find(brand, key):
        b = (brand or "").upper()
        k = (key or "").strip().rstrip(".")
        hit = exact.get(b, {}).get(k)
        if hit is not None:
            return hit
        hit = alias.get(b, {}).get(k)
        if hit is not None:
            return hit
        base = base_article(k)
        return exact.get(b, {}).get(base) if base != k else None

    return find, AMBIGUOUS


def parse_shade_brand_map(astro_src: str):
    """Достаёт {data-файл: бренд} прямо из [id].astro (import ... + resolveLiveShades(...)),
    чтобы список линеек не пришлось вручную дублировать и синхронизировать здесь."""
    imports = dict(re.findall(r"import (\w+) from '\.\./\.\./data/([\w-]+\.json)';", astro_src))
    resolves = re.findall(r"const (\w+) = resolveLiveShades\((\w+), '(\w+)'\);", astro_src)
    result = {}
    for _out_name, raw_name, brand in resolves:
        fname = imports.get(raw_name)
        if fname:
            result[fname] = brand
    return result


def check_palettes(find, AMBIGUOUS):
    astro_src = ARTICLE_PAGE.read_text(encoding="utf-8")
    brand_map = parse_shade_brand_map(astro_src)
    if not brand_map:
        print("  ! Не нашёл ни одной линейки в [id].astro — проверь регэксп в скрипте "
              "(возможно, поменялась структура импортов/resolveLiveShades).")
        return

    print(f"Палитры оттенков ({len(brand_map)} линеек, из [id].astro):")
    for fname, brand in sorted(brand_map.items()):
        path = DATA_DIR / fname
        if not path.exists():
            print(f"  ! {fname} — файла нет на диске, но есть импорт в [id].astro")
            continue
        shades = json.loads(path.read_text(encoding="utf-8"))
        total = len(shades)
        had_name = sum(1 for s in shades if s.get("name"))
        will_be_unavailable = 0
        ambiguous = 0
        for s in shades:
            name = s.get("name")
            if not name:
                continue
            live = find(brand, article_of(name))
            if live is AMBIGUOUS:
                ambiguous += 1
            elif live is None:
                will_be_unavailable += 1
        note = f", {ambiguous} неоднозначных (не трогаются)" if ambiguous else ""
        print(f"  {fname:<28} {brand:<12} {total} оттенков, "
              f"{had_name - will_be_unavailable}/{had_name} с ценой останутся доступны"
              f"{note}")


def check_kit_tables(find, AMBIGUOUS):
    row_pat = re.compile(r"<tr>.*?</tr>", re.S)
    btn_pat = re.compile(
        r'class="cart-add-btn"[^>]*data-name="([^"]+)"[^>]*data-price="([^"]+)"[^>]*data-brand="([^"]+)"'
    )
    unavail_pat = re.compile(r'class="order-unavailable"[^>]*data-article="([^"]+)"[^>]*data-brand="([^"]+)"')
    badge_pat = re.compile(r"kit-promo-badge")

    print("\nТоварные таблицы статей (.kit-table, кнопки \"+ В заявку\"):")
    any_files = False
    for fp in sorted(ARTICLES_DIR.glob("*.md")):
        text = fp.read_text(encoding="utf-8")
        rows = list(row_pat.finditer(text))
        if not any(btn_pat.search(r.group(0)) or unavail_pat.search(r.group(0)) for r in rows):
            continue
        any_files = True
        will_become_available = 0
        will_become_unavailable = 0
        ambiguous = 0
        checked = 0
        for row in rows:
            row_html = row.group(0)
            m = btn_pat.search(row_html)
            if m:
                name_raw, _price_str, brand = m.groups()
                name = name_raw.replace("&quot;", '"')
                checked += 1
                live = find(brand, article_of(name))
                if live is AMBIGUOUS:
                    ambiguous += 1
                elif live is None:
                    will_become_unavailable += 1
                continue
            m = unavail_pat.search(row_html)
            if m:
                article, brand = m.groups()
                checked += 1
                live = find(brand, article)
                if live is AMBIGUOUS:
                    ambiguous += 1
                elif live is not None:
                    will_become_available += 1
        if checked == 0:
            continue
        flags = []
        if will_become_unavailable:
            flags.append(f"{will_become_unavailable} станут «Под заказ»/«Нет в наличии» на клиенте")
        if will_become_available:
            flags.append(f"{will_become_available} снова появятся в заявке")
        if ambiguous:
            flags.append(f"{ambiguous} неоднозначных (не трогаются)")
        suffix = " — " + "; ".join(flags) if flags else " — без изменений"
        print(f"  {fp.name:<45} {checked} позиций{suffix}")

    if not any_files:
        print("  (не найдено ни одной статьи с .kit-table)")

    print(
        "\n  Ничего из этого не требует правки markdown — initLivePrices() в [id].astro\n"
        "  делает это сам в браузере при загрузке страницы (LEBEL -> «Под заказ», иначе\n"
        "  -> «Нет в наличии»). Правь markdown вручную только если авторская цена/название\n"
        "  товара изменились настолько, что артикул (последний токен в data-name) больше\n"
        "  не совпадает — такое встречается редко и обычно означает опечатку при написании статьи."
    )


def main():
    price_items = json.loads((DATA_DIR / "priceItems.json").read_text(encoding="utf-8"))
    find, AMBIGUOUS = build_price_index(price_items)
    print(f"priceItems.json: {len(price_items)} позиций\n")
    check_palettes(find, AMBIGUOUS)
    check_kit_tables(find, AMBIGUOUS)


if __name__ == "__main__":
    main()
