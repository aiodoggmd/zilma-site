<?php
/**
 * Приём заявки с сайта — замена serverless-функции Vercel.
 *
 * ЗАЧЕМ. Во-первых, закон: с 1 июля 2025 (ч. 5 ст. 18 152-ФЗ) имя и телефон россиянина
 * не должны впервые записываться на сервере за пределами РФ, а Vercel раздаёт сайт из
 * Франкфурта. Во-вторых, практика: с мобильного интернета российских операторов сайт на
 * Vercel не открывался вовсе — проверено пользователем на своей симке 10.09.2026.
 *
 * ЧТО ДЕЛАЕТ:
 *   1. Принимает форму, проверяет поля и отсеивает ботов.
 *   2. Кладёт заявку в папку ВНЕ public_html — из браузера её не открыть.
 *   3. Шлёт в Telegram уведомление БЕЗ персональных данных: номер, число позиций, сумму
 *      и ссылку. Имя, телефон и комментарий за границу не уходят, поэтому трансграничной
 *      передачи нет и уведомлять о ней Роскомнадзор не требуется.
 *
 * Настройки — в config.php рядом, он тоже вне public_html.
 */

declare(strict_types=1);

header('Content-Type: application/json; charset=utf-8');

$config = require __DIR__ . '/config.php';

function fail(string $code, int $status = 400)
{
    http_response_code($status);
    echo json_encode(['error' => $code], JSON_UNESCAPED_UNICODE);
    exit;
}

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    fail('method_not_allowed', 405);
}

/* --- Защита от ботов ---------------------------------------------------------------
   Honeypot: настоящий посетитель этого поля не видит. Отвечаем «ок», чтобы бот не понял,
   что его отсеяли, и не пошёл подбирать другой способ. */
if (trim((string)($_POST['hp_field'] ?? '')) !== '') {
    echo json_encode(['ok' => true]);
    exit;
}

/* Слишком быстрая отправка — тоже признак бота: человек столько не печатает. */
$renderedAt = (int)($_POST['form_rendered_at'] ?? 0);
if ($renderedAt > 0 && (microtime(true) * 1000 - $renderedAt) < 2500) {
    echo json_encode(['ok' => true]);
    exit;
}

/* Ограничение частоты по IP. Файл вместо базы: заявок единицы в день, база тут лишняя. */
$ip = $_SERVER['HTTP_X_FORWARDED_FOR'] ?? $_SERVER['REMOTE_ADDR'] ?? 'unknown';
$ip = trim(explode(',', (string)$ip)[0]);
$rateFile = $config['data_dir'] . '/rate.json';
$now = time();
$hits = is_file($rateFile) ? (json_decode((string)file_get_contents($rateFile), true) ?: []) : [];
$hits = array_filter($hits, static fn($v) => $v['t'] > $now - 3600);
$mine = array_filter($hits, static fn($v) => $v['ip'] === $ip);
if (count($mine) >= 10) {
    fail('rate_limited', 429);
}
$hits[] = ['ip' => $ip, 't' => $now];
file_put_contents($rateFile, json_encode(array_values($hits)), LOCK_EX);

/* --- Поля заявки ------------------------------------------------------------------ */
$name    = mb_substr(trim((string)($_POST['name'] ?? '')), 0, 200);
$contact = mb_substr(trim((string)($_POST['contact'] ?? '')), 0, 200);
if ($name === '' || $contact === '') {
    fail('missing_fields');
}

$messenger = mb_substr(trim((string)($_POST['messenger'] ?? '')), 0, 50);
$comment   = mb_substr(trim((string)($_POST['comment'] ?? '')), 0, 4000);
$items     = json_decode((string)($_POST['items_json'] ?? '[]'), true);
if (!is_array($items)) {
    $items = [];
}

$total = 0.0;
foreach ($items as $it) {
    $total += (float)($it['price'] ?? 0) * (int)($it['qty'] ?? 1);
}

/* --- Вложение ---------------------------------------------------------------------
   Проверяем по РЕАЛЬНОМУ содержимому, а не по расширению: расширение подделывается в два
   клика. finfo читает сигнатуру файла. */
$attachment = null;
if (!empty($_FILES['attachment']['tmp_name']) && is_uploaded_file($_FILES['attachment']['tmp_name'])) {
    if ($_FILES['attachment']['size'] > $config['max_file_bytes']) {
        fail('file_too_large');
    }
    $mime = (new finfo(FILEINFO_MIME_TYPE))->file($_FILES['attachment']['tmp_name']);
    if (!in_array($mime, $config['allowed_mime'], true)) {
        fail('file_type_invalid');
    }
    $attachment = [
        'name' => mb_substr((string)$_FILES['attachment']['name'], 0, 200),
        'mime' => $mime,
        'size' => (int)$_FILES['attachment']['size'],
    ];
}

/* --- Сохранение в РФ ---------------------------------------------------------------
   Случайная часть в номере — чтобы ссылку на заявку нельзя было подобрать перебором. */
$id = date('Ymd') . '-' . bin2hex(random_bytes(6));
$dir = $config['data_dir'] . '/orders';
if (!is_dir($dir)) {
    mkdir($dir, 0700, true);
}

if ($attachment !== null) {
    $stored = $dir . '/' . $id . '.file';
    move_uploaded_file($_FILES['attachment']['tmp_name'], $stored);
    $attachment['stored'] = basename($stored);
}

$record = [
    'id'         => $id,
    'at'         => date('c'),
    'name'       => $name,
    'contact'    => $contact,
    'messenger'  => $messenger,
    'comment'    => $comment,
    'items'      => $items,
    'total'      => $total,
    'attachment' => $attachment,
];
file_put_contents($dir . '/' . $id . '.json', json_encode($record, JSON_UNESCAPED_UNICODE), LOCK_EX);

/* --- Уведомление БЕЗ персональных данных -------------------------------------------
   Ни имени, ни телефона, ни комментария: комментарий человек пишет свободно и вполне
   может назвать там себя. В Telegram уходит только номер, счёт позиций, сумма и ссылка. */
$text = "Новая заявка {$id}\n"
    . count($items) . ' поз. · ' . number_format($total, 0, ',', ' ') . " ₽"
    . ($attachment !== null ? "\nЕсть вложение" : '')
    . "\n\nОткрыть: {$config['site_url']}/orders.php?id={$id}";

$payload = http_build_query([
    'chat_id' => $config['telegram_chat_id'],
    'text' => $text,
    'disable_web_page_preview' => 'true',
]);
$ctx = stream_context_create(['http' => [
    'method' => 'POST',
    'header' => "Content-Type: application/x-www-form-urlencoded\r\n",
    'content' => $payload,
    'timeout' => 20,
    'ignore_errors' => true,
]]);
// Заявка уже сохранена в РФ. Если Telegram не ответит — это не повод терять заказ,
// поэтому ошибку уведомления клиенту не показываем, а пишем в лог.
$sent = @file_get_contents(
    "https://api.telegram.org/bot{$config['telegram_bot_token']}/sendMessage", false, $ctx);
if ($sent === false) {
    error_log("zilma: telegram notify failed for {$id}");
}

echo json_encode(['ok' => true, 'id' => $id], JSON_UNESCAPED_UNICODE);
