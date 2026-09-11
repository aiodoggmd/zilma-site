# -*- coding: utf-8 -*-
"""
Публикация сайта одной командой.

    npm run publish            — только показать, что поедет (ничего не меняет)
    npm run publish -- --apply — собрать, выложить и проверить живой сайт

Зачем: публикация — это четыре шага подряд, и порядок у них не случайный. Держать его в
голове каждый раз — верный способ однажды залить несобранное или не заметить, что выкладка
собралась что-то удалить. Теперь порядок зашит здесь:

  1. Чистая сборка с нуля. Именно с нуля: в dist остаются файлы от прошлых сборок, и
     мёртвый скрипт может уехать на сервер вместе с живыми.
  2. Проверка связки прайса со статьями — сводка verify-price-sync.py.
  3. Проверка самой сборки: страницы на месте, главная не пустая.
  4. План выкладки: что зальётся и, главное, что УДАЛИТСЯ. Без --apply на этом всё
     заканчивается.
  5. Заливка (только с --apply), сразу за ней — утренняя проверка по живому сайту.

Любой шаг упал — публикация останавливается. Выложить наполовину хуже, чем не выложить.
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable


def run(title: str, command: list[str] | str, *, shell: bool = False, quiet: bool = False) -> str:
    """Выполняет шаг и останавливает публикацию, если он не прошёл."""
    print(f'\n[{title}]')
    proc = subprocess.run(command, shell=shell, cwd=ROOT, text=True, encoding='utf-8',
                          errors='replace', capture_output=True)
    out = (proc.stdout or '') + (proc.stderr or '')
    if proc.returncode != 0:
        print(out.strip()[-2000:])
        sys.exit(f'\n✗ Шаг «{title}» не прошёл. Публикация остановлена, на сайте ничего не изменилось.')
    if not quiet:
        print(out.rstrip())
    return out


def clean_dist() -> None:
    """Убирает прошлую сборку.

    Не через `rm -rf`: если открыт локальный предпросмотр, папка занята процессом, и вся
    публикация падала на первом же шаге из-за мелочи. Astro и сам очищает папку перед
    сборкой, поэтому занятая папка — повод предупредить, а не останавливаться.
    """
    dist = ROOT / 'dist'
    if not dist.exists():
        return
    try:
        shutil.rmtree(dist)
    except OSError:
        print('  прошлая сборка занята (открыт локальный предпросмотр?) — очистит Astro')


def check_build() -> None:
    """Сборка бывает «успешной» и при этом пустой — проверяем то, что реально важно."""
    dist = ROOT / 'dist'
    index = dist / 'index.html'
    if not index.is_file():
        sys.exit('✗ В сборке нет главной страницы — публиковать нечего.')
    html = index.read_text(encoding='utf-8', errors='replace')
    pages = len(list(dist.rglob('index.html')))
    problems = []
    if len(html) < 50_000:
        problems.append(f'главная подозрительно маленькая ({len(html) // 1024} КБ)')
    if 'pc-check' not in html:
        problems.append('на главной нет каталога товаров')
    if pages < 15:
        problems.append(f'страниц всего {pages}')
    if problems:
        sys.exit('✗ Сборка выглядит неполной: ' + '; '.join(problems))
    print(f'  страниц: {pages}, главная: {len(html) // 1024} КБ, каталог на месте')


def main() -> None:
    ap = argparse.ArgumentParser(description='Собрать и опубликовать сайт')
    ap.add_argument('--apply', action='store_true', help='выложить на сайт (без него — только план)')
    args = ap.parse_args()

    print('\n=== Публикация сайта Zilma ===')

    clean_dist()
    run('1/5 Чистая сборка', 'npx astro build', shell=True, quiet=True)
    print('  собрано')

    run('2/5 Прайс и статьи', [PY, 'scripts/verify-price-sync.py'])
    check_build()
    print('[3/5 Проверка сборки] — выше')

    plan = run('4/5 Что поедет на сайт', [PY, 'scripts/deploy-to-hosting.py'])

    if not args.apply:
        print('\nЭто был план, на сайте ничего не изменилось.')
        print('Публиковать: npm run publish -- --apply\n')
        return

    # «Удалить лишние» — единственная строка плана, которую нельзя пролистывать: именно она
    # один раз собралась снести mailer.php, на котором держится отправка заказов.
    for line in plan.splitlines():
        if line.startswith('удалить лишние:') and not line.endswith(' 0'):
            print(f'\n  ВНИМАНИЕ: {line.strip()} — это файлы, которых нет в сборке.')

    run('5/5 Заливка', [PY, 'scripts/deploy-to-hosting.py', '--apply'])
    run('Проверка живого сайта', [PY, 'scripts/morning-check.py'])
    print('\nОпубликовано.\n')


if __name__ == '__main__':
    main()
