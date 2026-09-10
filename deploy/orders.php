<?php
/**
 * Просмотр заявки целиком — по паролю.
 *
 * В Telegram уходит только номер и сумма, без персональных данных: так за границу не
 * попадает ничего, что закон считает персональными данными. Имя, телефон, комментарий и
 * вложение продавец смотрит здесь — страницу отдаёт российский сервер.
 *
 * Файлы заявок лежат ВНЕ public_html, поэтому и вложение отдаётся через этот скрипт, а не
 * прямой ссылкой: иначе достаточно было бы угадать имя файла.
 *
 * Все значения для вывода готовятся ЗАРАНЕЕ, в обычные переменные, и только потом
 * подставляются в шаблон: вызов функции прямо внутри строки PHP понимает не во всех
 * версиях, а проверить это на общем хостинге получится только вживую.
 */

declare(strict_types=1);

// Конфиг лежит НА УРОВЕНЬ ВЫШЕ public_html — там, куда веб-сервер не пускает.
// Рядом со скриптом его держать нельзя: файл с паролем и токенами открывался бы
// прямой ссылкой.
$config = require __DIR__ . '/../config.php';

session_start();

$id = preg_replace('/[^0-9a-f\-]/', '', (string)($_GET['id'] ?? ''));

function esc($value): string
{
    return htmlspecialchars((string)$value, ENT_QUOTES, 'UTF-8');
}

function rub($value): string
{
    return number_format((float)$value, 2, ',', ' ');
}

/* --- Вход ------------------------------------------------------------------------- */
$error = '';
if (isset($_POST['password'])) {
    // hash_equals, а не ==: сравнение с ранним выходом позволяет подбирать пароль по времени ответа.
    if (hash_equals($config['view_password'], (string)$_POST['password'])) {
        $_SESSION['zilma_orders'] = true;
    } else {
        $error = '<p class="err">Неверный пароль</p>';
    }
}

