"""
Формирует деплойный прайс для сайта (price-current.xlsx) из двух исходников:
  - общий прайс (продажные цены)
  - остатки (себестоимость)

Методика — "вариант 2" (по марже, не по наценке):
  текущая маржа% = (цена - себестоимость) / цена * 100
  маржа >= 45%        -> скидка 15%
  35% <= маржа < 45%   -> скидка 10%
  30% <= маржа < 35%   -> скидка 5%
  маржа < 30%          -> скидка 0% (не акция)
  цена акции = цена * (1 - скидка/100)

Структура исходной таблицы сохраняется (бренд-заголовки, колонки
Наименование/Цена/Ед., объединённые ячейки). Акционные строки красятся
красным. Заголовок ценовой колонки меняется на "Цена".

Отдельный файл price-promo.xlsx больше НЕ формируется (убрано 2026-08-25) —
акционные товары и так видны прямо в общем прайсе (красным шрифтом) и в
каталоге на сайте (priceItems.json/xlsx-to-price-items.py читает promo
из этого же файла) - отдельный акционный прайс был чистым дублированием
одних и тех же данных, требовавшим ручной поддержки. Не возвращать этот
файл без явной новой просьбы пользователя.

Результат нужно проверить перед публикацией на сайт - файл не
задеплоивается автоматически.
"""
import openpyxl
from openpyxl.styles import Font, Border, Side, PatternFill, Alignment
from openpyxl.comments import Comment
from copy import copy
from collections import defaultdict, deque
import json
import os
import re
import sys

# Журнал категорий (в репозитории, src/data/ - не в Price/) - ведёт xlsx-to-price-items.py,
# накапливаемый "название товара -> номер категории 1-17" (см. Site/CLAUDE.md). Читаем его
# здесь, чтобы новый price-current.xlsx сразу приходил с уже известными категориями в
# колонке F - без этого пользователю пришлось бы каждый раз заново размечать весь прайс.
SITE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATEGORIES_PATH = os.path.join(SITE_ROOT, "src", "data", "price-categories.json")

# Сайдкар для сайта: скидочная цена перезаписывает цену в самой ячейке (см. цикл акций
# ниже), исходная цена товара иначе теряется - а она нужна на сайте, чтобы показать
# зачёркнутую старую цену рядом с новой. Кладём рядом со скриптом, в Price/ (эта папка
# в .gitignore, наружу/в скачиваемый прайс ничего не попадает) - xlsx-to-price-items.py
# подхватывает его по имени товара при сборке src/data/priceItems.json.
PROMO_META_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "promo-meta.json")

# Три ступени вместо двух (выбор пользователя 2026-09-05, вариант «В»).
# Порог входа в акцию остался прежним — 30% маржи, поэтому НИ ОДИН товар акцию
# не потерял: те же ~319 позиций просто перераспределились между ступенями.
# Посчитано на реальном прайсе от 02.09: 15% — 52 товара, 10% — 105, 5% — 162.
# Обходится столько же, сколько прежняя схема 7/15 (17 254 ₽ против 17 185 ₽
# с одной единицы каждого товара), но витрина получает заметную среднюю ступень.
TIERS = [
    (45.0, 15.0),
    (35.0, 10.0),
    (30.0, 5.0),
    (0.0, 0.0),
]

# Служебные строки из 1С, которые не являются товаром и никогда не должны
# попадать ни в один прайс/каталог сайта (не удалять из этого списка молча -
# см. Site/CLAUDE.md, зафиксировано пользователем 2026-08-25).
EXCLUDE_NAME_PREFIXES = ["доставка"]
EXCLUDE_NAME_SUBSTRINGS = ["мятая", "мятые"]  # брак/мятая упаковка, скриншот пользователя 2026-08-25
EXCLUDE_ARTICLES = {"007927"}
# Секции-заголовки вида "Wella_Акция"/"Londa_Акция" - клиренс мятого/бракованного товара
# без цены (ячейка цены = " ", не число). Такую секцию убираем целиком (сам заголовок и все
# строки под ним), а не только по мятая-подстроке - страхуется от товаров без этого слова в имени.
JUNK_SECTION_SUFFIXES = ("_акция",)

# Разделы, которые НИКОГДА не уходят в акцию, по брендам (24.09.2026, решение пользователя).
# Повод: у LONDA поднялись закупочные цены на красители, и продавать их со скидкой нельзя.
# Скидка считается от маржи, а маржа при подорожании РАСТЁТ — то есть без этого списка
# подорожавший товар провалился бы в акцию сам собой, ровно наоборот к намерению.
#
# Ключ — раздел из Price/Каталог.xlsx (через журнал src/data/price-sections.json), а не
# линейка 1С: у LONDA линеек в 1С нет вовсе, все товары лежат прямо под брендом.
# Оксиданты и уход НЕ включены: подорожали красители, про остальное речи не было.
NO_PROMO_SECTIONS = {
    "LONDA": (
        "Аммиачный краситель",
        "Безаммиачный краситель",
        "Экспресс-тонирование блонда - Color Tune",
    ),
}
SECTIONS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "..", "src", "data", "price-sections.json")


def sections_by_name():
    """Раздел каталога по имени товара. Пусто — значит журнала ещё нет, и это не авария:
    исключение просто не сработает, а сборка не должна падать из-за него."""
    try:
        with open(SECTIONS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}

def is_excluded(name):
    n = name.strip().lower()
    if any(n.startswith(p) for p in EXCLUDE_NAME_PREFIXES):
        return True
    if any(s in n for s in EXCLUDE_NAME_SUBSTRINGS):
        return True
    if article(name) in EXCLUDE_ARTICLES:
        return True
    return False

def is_junk_section_header(name):
    n = name.strip().lower()
    return any(n.endswith(suf) for suf in JUNK_SECTION_SUFFIXES)

def discount_for_margin(margin_pct):
    for threshold, discount in TIERS:
        if margin_pct >= threshold:
            return discount
    return 0.0

