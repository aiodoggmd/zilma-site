"""
Конвертирует прайс-лист (public/prices/price-current.xlsx) в структурированные данные
для интерактивного списка на сайте (src/data/priceItems.json).

Запуск при каждом обновлении прайса: python scripts/xlsx-to-price-items.py
Формат исходника: колонка B — название бренда/линейки (строка-заголовок) или товара,
колонка C — цена, колонка D — единица измерения.

Заголовки — два уровня, различаются заливкой ячейки (индексированный цвет Excel):
  - indexed=8  (чёрный) — бренд (напр. WELLA, SCHWARZKOPF)
  - indexed=22 (серый)  — линейка внутри бренда (напр. OSIS, SILHOUETTE)
Товары, выделенные красным шрифтом в Excel, помечаются promo: true (для блока «Акции»).
"""
import json
import re
from datetime import date, timedelta
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent.parent
SRC_XLSX = ROOT / "public" / "prices" / "price-current.xlsx"
OUT_JSON = ROOT / "src" / "data" / "priceItems.json"
# Сайдкар из build_price_current.py (Price/ - в .gitignore, не деплоится): старая цена
# и скидка по каждому акционному товару - price-current.xlsx хранит только цену со
# скидкой, старая цена иначе теряется. Файла может не быть (напр. кто-то прогнал этот
# скрипт отдельно, без пересборки прайса) - тогда просто не добавляем oldPrice/discountPct.
PROMO_META_PATH = ROOT / "Price" / "promo-meta.json"
# Ведётся В РЕПОЗИТОРИИ (не в Price/, который локальный и в .gitignore) - в отличие от
# промо-сайдкара, это НАКАПЛИВАЕМЫЙ журнал "когда товар впервые встретился в прайсе",
# должен пережить любую пересборку и не потеряться со сменой машины/сессии. Формат:
# {имя_товара: "YYYY-MM-DD" первого появления}. НЕ удалять и не редактировать руками -
# один раз потерянный файл заставит все текущие товары ошибочно выглядеть "новыми".
FIRST_SEEN_PATH = ROOT / "src" / "data" / "price-first-seen.json"
NEW_WINDOW_DAYS = 14

BRAND_FILL_INDEX = 8
LINE_FILL_INDEX = 22

# Служебные строки 1С (не товар) - никогда не должны попадать в каталог сайта.
# См. Site/CLAUDE.md / Site/Price/build_price_current.py (та же логика, зафиксировано 2026-08-25).
EXCLUDE_NAME_PREFIXES = ["доставка"]
EXCLUDE_NAME_SUBSTRINGS = ["мятая", "мятые"]  # брак/мятая упаковка
EXCLUDE_ARTICLES = {"007927"}
JUNK_SECTION_SUFFIXES = ("_акция",)  # секции вроде "Wella_Акция"/"Londa_Акция" - клиренс без цены


def article(name: str):
    toks = name.strip().split()
    return toks[-1] if toks else None


def is_excluded(name: str) -> bool:
    n = name.strip().lower()
    if any(n.startswith(p) for p in EXCLUDE_NAME_PREFIXES):
        return True
    if any(s in n for s in EXCLUDE_NAME_SUBSTRINGS):
        return True
    if article(name) in EXCLUDE_ARTICLES:
        return True
    return False


def is_junk_section_header(name: str) -> bool:
    n = name.strip().lower()
    return any(n.endswith(suf) for suf in JUNK_SECTION_SUFFIXES)


def is_red(cell) -> bool:
    try:
        rgb = cell.font.color.rgb
        return isinstance(rgb, str) and rgb.upper().endswith("FF0000")
    except Exception:
        return False


def header_level(cell) -> str:
    """Возвращает 'brand', 'line' или 'unknown' по заливке ячейки-заголовка."""
    fg = cell.fill.fgColor
    if fg.type == "indexed":
        if fg.indexed == BRAND_FILL_INDEX:
            return "brand"
        if fg.indexed == LINE_FILL_INDEX:
            return "line"
    return "unknown"


