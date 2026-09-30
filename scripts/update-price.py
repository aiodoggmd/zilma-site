# -*- coding: utf-8 -*-
"""
Обновление прайса одной командой.

    npm run price                       — самые свежие «общий прайс_*» и «Остатки_*» из Price/
    npm run price -- --date 29,09,2026  — конкретная дата

Зачем: ритуал из AGENTS.md («ОБНОВЛЕНИЕ ПРАЙСА») — восемь команд, три из них с
предпросмотром, и порядок у них не случайный. Держать его в голове каждый раз долго и
опасно. Теперь порядок зашит здесь, а место человека, читавшего предпросмотры, заняли
проверки — каждая взята из реальной поломки, описанной в AGENTS.md:

  0. Проверки ДО записи: даты внутри файлов совпадают с датой в имени (файл
     «Остатки_06,05,2026» однажды оказался сентябрьским); данные сайта закоммичены —
     иначе при сбое откатить будет нечем; снимок «было».
  1. Сборка прайса (имена из Каталог.xlsx ставятся внутри).
     1а. Новинки в каталог (add-to-catalog.py). Если что-то дописано — по ритуалу:
         пересборка → разделы → перенос журналов → ещё пересборка (журналы ключуются по
         имени, без этого новинки остались бы без категории). Каталог должен быть закрыт
         в Excel — проверяется до записи.
  2. Разделы.
  3. Перенос журналов — предпросмотр, проверка, запись.
  4. Данные сайта.
  5. Привязка оттенков палитр.
  6. LEBEL «под заказ» — предпросмотр, проверка, запись; затем снова 4 и 5.
  7. Датированная копия прайса и дата в src/data/prices.ts; затем «нет в наличии» —
     build-gone-items.py (серые строки каталога, окно 90 дней от даты прайса).
  8. Сверка и снимок «стало»: сравнение с «было», стоп на аномалии.

Публикации здесь нет — она остаётся отдельным шагом с подтверждением (npm run publish).
Любая аномалия — стоп с понятной причиной и командой отката.
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
PRICE_DIR = ROOT / 'Price'
DATA = ROOT / 'src' / 'data'
PRICE_XLSX = ROOT / 'public' / 'prices' / 'price-current.xlsx'
PRICES_TS = DATA / 'prices.ts'
PROMO_META = PRICE_DIR / 'promo-meta.json'
PROMO_BACKUP = PRICE_DIR / 'promo-meta-before-update.json'
# Тронутые конвейером файлы под git — их откат одной командой.
TRACKED = ['src/data', 'public/prices']

MONTHS = {'января': 1, 'февраля': 2, 'марта': 3, 'апреля': 4, 'мая': 5, 'июня': 6, 'июля': 7,
          'августа': 8, 'сентября': 9, 'октября': 10, 'ноября': 11, 'декабря': 12}
NAME_DATE = re.compile(r'_(\d{2}),(\d{2}),(\d{4})\.xlsx$')


CATALOG = PRICE_DIR / 'Каталог.xlsx'
CATALOG_LOCK = PRICE_DIR / '~$Каталог.xlsx'  # Excel кладёт такой файл, пока каталог открыт
WRITING = False           # True с первого пишущего шага: до него откатывать нечего
CATALOG_BACKUP = None     # копия каталога, если add-to-catalog.py его менял


def stop(reason: str) -> None:
    if not WRITING:
        sys.exit(f'\n✗ СТОП: {reason}\n  Ничего не записано.')
    msg = (f'\n✗ СТОП: {reason}\n'
           f'  Откатить данные сайта: git checkout -- {" ".join(TRACKED)}\n'
           f'  Откатить акции: скопировать {PROMO_BACKUP.name} обратно в {PROMO_META.name}')
    if CATALOG_BACKUP:
        msg += f'\n  Откатить каталог: скопировать {CATALOG_BACKUP.name} обратно в {CATALOG.name}'
    sys.exit(msg)


def run(title: str, args: list[str]) -> str:
    print(f'\n[{title}]')
    proc = subprocess.run([PY, *args], cwd=ROOT, text=True, encoding='utf-8', errors='replace',
                          capture_output=True)
    out = (proc.stdout or '') + (proc.stderr or '')
    print(out.rstrip())
    if proc.returncode != 0:
        stop(f'шаг «{title}» завершился с ошибкой')
    if re.search(r'^\s*СТОП', out, re.M):
        stop(f'шаг «{title}» сам сказал СТОП — см. вывод выше')
    return out


# ---------- проверки до записи ----------

def pick_sources(date: str | None) -> tuple[Path, Path, tuple[int, int, int]]:
    def dated(prefix):
        found = {}
        for p in PRICE_DIR.glob(f'{prefix}_*.xlsx'):
            m = NAME_DATE.search(p.name)
            if m:
                d, mth, y = map(int, m.groups())
                found[(y, mth, d)] = p
        return found
    prices, stocks = dated('общий прайс'), dated('Остатки')
    if date:
        d, mth, y = map(int, date.split(','))
        key = (y, mth, d)
    else:
        common = set(prices) & set(stocks)
        if not common:
            stop('в Price/ нет пары «общий прайс_ДД,ММ,ГГГГ» + «Остатки_ДД,ММ,ГГГГ» с одной датой')
        key = max(common)
    if key not in prices or key not in stocks:
        stop(f'нет пары файлов за {key[2]:02},{key[1]:02},{key[0]}')
    # xlsx-to-price-items.py сам берёт САМЫЕ СВЕЖИЕ остатки по имени — если выбрана не
    # последняя дата, он прочитает другой файл, чем сборщик прайса.
    if key != max(stocks):
        stop('выбрана не самая свежая дата, а xlsx-to-price-items.py возьмёт самые свежие остатки — '
             'файлы разъедутся')
    return prices[key], stocks[key], key


def date_inside(path: Path) -> tuple[int, int, int] | None:
    ws = openpyxl.load_workbook(path, read_only=True, data_only=True).active
    for row in ws.iter_rows(max_row=15, values_only=True):
        for v in row:
            s = str(v or '').strip().lower()
            m = re.search(r'(\d{1,2})\s+([а-я]+)\s+(\d{4})', s)          # 29 Сентября 2026 г.
            if m and m.group(2) in MONTHS:
                return int(m.group(3)), MONTHS[m.group(2)], int(m.group(1))
            m = re.search(r'на дату:\s*(\d{2})\.(\d{2})\.(\d{2,4})', s)  # На дату: 29.09.26
            if m:
                y = int(m.group(3))
                return (y + 2000 if y < 100 else y), int(m.group(2)), int(m.group(1))
    return None


def check_dates(price: Path, stock: Path, key) -> None:
    for p in (price, stock):
        inside = date_inside(p)
        if inside is None:
            stop(f'не нашёл дату внутри {p.name} — открыть файл и проверить глазами')
        if inside != key:
            stop(f'{p.name}: дата в имени {key[2]:02}.{key[1]:02}.{key[0]}, а внутри '
                 f'{inside[2]:02}.{inside[1]:02}.{inside[0]} — переименовать копию по дате ВНУТРИ')
    print(f'  даты внутри файлов совпадают с именем: {key[2]:02}.{key[1]:02}.{key[0]}')


def check_clean() -> None:
    out = subprocess.run(['git', 'status', '--porcelain', '--', *TRACKED], cwd=ROOT, text=True,
                         encoding='utf-8', capture_output=True).stdout.strip()
    if out:
        stop('в данных сайта есть незакоммиченные правки — при сбое их не откатить отдельно:\n'
             + out + '\n  Сначала закоммитить или откатить их.')
    print('  данные сайта закоммичены — откат при сбое одной командой')


# ---------- снимки ----------

def article(name: str) -> str:
    tok = name.strip().split()[-1].rstrip('.') if name.strip() else ''
    m = re.fullmatch(r'(\d{3,10})[а-яё]{1,3}', tok)
    return m.group(1) if m else tok


def snapshot(verify_out: str) -> dict:
    items = json.loads((DATA / 'priceItems.json').read_text(encoding='utf-8'))
    promo_meta = json.loads(PROMO_META.read_text(encoding='utf-8')) if PROMO_META.exists() else {}
    stock = [i for i in items if not i.get('preorder')]
    pre = [i for i in items if i.get('preorder')]
    names = [i['name'] for i in items]
    stock_lebel = {article(i['name']) for i in stock if i['brand'].upper() == 'LEBEL'}
    palettes = re.findall(r'(\d+)/(\d+) с ценой останутся доступны', verify_out)
    gone_path = DATA / 'gone-items.json'
    gone = json.loads(gone_path.read_text(encoding='utf-8')) if gone_path.exists() else []
    live_keys = {(i['brand'].upper(), article(i['name'])) for i in items}
    return {
        'нет в наличии (серые)': len(gone),
        'серых, совпавших с живыми': sum(1 for g in gone if ((g['brand'] or '').upper(), article(g['name'])) in live_keys),
        'всего позиций': len(items),
        'складских': len(stock),
        'под заказ': len(pre),
        'акций': sum(1 for i in items if i.get('promo')),
        'акций со старой ценой': sum(1 for i in items if i.get('promo') and i['name'] in promo_meta),
        'без категории': sum(1 for i in items if not i.get('category')),
        'дублей имени': len(names) - len(set(names)),
        'LEBEL и на складе, и под заказ': sum(1 for i in pre if article(i['name']) in stock_lebel),
        'оттенков палитр с ценой': sum(int(a) for a, _ in palettes),
    }


# ---------- проверки после ----------

def after_migrate_preview(out: str, stock_before: int) -> int:
    m = re.search(r'Товаров: было (\d+), стало (\d+)', out)
    if not m:
        stop('перенос журналов не напечатал «Товаров: было N, стало M» — вывод изменился, проверить глазами')
    was, now = map(int, m.groups())
    # «было» ≈ 570 сверх складских — признак, что откатили отсечку товаров «под заказ».
    if was > stock_before + 100:
        stop(f'перенос журналов считает «было {was}» при {stock_before} складских — похоже, откатилась '
             'правка про товары «под заказ» (AGENTS.md)')
    if now < was * 0.9:
        stop(f'товаров стало {now} против {was} — больше 10% ушло разом, похоже на ошибку в файлах')
    gone = re.search(r'Действительно ушли из прайса: (\d+)', out)
    return int(gone.group(1)) if gone else 0


def add_new_to_catalog() -> list[str]:
    """Шаг 1а. Возвращает строки «БЕЗ МЕСТА» — новинки, которым скрипт не нашёл раздел."""
    global CATALOG_BACKUP
    out = run('1а Новинки в каталог — предпросмотр', ['scripts/add-to-catalog.py'])
    m = re.search(r'позиций: (\d+) \| без места: (\d+)', out)
    if not m:
        stop('add-to-catalog.py не напечатал «позиций: N | без места: M» — вывод изменился, проверить глазами')
    added = int(m.group(1))
    unplaced = [line.strip() for line in out.splitlines() if 'БЕЗ МЕСТА:' in line]
    if added == 0:
        print('  новинок для каталога нет')
        return unplaced
    if CATALOG_LOCK.exists():
        stop('Каталог.xlsx открыт в Excel — закрыть его и запустить команду снова '
             f'(дописать нужно {added} новинок)')
    before_files = set(PRICE_DIR.glob('Каталог-до-правки-*.xlsx'))
    run('1а Новинки в каталог — запись', ['scripts/add-to-catalog.py', '--apply'])
    new_backups = set(PRICE_DIR.glob('Каталог-до-правки-*.xlsx')) - before_files
    CATALOG_BACKUP = max(new_backups or before_files, key=lambda p: p.stat().st_mtime, default=None)
    return unplaced


def uncategorized() -> list[str]:
    items = json.loads((DATA / 'priceItems.json').read_text(encoding='utf-8'))
    return [f'{i["brand"]} / {i["name"]}' for i in items if not i.get('category')]


def compare(before: dict, after: dict, gone: int, uncat_before: set[str]) -> list[str]:
    """Стоп на поломке; возвращает предупреждения — то, что ждёт человека, но не авария."""
    print(f'\n{"":<34}{"было":>8}{"стало":>8}')
    for k in before:
        print(f'  {k:<32}{before[k]:>8}{after[k]:>8}')
    problems, warnings = [], []
    if after['акций со старой ценой'] != after['акций']:
        problems.append(f'акций {after["акций"]}, а со старой ценой {after["акций со старой ценой"]} — '
                        'часть акций потеряла зачёркнутую цену')
    # Новинка без категории — обычное дело, а не авария: стоп здесь заводил в тупик (данные
    # уже записаны, а повторный запуск на незакоммиченных данных не стартует). Проверено
    # повтором прогона 29.09.2026: ровно три новинки, которые утром размечали руками.
    if after['без категории'] > before['без категории']:
        warnings.append(f'без категории стало {after["без категории"]} (было {before["без категории"]}). '
                        'Разметить новинки в src/data/price-categories.json (по родне, спорное — '
                        'спросить Олега), затем прогнать scripts/xlsx-to-price-items.py и '
                        'scripts/verify-price-sync.py. Новые без категории:\n      '
                        + '\n      '.join(x for x in uncategorized() if x not in uncat_before))
    if after['серых, совпавших с живыми']:
        problems.append(f'{after["серых, совпавших с живыми"]} товаров одновременно в наличии и «нет в наличии»')
    if after['дублей имени']:
        problems.append(f'дублей имени: {after["дублей имени"]}')
    if after['LEBEL и на складе, и под заказ']:
        problems.append(f'LEBEL задвоен (и на складе, и под заказ): {after["LEBEL и на складе, и под заказ"]}')
    if after['под заказ'] < before['под заказ'] * 0.7:
        problems.append(f'«под заказ» упало с {before["под заказ"]} до {after["под заказ"]}')
    drop = before['оттенков палитр с ценой'] - after['оттенков палитр с ценой']
    if drop > gone:
        problems.append(f'палитры потеряли {drop} оттенков при {gone} ушедших товарах — искать '
                        'переименования (AGENTS.md, «Переименование рвёт связь каталога с цветом»)')
    if problems:
        stop('после сборки:\n  - ' + '\n  - '.join(problems))
    return warnings


def write_dated_copy(key) -> None:
    y, m, d = key
    iso = f'{y}-{m:02}-{d:02}'
    dst = PRICE_XLSX.with_name(f'{iso}-zilma-price.xlsx')
    shutil.copyfile(PRICE_XLSX, dst)
    src = PRICES_TS.read_text(encoding='utf-8')
    new = re.sub(r"file: '/prices/[\d-]+-zilma-price\.xlsx'", f"file: '/prices/{iso}-zilma-price.xlsx'", src)
    new = re.sub(r"date: '[\d-]+'", f"date: '{iso}'", new)
    if new.count(iso) < 2:
        stop('не смог поправить дату в src/data/prices.ts — формат строк изменился')
    PRICES_TS.write_text(new, encoding='utf-8')
    print(f'\n[7/8 Датированная копия]\n  {dst.name}; дата в prices.ts: {iso}')


def main() -> None:
    global WRITING
    ap = argparse.ArgumentParser(description='Обновить прайс сайта одной командой')
    ap.add_argument('--date', help='дата файлов в Price/, формат 29,09,2026 (по умолчанию — самая свежая)')
    args = ap.parse_args()
    print('\n=== Обновление прайса Zilma ===')

    print('\n[0/8 Проверки до записи]')
    price, stock, key = pick_sources(args.date)
    print(f'  прайс:   {price.name}\n  остатки: {stock.name}')
    check_dates(price, stock, key)
    check_clean()
    before = snapshot(run('0/8 Снимок «было»', ['scripts/verify-price-sync.py']))
    uncat_before = set(uncategorized())
    if PROMO_META.exists():
        shutil.copyfile(PROMO_META, PROMO_BACKUP)

    WRITING = True
    build = ['Price/build_price_current.py', str(price), str(stock), str(PRICE_XLSX)]
    migrate = ['scripts/migrate-renamed-products.py']
    run('1/8 Сборка прайса', build)
    run('2/8 Разделы', ['scripts/build-price-sections.py', '--apply'])
    gone = after_migrate_preview(run('3/8 Перенос журналов — предпросмотр', migrate), before['складских'])
    run('3/8 Перенос журналов — запись', [*migrate, '--apply'])
    unplaced = add_new_to_catalog()
    if CATALOG_BACKUP:
        # add-to-catalog причёсывает имена новинок («250 мл.» -> «250мл»), а журналы
        # (категории, дата первого появления) ключуются по имени. Товар, вернувшийся после
        # паузы, иначе теряет категорию и получает ложный бейдж «Нов» — так было с шампунем
        # OLLIN 395171 при повторе прогона 29.09.2026 (в прайсе с 12.08). Поэтому: снять
        # данные сайта с именами из 1С, пересобрать с именами каталога и перенести журналы
        # с первых на вторые — migrate опознает переименование по артикулу.
        run('1а Данные сайта с именами из 1С', ['scripts/xlsx-to-price-items.py'])
        run('1а Пересборка с новинками', build)
        run('1а Разделы', ['scripts/build-price-sections.py', '--apply'])
        after_migrate_preview(run('1а Перенос журналов на имена каталога — предпросмотр', migrate),
                              before['складских'])
        run('1а Перенос журналов на имена каталога — запись', [*migrate, '--apply'])
        run('1а Пересборка после переноса журналов', build)
    run('4/8 Данные сайта', ['scripts/xlsx-to-price-items.py'])
    run('5/8 Привязка палитр', ['scripts/link-palette-shades.py', '--apply'])
    run('6/8 LEBEL под заказ — предпросмотр', ['scripts/build-lebel-preorder.py'])
    run('6/8 LEBEL под заказ — запись', ['scripts/build-lebel-preorder.py', '--apply'])
    run('6/8 Данные сайта — повтор после LEBEL', ['scripts/xlsx-to-price-items.py'])
    run('6/8 Привязка палитр — повтор', ['scripts/link-palette-shades.py', '--apply'])
    write_dated_copy(key)
    # После даты в prices.ts: по ней считается окно «90 дней».
    run('7/8 Нет в наличии', ['scripts/build-gone-items.py'])
    after = snapshot(run('8/8 Сверка', ['scripts/verify-price-sync.py']))
    warnings = compare(before, after, gone, uncat_before)

    print('\n✓ Прайс обновлён, аномалий нет.')
    for w in warnings:
        print(f'  ! {w}')
    if CATALOG_BACKUP:
        print(f'  В каталог дописаны новинки; копия до правки — {CATALOG_BACKUP.name}.')
    if unplaced:
        print(f'  ! Без места в каталоге ({len(unplaced)}) — раздел не нашёлся, вписать руками '
              '(или добавить в MANUAL_SECTION в add-to-catalog.py):')
        for line in unplaced:
            print(f'    {line}')
    print('  Всё, что осталось без имени из каталога, — в выводе сверки выше («Без имени из каталога»).')
    print('  Дальше: git diff для просмотра, затем npm run publish (план) и публикация с --apply.\n')


if __name__ == '__main__':
    main()