def remove_rows_clean(ws, excluded_rows):
    """Удаляет строки из excluded_rows, вручную переносит высоты строк и объединения
    ячеек на новые номера строк - штатный ws.delete_rows() этого не делает (известное
    ограничение openpyxl: row_dimensions и merged_cells остаются привязаны к старым
    номерам строк), из-за чего после удаления высоты и объединения C:D съезжают на
    чужое содержимое (напр. объединение цена+единица могло попасть на строку товара
    вместо заголовка бренда - реальный случай, найден пользователем 2026-08-26).
    """
    excluded_set = set(excluded_rows)
    max_row = ws.max_row

    # старый номер строки -> новый номер строки (после удаления, тот же порядок)
    row_map = {}
    new_row = 0
    for old_row in range(1, max_row + 1):
        if old_row in excluded_set:
            continue
        new_row += 1
        row_map[old_row] = new_row
    kept_heights = {row_map[r]: ws.row_dimensions[r].height for r in row_map}

    # снимаем все объединения на старых номерах, запоминаем те, что переживут удаление
    old_merges = [(m.min_row, m.max_row, m.min_col, m.max_col) for m in list(ws.merged_cells.ranges)]
    for min_row, max_row_m, min_col, max_col in old_merges:
        ws.unmerge_cells(start_row=min_row, end_row=max_row_m, start_column=min_col, end_column=max_col)
    surviving_merges = []
    for min_row, max_row_m, min_col, max_col in old_merges:
        if min_row in excluded_set or max_row_m in excluded_set:
            continue  # объединение стояло на удаляемой строке - не переносим
        surviving_merges.append((row_map[min_row], row_map[max_row_m], min_col, max_col))

    for row_idx in sorted(excluded_rows, reverse=True):
        ws.delete_rows(row_idx, 1)

    for r, height in kept_heights.items():
        ws.row_dimensions[r].height = height
    for min_row, max_row_m, min_col, max_col in surviving_merges:
        ws.merge_cells(start_row=min_row, end_row=max_row_m, start_column=min_col, end_column=max_col)

def article(name):
    toks = name.strip().split()
    return toks[-1] if toks else None

def add_order_column(ws):
    """Добавляет колонку E "Заказ" - пустое поле, куда клиент вписывает количество при
    заказе по скачанному прайсу. Не голая колонка - оформление в стиле остальной таблицы:
    те же границы (тонкие между строками, внешний контур - средние), та же заливка
    бренд/линейка-заголовков (переносится с D на E, чтобы чёрная/серая полоса шла до
    конца таблицы без разрыва), правая внешняя граница переносится с D на E.
    Добавлено по просьбе пользователя 2026-08-26.
    """
    thin = Side(style="thin")
    medium = Side(style="medium")
    max_row = ws.max_row

    header_font = copy(ws.cell(row=4, column=3).font)
    header_align = copy(ws.cell(row=4, column=3).alignment)

    ws.column_dimensions["E"].width = 12

    # Строки 4 и 5 (шапка "Цена" и дисклеймер про НДС) снимаем с объединения C:D:
    # у объединённой не-якорной ячейки (тут - D) правка border не сохраняется при записи
    # файла (ограничение openpyxl) - без unmerge новая граница молча не запишется на диск.
    # Границу D нужно СНЯТЬ (прочитать) ДО unmerge - после снятия объединения ячейка
    # становится обычной пустой, её старый border не сохраняется автоматически.
    saved_d_border = {}
    for r in (4, 5):
        m = next((m for m in ws.merged_cells.ranges
                   if m.min_row == r and m.max_row == r and m.min_col == 3 and m.max_col == 4), None)
        if m:
            saved_d_border[r] = copy(ws.cell(row=r, column=4).border)
            ws.unmerge_cells(start_row=r, end_row=r, start_column=3, end_column=4)

    # расширяем объединения бренд/линейка-заголовков с C:D на C:E - чтобы чёрная/серая
    # полоса шла без разрыва до самого края таблицы, а не обрывалась перед новой колонкой.
    # Строки 4 и 5 (шапка "Цена"/"Заказ" и дисклеймер про НДС) НЕ трогаем - там C:D несёт
    # свой отдельный текст, а колонка E должна остаться самостоятельной ("Заказ" - свой
    # заголовок, а не продолжение "Цена").
    cd_merges = [m for m in list(ws.merged_cells.ranges)
                 if m.min_row == m.max_row and m.min_col == 3 and m.max_col == 4 and m.min_row > 5]
    for m in cd_merges:
        r = m.min_row
        ws.unmerge_cells(start_row=r, end_row=r, start_column=3, end_column=4)
        ws.merge_cells(start_row=r, end_row=r, start_column=3, end_column=5)

    for r in range(4, max_row + 1):
        b_cell = ws.cell(row=r, column=2)
        c_cell = ws.cell(row=r, column=3)
        d_cell = ws.cell(row=r, column=4)
        e_cell = ws.cell(row=r, column=5)

        d_border = saved_d_border.get(r) or d_cell.border
        if d_border.right is None or d_border.right.style != "medium":
            continue  # строка вне таблицы (не должно случаться начиная с 4, но на всякий случай)

        is_closing_row = b_cell.value is None and c_cell.value is None and d_cell.value is None
        is_item_row = isinstance(c_cell.value, (int, float))
        is_header_row = r > 5 and not is_item_row and not is_closing_row

        # правая внешняя граница таблицы переезжает с D на E
        d_cell.border = Border(left=d_border.left, right=thin, top=d_border.top, bottom=d_border.bottom)
        e_cell.border = Border(left=thin, right=medium, top=d_border.top, bottom=d_border.bottom)

        if r == 4:
            e_cell.value = "Заказ"
            e_cell.font = copy(header_font)
            e_cell.alignment = copy(header_align)
        elif is_header_row:
            e_cell.fill = copy(c_cell.fill)  # заливка бренда/линейки - продолжается на E без разрыва
        elif is_item_row:
            e_cell.font = copy(d_cell.font)
            e_cell.alignment = copy(d_cell.alignment)
        # строка 5 (disclaimer) и закрывающая последняя строка - только граница, без текста/заливки

