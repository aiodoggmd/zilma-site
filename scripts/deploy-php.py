# -*- coding: utf-8 -*-
"""
Заливает серверные PHP-файлы из deploy/ на хостинг.

ЗАЧЕМ ОТДЕЛЬНЫЙ СКРИПТ. `npm run publish` выкладывает только папку dist, а order.php,
orders.php и mailer.php лежат в списке KEEP (deploy-to-hosting.py) — «не создаётся
сборкой, не трогать». Правило верное: без него выкладка сносила бы приём заявок. Но у
него была обратная сторона — правка самих этих файлов НЕ доезжала до сервера и никак об
этом не сообщала. Поймано 21.09.2026: блок «ПОД ЗАКАЗ» в письме был написан, проверен и
закоммичен, сайт опубликован, а письмо на боевом сервере осталось прежним.

config.php сюда НЕ входит: он собирается из .env.deploy отдельным scripts/deploy-config.py
и лежит вне public_html. Здесь только код, без паролей.

Запуск:
    .venv/Scripts/python.exe scripts/deploy-php.py            # план, ничего не меняет
    .venv/Scripts/python.exe scripts/deploy-php.py --apply    # залить
"""
import argparse
import ftplib
import hashlib
import pathlib
import io
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "deploy"
REMOTE_DIR = "public_html"

# Только код приёмника заявок. config.php исключён намеренно: в нём пароли, его собирает
# deploy-config.py из .env.deploy, и он живёт ВНЕ public_html.
FILES = ["order.php", "orders.php", "mailer.php"]


def load_credentials() -> dict:
    """Те же доступы, что у основной выкладки: Site/.env.deploy (он в .gitignore)."""
    env = ROOT / ".env.deploy"
    creds = {}
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            creds[k.strip()] = v.strip().strip('"').strip("'")
    missing = [k for k in ("FTP_HOST", "FTP_USER", "FTP_PASSWORD") if not creds.get(k)]
    if missing:
        sys.exit(f"Нет доступов в .env.deploy: {', '.join(missing)}")
    return creds


def connect(host: str, user: str, password: str) -> ftplib.FTP_TLS:
    """ТОЛЬКО шифрованное соединение — как в deploy-to-hosting.py.

    Запасного незашифрованного пути нет намеренно: молчаливый откат на открытый FTP
    вернул бы утечку логина и пароля, только незаметно.
    """
    ftp = ftplib.FTP_TLS(host, timeout=60)
    ftp.login(user, password)
    ftp.prot_p()
    ftp.set_pasv(True)
    return ftp


def remote_size(ftp: ftplib.FTP_TLS, path: str):
    try:
        return ftp.size(path)
    except (ftplib.error_perm, ftplib.error_temp):
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="реально заливать, иначе только план")
    args = ap.parse_args()

    local = []
    for name in FILES:
        p = SRC / name
        if not p.exists():
            print(f"  ПРОПУСК: {name} — нет в deploy/")
            continue
        data = p.read_bytes()
        local.append((name, data, hashlib.md5(data).hexdigest()[:8], len(data)))
    if not local:
        sys.exit("В deploy/ нет ни одного из этих файлов — заливать нечего")

    creds = load_credentials()
    ftp = connect(creds["FTP_HOST"], creds["FTP_USER"], creds["FTP_PASSWORD"])
    try:
        ftp.cwd(REMOTE_DIR)
        print(f"Хостинг: {creds['FTP_HOST']}/{REMOTE_DIR}\n")
        print(f"{'файл':<16} {'на сервере':>12} {'локально':>12}   что будет")
        for name, data, digest, size in local:
            there = remote_size(ftp, name)
            if there is None:
                verdict = "ЗАЛИТЬ (на сервере нет)"
            elif there == size:
                verdict = "размер совпал — возможно, уже там"
            else:
                verdict = f"ЗАМЕНИТЬ ({there} -> {size})"
            print(f"{name:<16} {str(there or '—'):>12} {size:>12}   {verdict}")

        if not args.apply:
            print("\nЭто был план. Для заливки — запустить с --apply")
            return 0

        # Приём заявок — самое ценное на сайте. Резервная копия ДО замены, чтобы откат
        # не зависел от того, сохранился ли прежний файл где-то ещё.
        print()
        for name, data, digest, size in local:
            if remote_size(ftp, name) is not None:
                backup = f"{name}.bak"
                try:
                    ftp.rename(name, backup)
                    print(f"  {name}: прежний сохранён как {backup}")
                except ftplib.error_perm as e:
                    print(f"  {name}: не удалось сделать резервную копию ({e}) — НЕ заливаю")
                    continue
            ftp.storbinary(f"STOR {name}", io.BytesIO(data))
            now = remote_size(ftp, name)
            ok = now == size
            print(f"  {name}: залит, {now} байт — {'совпало' if ok else 'РАЗМЕР НЕ СОВПАЛ'}")
            if not ok:
                print("     откат: переименуй .bak обратно через файловый менеджер хостинга")
        print("\nГотово. Проверь приём заявки: npm run check")
    finally:
        try:
            ftp.quit()
        except Exception:
            ftp.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