if (empty($_SESSION['zilma_orders'])) {
    http_response_code(401);
    header('Content-Type: text/html; charset=utf-8');
    $safeId = esc($id);
    echo <<<HTML
<!doctype html><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Заявки Zilma</title>
<style>body{font:16px system-ui;margin:0;min-height:100vh;display:grid;place-items:center;
background:#faf6f0;color:#2b201c}form{display:grid;gap:10px;width:min(320px,90vw)}
input,button{font:inherit;padding:10px;border:1px solid #d8cfbf;border-radius:4px}
button{background:#38628c;color:#fff;border-color:#38628c;cursor:pointer}
.err{color:#c8000f;margin:0}</style>
<form method=post action="?id={$safeId}">{$error}
<label>Пароль<input type=password name=password autofocus></label>
<button>Открыть</button></form>
HTML;
    exit;
}

$dir = $config['data_dir'] . '/orders';

/* --- Отдача вложения --------------------------------------------------------------- */
if (isset($_GET['file']) && $id !== '' && is_file("{$dir}/{$id}.json")) {
    $record = json_decode((string)file_get_contents("{$dir}/{$id}.json"), true);
    $stored = $record['attachment']['stored'] ?? null;
    if (!$stored || !is_file("{$dir}/{$stored}")) {
        http_response_code(404);
        exit('нет файла');
    }
    header('Content-Type: ' . ($record['attachment']['mime'] ?? 'application/octet-stream'));
    header('Content-Disposition: attachment; filename="'
        . rawurlencode((string)($record['attachment']['name'] ?? 'file')) . '"');
    readfile("{$dir}/{$stored}");
    exit;
}

header('Content-Type: text/html; charset=utf-8');

/* --- Одна заявка ------------------------------------------------------------------- */
if ($id !== '' && is_file("{$dir}/{$id}.json")) {
    $r = json_decode((string)file_get_contents("{$dir}/{$id}.json"), true);

    $rows = '';
    foreach ($r['items'] ?? [] as $it) {
        $rows .= '<tr><td>' . esc($it['name'] ?? '') . '</td>'
            . '<td>' . (int)($it['qty'] ?? 1) . '</td>'
            . '<td>' . rub($it['price'] ?? 0) . ' ₽</td></tr>';
    }

    $fileLink = '';
    if (!empty($r['attachment'])) {
        $fileLink = '<p><a href="?id=' . esc($id) . '&file=1">Скачать вложение: '
            . esc($r['attachment']['name'] ?? 'файл') . '</a></p>';
    }

    $safeId    = esc($id);
    $at        = esc(str_replace('T', ' ', substr((string)($r['at'] ?? ''), 0, 16)));
    $name      = esc($r['name'] ?? '');
    $contact   = esc($r['contact'] ?? '');
    $messenger = esc(($r['messenger'] ?? '') !== '' ? $r['messenger'] : '—');
    $comment   = nl2br(esc(($r['comment'] ?? '') !== '' ? $r['comment'] : '—'));
    $total     = rub($r['total'] ?? 0);

    echo <<<HTML
<!doctype html><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Заявка {$safeId}</title>
<style>body{font:16px system-ui;margin:0;padding:20px;background:#faf6f0;color:#2b201c}
.card{max-width:720px;margin:0 auto;background:#fff;border:1px solid #d8cfbf;padding:18px}
h1{font-size:1.1rem;margin:0 0 4px}.meta{color:#7a6f66;font-size:.85rem;margin:0 0 14px}
dl{display:grid;grid-template-columns:auto 1fr;gap:6px 14px;margin:0 0 16px}
dt{color:#7a6f66;font-size:.85rem}dd{margin:0}
table{width:100%;border-collapse:collapse;font-size:.9rem}
td,th{border-bottom:1px solid #eee;padding:6px 4px;text-align:left}
td:nth-child(2),td:nth-child(3){text-align:right;white-space:nowrap}
.total{margin-top:12px;font-weight:700}a{color:#38628c}</style>
<div class=card>
<h1>Заявка {$safeId}</h1><p class=meta>{$at}</p>
<dl><dt>Имя</dt><dd>{$name}</dd><dt>Контакт</dt><dd>{$contact}</dd>
<dt>Чат</dt><dd>{$messenger}</dd><dt>Комментарий</dt><dd>{$comment}</dd></dl>
<table><thead><tr><th>Товар</th><th>Кол-во</th><th>Цена</th></tr></thead><tbody>{$rows}</tbody></table>
<p class=total>Итого: {$total} ₽</p>
{$fileLink}
<p><a href="?">← Все заявки</a></p></div>
HTML;
    exit;
}

/* --- Список последних заявок -------------------------------------------------------- */
$files = glob("{$dir}/*.json") ?: [];
rsort($files);
$list = '';
foreach (array_slice($files, 0, 100) as $f) {
    $r = json_decode((string)file_get_contents($f), true);
    if (!is_array($r)) {
        continue;
    }
    $list .= '<li><a href="?id=' . esc($r['id'] ?? '') . '">'
        . esc(str_replace('T', ' ', substr((string)($r['at'] ?? ''), 0, 16)))
        . ' · ' . count($r['items'] ?? []) . ' поз. · '
        . number_format((float)($r['total'] ?? 0), 0, ',', ' ') . ' ₽</a></li>';
}
if ($list === '') {
    $list = '<li><span style="display:block;padding:10px 2px;color:#7a6f66">Заявок пока нет</span></li>';
}

echo <<<HTML
<!doctype html><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Заявки Zilma</title>
<style>body{font:16px system-ui;margin:0;padding:20px;background:#faf6f0;color:#2b201c}
.card{max-width:720px;margin:0 auto;background:#fff;border:1px solid #d8cfbf;padding:18px}
h1{font-size:1.1rem;margin:0 0 12px}
ul{margin:0;padding:0;list-style:none}li{border-bottom:1px solid #eee}
li a{display:block;padding:10px 2px;color:#38628c;text-decoration:none}</style>
<div class=card><h1>Заявки</h1><ul>{$list}</ul></div>
HTML;