def add_category_column(ws):
    """Добавляет колонку F "категории" - номер категории (1-17, см. Site/CLAUDE.md) для
    интерактивного каталога сайта. Известные категории подтягиваются из журнала
    src/data/price-categories.json (по точному имени товара, после нормализации пробелов -
    тем же способом, что использует xlsx-to-price-items.py, иначе не совпадёт). Товары,
    которых в журнале ещё нет (новые позиции) - остаются с пустой ячейкой и подсвечиваются
    синей заливкой, чтобы пользователь сразу увидел, что нужно вручную проставить категорию,
    не пролистывая весь прайс в поисках пропусков. Добавлено 2026-09-03 по прямой просьбе
    пользователя. Технически - продолжение add_order_column ещё на одну колонку вправо
    (тот же приём: внешняя граница таблицы переезжает с E на F, заливка бренд/линейка-
    заголовков копируется без разрыва).
    """
    thin = Side(style="thin")
    medium = Side(style="medium")
    max_row = ws.max_row

    categories = {}
    if os.path.exists(CATEGORIES_PATH):
        with open(CATEGORIES_PATH, "r", encoding="utf-8") as f:
            categories = json.load(f)

    # Позиции, которые категорию НЕ получат никогда: это не парикмахерский товар, и в
    # каталоге сайта они доступны только через "По бренду" (решено 2026-09-03).
    # Без этого списка они подсвечивались бы синим в КАЖДОЙ новой сборке прайса - вместе
    # со своими бренд-заголовками CONCEPT и KAPOUS. Подсветка задумана как рабочая пометка
    # "размети меня", а файл скачивает клиент: вечное синее пятно он читает как брак.
    NEVER_CATEGORIZED = {
        # Имена ИЗ КАТАЛОГА: список читается уже ПОСЛЕ apply_catalog_names(),
        # поэтому старые 1С-имена здесь больше не совпадали бы и эти пять
        # позиций подсвечивались бы синим вечно (поймано 14.09.2026).
        "Бальзам для губ ультраувлажняющий 13мл 52803",
        "Гель после бритья с охлаждающим эффектом 250мл 2921",
        "Гель увлажняющий для душа, мужской с экстрактом оливы 250мл 1151",
        "Гель увлажняющий для душа, мужской с экстрактом оливы 300мл 3225",
        "Пена мужская для бритья GENTLEMEN 3 effect 300мл 923",
    }

    header_font = copy(ws.cell(row=4, column=5).font)
    header_align = copy(ws.cell(row=4, column=5).alignment)

    ws.column_dimensions["F"].width = 12

    # Header-объединения C:E (расширены add_order_column) - ещё на шаг вправо, до C:F.
    ce_merges = [m for m in list(ws.merged_cells.ranges)
                 if m.min_row == m.max_row and m.min_col == 3 and m.max_col == 5 and m.min_row > 5]
    for m in ce_merges:
        r = m.min_row
        ws.unmerge_cells(start_row=r, end_row=r, start_column=3, end_column=5)
        ws.merge_cells(start_row=r, end_row=r, start_column=3, end_column=6)

    new_items = []
    # Заголовки бренда/линейки - "папки" в интерактивном каталоге сайта. Товар без категории
    # может затеряться среди ~1100 строк - подсвечиваем синим ещё и его заголовки (бренд +,
    # если есть, линейку), чтобы новую позицию было видно сразу по свёрнутому списку папок,
    # не читая построчно. Добавлено 2026-09-03 по прямой просьбе пользователя.
    # ВАЖНО: подсвечивать нужно B и C (якорь объединения C:F), НЕ F - запись заливки на
    # НЕ-якорную ячейку объединения (D/E/F) молча не сохраняется при записи файла (то же
    # ограничение openpyxl, что уже ловили с border, см. add_order_column выше) - проверено
    # на реальном тесте: заливка F header-строки не пережила save()/load(), а у B/C всегда
    # была своя настоящая (не унаследованная от merge) заливка - её перезапись видна честно.
    for r in range(4, max_row + 1):
        c_cell = ws.cell(row=r, column=3)
        d_cell = ws.cell(row=r, column=4)
        e_cell = ws.cell(row=r, column=5)
        f_cell = ws.cell(row=r, column=6)

        # В отличие от add_order_column, тут НЕ проверяем e_border.right == "medium" перед
        # обработкой строки: у заголовков бренда/линейки собственная граница E ненадёжна
        # (та же природа, что и с заливкой - см. коммент выше), и этот гейт молча пропускал
        # ВСЕ header-строки целиком (заголовки никогда не подсвечивались бы). range(4, max_row+1)
        # и так гарантированно только настоящие строки таблицы (max_row посчитан ПОСЛЕ
        # remove_rows_clean, мусора после него не остаётся) - классификации по значениям
        # достаточно, отдельный гейт по границе не нужен.
        e_border = e_cell.border
        is_item_row = isinstance(c_cell.value, (int, float))
        is_closing_row = ws.cell(row=r, column=2).value is None and c_cell.value is None and d_cell.value is None
        is_header_row = r > 5 and not is_item_row and not is_closing_row

        e_cell.border = Border(left=e_border.left, right=thin, top=e_border.top, bottom=e_border.bottom)
        f_cell.border = Border(left=thin, right=medium, top=e_border.top, bottom=e_border.bottom)

        if r == 4:
            f_cell.value = "категории"
            f_cell.font = copy(header_font)
            f_cell.alignment = copy(header_align)
        elif is_header_row:
            f_cell.fill = copy(c_cell.fill)
        elif is_item_row:
            name = ws.cell(row=r, column=2).value
            clean_name = re.sub(r"\s+", " ", str(name).strip())
            cat = categories.get(clean_name)
            if cat is not None:
                f_cell.value = int(cat)
                f_cell.font = copy(d_cell.font)
                f_cell.alignment = copy(d_cell.alignment)
            elif clean_name not in NEVER_CATEGORIZED:
                new_items.append(clean_name)

    if new_items:
        print(f"Без категории ({len(new_items)}) — разметить в src/data/price-categories.json: {new_items}")

    # Колонка F СКРЫВАЕТСЯ в готовом файле. Она нужна только нам: её читает
    # xlsx-to-price-items.py при разметке категорий, а покупателю, который скачает прайс,
    # столбец голых номеров с подписью «категории» ничего не говорит — это внутренняя кухня.
    # Найдено предпубликационной проверкой 2026-09-05: на проде такой колонки не было, она
    # появилась бы впервые именно как мусор в клиентском файле.
    # Скрытая колонка полностью читается openpyxl, поэтому пайплайн разметки не страдает.
    # ВАЖНО: если нужно проставить категории вручную — в Excel показать колонку F
    # (выделить E:G, правый клик, «Показать»), заполнить и сохранить; скрипт при следующем
    # запуске снова её скроет.
    ws.column_dimensions["F"].hidden = True


