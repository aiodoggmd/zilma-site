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
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent.parent
SRC_XLSX = ROOT / "public" / "prices" / "price-current.xlsx"
OUT_JSON = ROOT / "src" / "data" / "priceItems.json"

BRAND_FILL_INDEX = 8
LINE_FILL_INDEX = 22


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
    wb = openpyxl.load_workbook(SRC_XLSX, data_only=True)
    ws = wb.active

    items = []
    brand = None
    line = None
    idx = 0
    unknown_headers = []
    for row in ws.iter_rows(min_row=6):
        name_cell = row[1] if len(row) > 1 else None
        price_cell = row[2] if len(row) > 2 else None
        if name_cell is None or name_cell.value is None:
            continue
        name = str(name_cell.value).strip()
        if not name:
            continue
        price = price_cell.value if price_cell else None
        if price is None or not isinstance(price, (int, float)):
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
        promo = is_red(name_cell) or (price_cell is not None and is_red(price_cell))
        idx += 1
        # round() убирает артефакты двоичного float (напр. 998.5799999999999 -> 998.58)
        price_rounded = round(float(price), 2)
        items.append({
            "id": idx,
            "brand": brand,
            "line": line,
            "name": re.sub(r"\s+", " ", name),
            "price": int(price_rounded) if price_rounded.is_integer() else price_rounded,
            "promo": promo,
        })

    OUT_JSON.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    promo_count = sum(1 for i in items if i["promo"])
    print(f"Сохранено {len(items)} товаров ({promo_count} акционных) -> {OUT_JSON}")
    if unknown_headers:
        print(f"ВНИМАНИЕ: {len(unknown_headers)} заголовков с нераспознанной заливкой (взяты как бренд): {unknown_headers}")


if __name__ == "__main__":
    main()