def main() -> None:
    promo_meta = {}
    if PROMO_META_PATH.exists():
        promo_meta = json.loads(PROMO_META_PATH.read_text(encoding="utf-8"))
    else:
        print(f"ВНИМАНИЕ: сайдкар {PROMO_META_PATH} не найден - акционные товары останутся без oldPrice/discountPct.")

    today = date.today()
    is_bootstrap = not FIRST_SEEN_PATH.exists()
    first_seen = {} if is_bootstrap else json.loads(FIRST_SEEN_PATH.read_text(encoding="utf-8"))
    # При самом первом запуске (файла ещё нет) весь текущий прайс - не "новинки", а то,
    # что уже давно продаётся, просто мы только сейчас начали это отслеживать. Ставим
    # дату заведомо за пределами окна NEW_WINDOW_DAYS, а не сегодняшнюю.
    bootstrap_date = (today - timedelta(days=NEW_WINDOW_DAYS + 1)).isoformat()
    if is_bootstrap:
        print(f"Первый запуск - журнал новинок {FIRST_SEEN_PATH} создаётся, текущий прайс новинками не считается.")

    wb = openpyxl.load_workbook(SRC_XLSX, data_only=True)
    ws = wb.active

    items = []
    brand = None
    line = None
    idx = 0
    unknown_headers = []
    in_junk_section = False
    for row in ws.iter_rows(min_row=6):
        name_cell = row[1] if len(row) > 1 else None
        price_cell = row[2] if len(row) > 2 else None
        unit_cell = row[3] if len(row) > 3 else None
        if name_cell is None or name_cell.value is None:
            continue
        name = str(name_cell.value).strip()
        if not name:
            continue
        if is_excluded(name):
            continue
        price = price_cell.value if price_cell else None
        unit = unit_cell.value if unit_cell else None

        # Настоящий заголовок (бренд/линейка): нет ни цены, ни единицы измерения.
        if (price is None or not isinstance(price, (int, float))) and unit is None:
            if is_junk_section_header(name):
                in_junk_section = True
            else:
                in_junk_section = False
                level = header_level(name_cell)
                if level == "brand":
                    brand = name
                    line = None
                elif level == "line":
                    line = name
                else:
                    # Неопознанная заливка — считаем брендом (безопаснее, чем потерять товары внутри).
                    unknown_headers.append(name)
                    brand = name
                    line = None
            continue

        # Товар без цены (в т.ч. внутри мусорной секции выше) - пропускаем, не заголовок и не товар.
        if price is None or not isinstance(price, (int, float)):
            continue
        if in_junk_section:
            continue

        promo = is_red(name_cell) or (price_cell is not None and is_red(price_cell))
        idx += 1
        # round() убирает артефакты двоичного float (напр. 998.5799999999999 -> 998.58)
        price_rounded = round(float(price), 2)
        clean_name = re.sub(r"\s+", " ", name)
        item = {
            "id": idx,
            "brand": brand,
            "line": line,
            "name": clean_name,
            "price": int(price_rounded) if price_rounded.is_integer() else price_rounded,
            "promo": promo,
        }
        if promo:
            meta = promo_meta.get(clean_name)
            if meta:
                old_price = round(float(meta["old_price"]), 2)
                item["oldPrice"] = int(old_price) if old_price.is_integer() else old_price
                item["discountPct"] = meta["discount"]

        seen_date = first_seen.get(clean_name)
        if seen_date is None:
            seen_date = bootstrap_date if is_bootstrap else today.isoformat()
            first_seen[clean_name] = seen_date
        if (today - date.fromisoformat(seen_date)).days <= NEW_WINDOW_DAYS:
            item["isNew"] = True

        items.append(item)

    FIRST_SEEN_PATH.write_text(json.dumps(first_seen, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    OUT_JSON.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    promo_count = sum(1 for i in items if i["promo"])
    with_old_price = sum(1 for i in items if i.get("oldPrice") is not None)
    new_count = sum(1 for i in items if i.get("isNew"))
    print(f"Сохранено {len(items)} товаров ({promo_count} акционных, из них {with_old_price} со старой ценой; {new_count} новинок за последние {NEW_WINDOW_DAYS} дн.) -> {OUT_JSON}")
    if promo_count and with_old_price < promo_count:
        print(f"ВНИМАНИЕ: {promo_count - with_old_price} акционных товаров не нашлись в сайдкаре по имени - проверить.")
    if unknown_headers:
        print(f"ВНИМАНИЕ: {len(unknown_headers)} заголовков с нераспознанной заливкой (взяты как бренд): {unknown_headers}")


if __name__ == "__main__":
    main()