def add_sum_column(ws):
    """Колонка G «Сумма» = кол-во × цена, итог вверху и автофильтр по шапке.

    Просьба пользователя 23.09.2026: клиент заполняет «Заказ» прямо в скачанном файле,
    и ему нужно видеть, на сколько он набрал, а не считать в уме.

    Почему G, а не F: F занята служебной колонкой категорий, и она СКРЫТА — для клиента
    «Заказ» и «Сумма» окажутся вплотную. Вставлять колонку в середину нельзя: в файле
    объединённые ячейки на каждом заголовке бренда, а openpyxl при вставке их не
    переносит (та же природа, что у delete_rows, см. remove_rows_clean).

    Почему итог ВВЕРХУ, в строке 5, а не отдельной строкой внизу:
      * строк больше тысячи — итог внизу клиент не увидит, пока не долистает;
      * со закреплённой шапкой строка 5 висит на экране всегда;
      * лишняя строка под таблицей опасна: у неё нет цены, и xlsx-to-price-items.py
        принял бы её за заголовок бренда с нераспознанной заливкой.
    """
    thin = Side(style="thin")
    medium = Side(style="medium")
    max_row = ws.max_row
    ws.column_dimensions["G"].width = 13

    # объединения заголовков бренда/линейки тянем с C:F на C:G — чтобы полоса заливки
    # шла до края таблицы без разрыва, как это делают add_order_column/add_category_column
    cf_merges = [m for m in list(ws.merged_cells.ranges)
                 if m.min_row == m.max_row and m.min_col == 3 and m.max_col == 6 and m.min_row > 5]
    for m in cf_merges:
        r = m.min_row
        ws.unmerge_cells(start_row=r, end_row=r, start_column=3, end_column=6)
        ws.merge_cells(start_row=r, end_row=r, start_column=3, end_column=7)

    header_font = copy(ws.cell(row=4, column=5).font)
    header_align = copy(ws.cell(row=4, column=5).alignment)
    money = '# ##0.00'

    for r in range(4, max_row + 1):
        c_cell = ws.cell(row=r, column=3)
        f_cell = ws.cell(row=r, column=6)
        g_cell = ws.cell(row=r, column=7)
        fb = f_cell.border
        is_item_row = isinstance(c_cell.value, (int, float))
        is_header_row = r > 5 and not is_item_row

        # правая внешняя граница таблицы переезжает с F на G
        f_cell.border = Border(left=fb.left, right=thin, top=fb.top, bottom=fb.bottom)
        g_cell.border = Border(left=thin, right=medium, top=fb.top, bottom=fb.bottom)

        if r == 4:
            g_cell.value = "Сумма"
            g_cell.font = copy(header_font)
            g_cell.alignment = copy(header_align)
        elif r == 5:
            pass  # строка-дисклеймер про НДС — только граница
        elif is_header_row:
            g_cell.fill = copy(c_cell.fill)
        elif is_item_row:
            # Пустая клетка «Заказ» не должна давать ноль в каждой строке — тысяча нулей
            # превратит колонку в шум, и настоящие суммы в ней потеряются.
            g_cell.value = f'=IF(E{r}="","",E{r}*C{r})'
            g_cell.number_format = money
            g_cell.alignment = copy(ws.cell(row=r, column=4).alignment)

    # Итог — в строке 3, ВЫШЕ шапки таблицы. Внутри диапазона фильтра ему не место:
    # при любом отборе строка с итогом спряталась бы вместе с отфильтрованными
    # товарами. Строка 3 пустая, лежит выше фильтра и внутри закреплённой области,
    # поэтому итог виден всегда — и до прокрутки, и после.
    label = ws.cell(row=3, column=5, value="Итого заказа:")
    label.font = copy(header_font)
    # Прижимаем вправо: в колонке «Заказ» ширины 12 подпись не помещается и обрезается
    # («Итого зака»). У правого выравнивания текст вытягивается ВЛЕВО по пустым соседним
    # ячейкам (D3, C3 в строке 3 пусты) и виден целиком. Замечание пользователя 23.09.2026.
    label.alignment = Alignment(horizontal="right", vertical="center")
    total = ws.cell(row=3, column=7, value=f"=SUM(G6:G{max_row})")
    total.font = copy(header_font)
    total.number_format = money
    total.alignment = Alignment(horizontal="right", vertical="center")
    # Высота строки: по умолчанию строка 3 была технической и узкой — текст и сумма
    # в ней срезались сверху и снизу.
    ws.row_dimensions[3].height = 21

    # Фильтр по шапке и закреплённая шапка: в прайсе больше тысячи строк, и без этого
    # клиент, долистав до середины, уже не помнит, какая колонка чему.
    ws.auto_filter.ref = f"B4:G{max_row}"
    ws.freeze_panes = "A6"


def close_table_bottom(ws):
    """Прочерчивает нижнюю границу таблицы на последней строке (B:E) - без неё низ
    таблицы держался только на верхней границе следующей строки (общий приём Excel:
    нижняя линия строки N визуально = верхняя линия строки N+1), а роль этой "следующей
    строки" раньше играла техническая пустая строка-заглушка из 1С-экспорта. После того
    как build() стал удалять эту заглушку как мусор (2026-08-28, см. Site/CLAUDE.md),
    у настоящей последней строки таблицы не осталось соседа снизу - и её нижний край
    повис без линии. Ставим explicit medium-границу здесь же, а не полагаемся на соседа.
    """
    medium = Side(style="medium")
    last_row = ws.max_row
    for col in range(2, 8):  # B..G
        cell = ws.cell(row=last_row, column=col)
        b = cell.border
        cell.border = Border(left=b.left, right=b.right, top=b.top, bottom=medium)

BRAND_FILL_INDEX = 8
LINE_FILL_INDEX = 22

def header_level(cell):
    """'brand' (чёрная заливка) или 'line' (серая) - как в xlsx-to-price-items.py.
    Неопознанная заливка (в т.ч. у заголовков без спец-оформления) считается брендом -
    безопаснее, чем ошибочно сузить область поиска товаров под ним.

    Комментарий-метка (см. add_category_column) проверяется первым: синяя подсветка
    "есть неразмеченный товар" перезаписывает fgColor тем же RGB-синим и на бренде,
    и на линейке - без метки оба стали бы неотличимы от "неопознанная заливка" и
    линейка потерялась бы в списке брендов (реальный случай 2026-09-16, 243 позиции
    WELLA/Illumina/EIMI/KP Me+/CT оторвались от бренда)."""
    if cell.comment is not None:
        if cell.comment.text == "zilma:line":
            return "line"
        if cell.comment.text == "zilma:brand":
            return "brand"
    fg = cell.fill.fgColor
    if fg.type == "indexed" and fg.indexed == LINE_FILL_INDEX:
        return "line"
    return "brand"

def norm_spaces(s):
    return re.sub(r"\s+", " ", str(s).strip())


def lebel_prices_from_form():
    """{числовой артикул: цена} из бланка заказа LebeL (Price/lebel-order-form-*.xlsx).

    Зачем: в 1С цены LEBEL обновляются не всегда вовремя — 22.09.2026 пользователь
    прямо сказал «не успел сделать цены для lebel, их нужно будет оставить из основного
    прайса lebel». Бланк поставщика в этом случае и есть источник истины.

    Ключ — ЧИСЛОВАЯ часть артикула: у LebeL к номеру приписан складской хвост
    («4263лп», «8429еп»), а в 1С номера голые. Тот же приём, что в
    scripts/build-lebel-preorder.py:art_num — держать в согласии с ним.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    forms = sorted(f for f in os.listdir(here)
                   if f.startswith("lebel-order-form-") and f.endswith(".xlsx"))
    if not forms:
        return {}
    wb = openpyxl.load_workbook(os.path.join(here, forms[-1]), read_only=True, data_only=True)
    ws_f = wb[wb.sheetnames[0]]
    out = {}
    for row in ws_f.iter_rows(min_row=3, values_only=True):
        art = str(row[3]).strip() if len(row) > 3 and row[3] else ""
        price = row[5] if len(row) > 5 else None
        if not art or not isinstance(price, (int, float)) or not price:
            continue
        m = re.match(r"^\D*(\d+)", art.split("/")[0])
        if m:
            out[m.group(1).lstrip("0") or "0"] = round(float(price), 2)
    wb.close()
    return out


def apply_lebel_prices(ws, item_rows, header_rows):
    """Ставит товарам LEBEL цену из бланка поставщика вместо цены из 1С.

    Место вызова принципиально — между сопоставлением себестоимостей и расчётом акций:
      * ВЫШЕ себестоимости уже найдены по именам из 1С, до этой точки строки трогать
        нельзя;
      * НИЖЕ считаются акции, и считаться они должны от НОВОЙ цены. Маржа при
        подорожании растёт, и товар может честно провалиться в акционную ступень —
        пользователь подтвердил это поведение 21.09.2026 на Igora.
    Подмена идёт в самом файле, поэтому скачиваемый прайс и сайт получают одинаковые
    цены. Правка только на сайте развела бы их, и клиент увидел бы в файле одно, а на
    странице другое.

    Ограничена строками под заголовком бренда LEBEL: числовой артикул сам по себе может
    совпасть с артикулом другого бренда.
    """
    prices = lebel_prices_from_form()
    if not prices:
        print("Бланк LebeL не найден — цены LEBEL остаются из 1С")
        return item_rows, 0
    brands = [(h, norm_spaces(ws.cell(row=h, column=2).value)) for h, lvl in header_rows
              if lvl == "brand"]

    def brand_of(row_idx):
        cur = ""
        for h, nm in brands:
            if h < row_idx:
                cur = nm
            else:
                break
        return (cur or "").upper()

    out, changed, same = [], 0, 0
    for row_idx, name, price, unit in item_rows:
        if "LEBEL" in brand_of(row_idx):
            m = re.match(r"^\D*(\d+)", str(article(name) or "").split("/")[0])
            key = (m.group(1).lstrip("0") or "0") if m else None
            fresh = prices.get(key)
            if fresh is not None:
                if abs(fresh - price) > 0.01:
                    ws.cell(row=row_idx, column=3, value=fresh)
                    price = fresh
                    changed += 1
                else:
                    same += 1
        out.append((row_idx, name, price, unit))
    print(f"Цены LEBEL из бланка поставщика: заменено {changed}, уже совпадали {same}")
    return out, changed


def lebel_names_from_form():
    """{числовой артикул: имя товара} из бланка заказа LebeL.

    Для LEBEL бланк поставщика полнее, чем Price/Каталог.xlsx: в каталоге имена заведены
    руками и новинок там может не быть, а бланк приходит со всеми позициями сразу и с
    нормальными именами. Замечание пользователя 22.09.2026: «зачем ты берёшь lebel из
    каталога, он для него уже не годен?!» — и он прав: в тот день три новинки LEBEL
    остались с сокращениями из 1С («Краска д/волос NEW G B-8»), хотя в бланке они
    подписаны как «Краска для волос Materia G Тон New B-8».
    """
    here = os.path.dirname(os.path.abspath(__file__))
    forms = sorted(f for f in os.listdir(here)
                   if f.startswith("lebel-order-form-") and f.endswith(".xlsx"))
    if not forms:
        return {}
    wb = openpyxl.load_workbook(os.path.join(here, forms[-1]), read_only=True, data_only=True)
    ws_f = wb[wb.sheetnames[0]]
    out, last_name = {}, ""
    for row in ws_f.iter_rows(min_row=3, values_only=True):
        name = norm_spaces(row[1]) if len(row) > 1 and row[1] else ""
        volume = str(row[2]).strip() if len(row) > 2 and row[2] else ""
        art = str(row[3]).strip() if len(row) > 3 and row[3] else ""
        price = row[5] if len(row) > 5 else None
        if name and not art:
            last_name = ""
            continue
        if name:
            last_name = name
        if not art or not isinstance(price, (int, float)) or not price or not last_name:
            continue
        # Товар в нескольких фасовках: имя стоит только в первой строке, дальше один объём.
        # Единицу приписываем, только если её нет в самой ячейке (иначе «600 млмл»).
        full = name if name else (
            f"{last_name} {volume}{'' if re.search(r'[а-яёa-z]', volume, re.I) else 'мл'}"
            if volume else last_name)
        m = re.match(r"^\D*(\d+)", art.split("/")[0])
        if m:
            out[m.group(1).lstrip("0") or "0"] = norm_spaces(full)
    wb.close()
    return out


def apply_lebel_names(ws, item_rows, header_rows, only_rows=None):
    """Добирает имена товарам LEBEL из бланка поставщика — ТОЛЬКО тем, которых нет
    в Price/Каталог.xlsx. Артикул из 1С НЕ трогает.

    Почему только пробелы, а не все подряд: имена в каталоге причёсаны пользователем и
    несут то, чего в бланке нет. Первый прогон 22.09.2026 переписал все 92 позиции и
    потерял и номер шага, и объём:
        было:  «№1 Сыворотка для волос PROEDIT CARE WORKS CMC 150мл»
        стало: «Сыворотка для волос PROEDIT CARE WORKS CMC»
    Номер шага важен мастеру, объём — всем. Каталог остаётся главным; бланк закрывает
    новинки, которые пользователь ещё не успел туда вписать.

    Артикул — последнее слово имени, на нём держатся остатки, палитры и гиды
    (правило проекта). Поэтому меняется только тело имени, а хвост остаётся прежним:
    «Краска д/волос NEW G B-8 9580/B-8» -> «Краска для волос Materia G Тон New B-8 9580/B-8».
    """
    names = lebel_names_from_form()
    if not names:
        return item_rows, 0
    brands = [(h, norm_spaces(ws.cell(row=h, column=2).value)) for h, lvl in header_rows
              if lvl == "brand"]

    def brand_of(row_idx):
        cur = ""
        for h, nm in brands:
            if h < row_idx:
                cur = nm
            else:
                break
        return (cur or "").upper()

    out, changed = [], 0
    for row_idx, name, price, unit in item_rows:
        if only_rows is not None and row_idx not in only_rows:
            out.append((row_idx, name, price, unit))
            continue
        if "LEBEL" in brand_of(row_idx):
            tail = article(name) or ""
            m = re.match(r"^\D*(\d+)", str(tail).split("/")[0])
            key = (m.group(1).lstrip("0") or "0") if m else None
            fresh = names.get(key)
            if fresh:
                # Имя из бланка берём ЦЕЛИКОМ и дописываем артикул из 1С.
                # Срезать последнее слово нельзя: в бланке артикул лежит в отдельной
                # колонке, а последним словом имени стоит КОД ОТТЕНКА. Срез превращал
                # «Materia G New Тон A-6» в «Materia G New Тон» и обезличивал всю
                # палитру — поймано на первом же прогоне 22.09.2026.
                new_name = norm_spaces(f"{fresh} {tail}")
                if new_name != name:
                    ws.cell(row=row_idx, column=2).value = new_name
                    name = new_name
                    changed += 1
        out.append((row_idx, name, price, unit))
    print(f"Имена LEBEL из бланка поставщика: заменено {changed}")
    return out, changed


def apply_catalog_names(ws):
    """Ставит в лист имена из Price/Каталог.xlsx. Возвращает число замен.

    Правила сопоставления («имя, потом артикул», псевдонимы брендов, разбор
    ничьих) не дублируются: импортируем их из scripts/apply-catalog-names.py —
    файл с дефисом в имени, поэтому через importlib. Если каталога нет, тихо
    ничего не делаем: прайс должен собираться и без него.
    """
    import importlib.util

    acn_path = os.path.join(SITE_ROOT, "scripts", "apply-catalog-names.py")
    if not os.path.exists(acn_path) or not os.path.exists(
            os.path.join(SITE_ROOT, "Price", "Каталог.xlsx")):
        print("Каталог имён не найден — имена остаются как в 1С.")
        return 0
    spec = importlib.util.spec_from_file_location("acn", acn_path)
    acn = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(acn)

    known = set()
    items_path = os.path.join(SITE_ROOT, "src", "data", "priceItems.json")
    if os.path.exists(items_path):
        with open(items_path, "r", encoding="utf-8") as f:
            known = {i["brand"].upper() for i in json.load(f) if i.get("brand")}

    catalog = acn.read_catalog()
    rows = acn.rows_from_sheet(ws, known)
    mapping, ambiguous, missing = acn.resolve_names(catalog, rows)
    for row_idx, new_name in mapping.items():
        ws.cell(row=row_idx, column=2).value = new_name

    print(f"Имена из каталога: заменено {len(mapping)}, "
          f"уже верных {len(rows) - len(mapping) - len(ambiguous) - len(missing)}, "
          f"двусмысленных {len(ambiguous)}, нет в каталоге {len(missing)}")
    # LEBEL из этого списка исключён: для него каталог больше не источник истины —
    # решение пользователя 22.09.2026 («для lebel каталог больше не актуален, поэтому
    # нет смысла их туда добавлять»). Имена таким позициям даёт бланк поставщика, см.
    # apply_lebel_names. Предупреждение, по которому никто не собирается действовать,
    # быстро превращается в шум и приучает не читать весь список.
    for p in missing:
        if "LEBEL" in str(p.get("brand", "")).upper():
            continue
        print(f"   НЕТ В КАТАЛОГЕ (имя останется из 1С): {p['brand']} / {p['name']}")
    for p, hits in ambiguous:
        print(f"   ДВУСМЫСЛЕННО (не трогаем): {p['name']}")
    # Номера строк, которых в каталоге нет: их имена добирает бланк поставщика
    # (для LEBEL), см. apply_lebel_names.
    missing_rows = {p["row"] for p in missing if p.get("row")}
    return len(mapping), missing_rows


def build(src_price, src_ost, dst):
    wb_ost = openpyxl.load_workbook(src_ost, data_only=True)
    ws_ost = wb_ost.active
    ost_by_name = defaultdict(deque)
    for row in ws_ost.iter_rows(min_row=1, values_only=True):
        name, cost = row[0], row[3]
        if not name or not isinstance(name, str):
            continue
        if not isinstance(cost, (int, float)):
            continue
        ost_by_name[name.strip()].append(cost)

    wb = openpyxl.load_workbook(src_price, data_only=False)
    ws = wb.active

    item_rows = []
    current_brand = None
    in_junk_section = False
    junk_rows = []  # заголовки мусорных секций + строки-товары без цены внутри них - удаляются целиком
    header_rows = []  # все настоящие заголовки бренда/линейки, по порядку - для поиска "осиротевших" ниже
    for row in ws.iter_rows(min_row=1):
        name_cell, price_cell, unit_cell = row[1], row[2], row[3]
        name, price, unit = name_cell.value, price_cell.value, unit_cell.value
        if not name or not isinstance(name, str):
            # Полностью пустая строка (нет ни названия, ни цены, ни единицы) - техническая
            # "закрывающая" строка из 1С-экспорта в самом конце книги, не несёт данных.
            # Раньше молча переживала обработку (не заголовок, не товар - никуда не
            # попадала на удаление) и оставалась с огрызком старой границы без низа и
            # без колонки "Заказ" - рваный хвост таблицы на скачанном прайсе, найдено
            # пользователем 2026-08-28. Удаляем как мусор, как и прочие служебные строки.
            if name_cell.row >= 6 and price is None and unit is None:
                junk_rows.append(name_cell.row)
            continue
        name_s = name.strip()

        # Настоящий заголовок (бренд/линейка): нет ни цены, ни единицы измерения.
        if not isinstance(price, (int, float)) and unit is None:
            if is_junk_section_header(name_s):
                in_junk_section = True
                junk_rows.append(name_cell.row)
            else:
                in_junk_section = False
                current_brand = name_s
                if name_cell.row >= 6:  # пропускаем титульный блок (строки 1-5: "Прайс-лист", дата и т.п.)
                    header_rows.append((name_cell.row, header_level(name_cell)))
            continue

        # Товар без цены (ячейка цены пустая/" ") - не заголовок, просто нечего продавать.
        # Раньше такие строки ошибочно принимались за заголовок бренда и портили группировку
        # для всех товаров после них (см. Site/CLAUDE.md, найдено пользователем 2026-08-25).
        if not isinstance(price, (int, float)):
            junk_rows.append(name_cell.row)
            continue

        if in_junk_section:
            junk_rows.append(name_cell.row)
            continue

        item_rows.append((name_cell.row, name_s, price, unit))

    excluded_rows = list(junk_rows)
    excluded_content_rows = [r for r, n, p, u in item_rows if is_excluded(n)]
    if excluded_content_rows:
        excluded_names = [n for r, n, p, u in item_rows if is_excluded(n)]
        print("Исключено по содержимому:", excluded_names)
        item_rows = [(r, n, p, u) for r, n, p, u in item_rows if not is_excluded(n)]
        excluded_rows += excluded_content_rows
    if junk_rows:
        print(f"Исключено мусорных строк (без цены/мятые секции): {len(junk_rows)}")

    # "Осиротевшие" заголовки - у бренда/линейки не осталось ни одного товара после всех
    # исключений выше (напр. единственный товар был мятым и его убрали) - сам заголовок
    # без единой позиции под ним выглядит как обрубок в прайсе, тоже убираем.
    # Реальный случай: REFECTOCIL, единственный товар был "... МЯТЫЕ", найдено пользователем 2026-08-26.
    # Область бренда - до СЛЕДУЮЩЕГО бренда (не до любого заголовка!), т.к. внутри бренда
    # бывают линейки (MATRIX -> Total Results New -> товары -> MATRIX ...) - иначе бренд с
    # товарами только под своими линейками ошибочно считается пустым (тоже реальный баг,
    # найден при первой попытке этой же правки 2026-08-26).
    surviving_item_rows = sorted(r for r, n, p, u in item_rows)
    brand_positions = [h for h, lvl in header_rows if lvl == "brand"]
    empty_headers = []
    for i, (h, lvl) in enumerate(header_rows):
        if lvl == "line":
            next_h = header_rows[i + 1][0] if i + 1 < len(header_rows) else float("inf")
        else:
            later_brands = [b for b in brand_positions if b > h]
            next_h = later_brands[0] if later_brands else float("inf")
        if not any(h < r < next_h for r in surviving_item_rows):
            empty_headers.append(h)
    if empty_headers:
        print("Исключено осиротевших заголовков (без единого товара под ними):",
              [ws.cell(row=h, column=2).value for h in empty_headers])
        excluded_rows += empty_headers

    matched = {}
    unmatched_idx = []
    for row_idx, name, price, unit in item_rows:
        if ost_by_name[name]:
            matched[row_idx] = ost_by_name[name].popleft()
        else:
            unmatched_idx.append(row_idx)

    remaining = defaultdict(deque)
    for n, dq in ost_by_name.items():
        for c in dq:
            remaining[article(n)].append(c)

    name_by_row = {r: n for r, n, p, u in item_rows}
    still_unmatched = []
    for row_idx in unmatched_idx:
        a = article(name_by_row[row_idx])
        if remaining[a]:
            matched[row_idx] = remaining[a].popleft()
        else:
            still_unmatched.append(row_idx)

    print(f"Позиций: {len(item_rows)}, с себестоимостью: {len(matched)}, без: {len(still_unmatched)}")

    # --- Имена из Price/Каталог.xlsx ---
    # Ставятся ЗДЕСЬ, а не отдельным шагом после сборки, и порядок принципиален:
    #   * ВЫШЕ уже сопоставлены себестоимости — они ищутся по именам ИЗ 1С,
    #     значит до этой точки имена трогать нельзя;
    #   * НИЖЕ формируется промо-сайдкар (ключ — имя товара) и колонка категорий
    #     (тоже по имени). Раньше переименование шло отдельным скриптом ПОСЛЕ
    #     сборки, и оба промахивались: 140 акций теряли старую цену, а 494 строки
    #     подсвечивались синим как «без категории» — в файле, который скачивает
    #     клиент. Поймано сквозным прогоном 14.09.2026.
    # Правило сопоставления живёт в одном месте — scripts/apply-catalog-names.py.
    renamed, rows_without_catalog_name = apply_catalog_names(ws)
    if renamed:
        item_rows = [(ri, norm_spaces(ws.cell(row=ri, column=2).value), pr, un)
                     for ri, _nm, pr, un in item_rows]

    # LEBEL — имена и цены из бланка поставщика. Идут ПОСЛЕ каталога (бланк для LEBEL
    # полнее и перекрывает его) и ДО расчёта акций и колонки категорий, которые ключуются
    # по имени. См. apply_lebel_names / apply_lebel_prices.
    item_rows, _lebel_renamed = apply_lebel_names(ws, item_rows, header_rows,
                                                  rows_without_catalog_name)
    item_rows, _lebel_repriced = apply_lebel_prices(ws, item_rows, header_rows)

    # заголовок ценовой колонки: "2. Олег" -> "Цена"
    ws.cell(row=4, column=3, value="Цена")

    red = Font(name="Arial", sz=8, color="FFFF0000")

    # Бренд строки — тем же способом, что и в apply_lebel_prices: по ближайшему
    # заголовку бренда выше. Нужен, чтобы «Аммиачный краситель» у LONDA и у другого
    # бренда не спутались: раздел с таким именем есть не только у неё.
    _brand_headers = [(h, norm_spaces(ws.cell(row=h, column=2).value))
                      for h, lvl in header_rows if lvl == "brand"]
    _sections = sections_by_name()

    def _no_promo(row_idx, name):
        brand = ""
        for h, nm in _brand_headers:
            if h < row_idx:
                brand = nm
            else:
                break
        blocked = NO_PROMO_SECTIONS.get(brand.strip().upper())
        if not blocked:
            return False
        return _sections.get(norm_spaces(name), "") in blocked

    promo_count = 0
    promo_meta = {}
    no_promo_count = 0
    for row_idx, name, price, unit in item_rows:
        cost = matched.get(row_idx)
        if not cost:
            continue
        if _no_promo(row_idx, name):
            no_promo_count += 1
            continue
        current_margin = (price - cost) / price * 100
        discount = discount_for_margin(current_margin)
        if discount <= 0:
            continue
        new_price = round(price * (1 - discount / 100), 2)
        price_cell = ws.cell(row=row_idx, column=3)
        price_cell.value = new_price
        for col in (2, 3, 4):
            ws.cell(row=row_idx, column=col).font = red
        promo_count += 1
        # Ключ - нормализованное имя, тем же способом, что и в xlsx-to-price-items.py
        # (там же схлопывает лишние пробелы при чтении финального файла) - иначе не совпадёт.
        promo_meta[re.sub(r"\s+", " ", name).strip()] = {"old_price": price, "discount": discount}

    print("Товаров переведено в акцию:", promo_count)
    if no_promo_count:
        print("Удержано от акции по NO_PROMO_SECTIONS:", no_promo_count)

    remove_rows_clean(ws, excluded_rows)
    add_order_column(ws)
    add_category_column(ws)
    add_sum_column(ws)
    close_table_bottom(ws)

    os.makedirs(os.path.dirname(dst), exist_ok=True)
    wb.save(dst)
    print("Сохранено:", dst)

    with open(PROMO_META_PATH, "w", encoding="utf-8") as f:
        json.dump(promo_meta, f, ensure_ascii=False, indent=2)
    print("Сохранён сайдкар для сайта (старая цена/скидка):", PROMO_META_PATH)


if __name__ == "__main__":
    src_price = sys.argv[1] if len(sys.argv) > 1 else r"D:\Projects\work\Site\Price\общий прайс_25,08,2026.xlsx"
    src_ost = sys.argv[2] if len(sys.argv) > 2 else r"D:\Projects\work\Site\Price\Остатки_25,08,2026.xlsx"
    dst = sys.argv[3] if len(sys.argv) > 3 else r"D:\Projects\work\Site\public\prices\price-current.xlsx"
    build(src_price, src_ost, dst)
