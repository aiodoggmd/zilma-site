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

// Конфиг лежит НА УРОВЕНЬ ВЫШЕ public_html — там, куда веб-сервер не пускает.
// Рядом со скриптом его держать нельзя: файл с паролем и токенами открывался бы
// прямой ссылкой.
$config = require __DIR__ . '/../config.php';
require __DIR__ . '/mailer.php';

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

/* Слишком быстрая отправка — тоже признак бота: человек столько не печатает.

   ВАЖНО: метку времени ставит БРАУЗЕР, а сравниваем с часами СЕРВЕРА, и они всегда
   расходятся. Реальный случай 10.09.2026: часы сервера отставали на 16 секунд, из-за
   чего настоящая заявка выглядела как «отправлена раньше, чем открыта форма» —
   отрицательный возраст меньше порога, и заявка молча отбрасывалась. Человек при этом
   видел «ок». Поэтому отрицательный возраст (часы клиента впереди) ботом НЕ считаем:
   пропустить бота не страшно, его ловит honeypot, а потерять заказ — страшно. */
$renderedAt = (int)($_POST['form_rendered_at'] ?? 0);
$formAgeMs = microtime(true) * 1000 - $renderedAt;
if ($renderedAt > 0 && $formAgeMs >= 0 && $formAgeMs < 2500) {
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

/* --- Уведомления идут ДО ответа, и это осознанно ------------------------------------
   Сначала я сделал наоборот: ответить клиенту, а письма слать после. На этом хостинге
   так нельзя — PHP работает модулем Apache (apache2handler), fastcgi_finish_request нет,
   а max_execution_time = 10 секунд. Скрипт просто не доживал до отправки: заявка
   сохранялась, письмо не уходило (поймано 10.09.2026 — тестовое письмо дошло, письмо
   с заявкой нет).

   Держать ответ можно только потому, что каналы быстрые: письмо через SMTP уходит
   примерно за секунду, а Telegram отключён — с российского хостинга он недоступен и
   раньше висел 25 секунд, из-за чего браузер показывал «Failed to fetch».
   ЕСЛИ КОГДА-НИБУДЬ ДОБАВИТСЯ МЕДЛЕННЫЙ КАНАЛ — его нельзя звать отсюда: сначала
   ответ клиенту, отправка отдельной задачей по расписанию. */


/* --- Куда уходит заявка ------------------------------------------------------------
   Решение пользователя 2026-09-10: заявки идут на ПОЧТУ ЯНДЕКСА и в MAX. Серверы обоих
   в России, значит персональные данные страну не покидают — трансграничной передачи нет,
   и уведомлять о ней Роскомнадзор не нужно. Поэтому в эти два канала уходит заявка
   ЦЕЛИКОМ: имя, телефон, комментарий.

   Telegram остаётся необязательным и получает только состав и сумму, без персональных
   данных: его серверы за границей. Выключается пустым токеном в config.php.

   Уведомление о начале обработки ПДн в Роскомнадзор это не отменяет — оно нужно любому,
   кто собирает контакты, и от выбора каналов не зависит. */

$itemLines = [];
foreach (array_slice($items, 0, 20) as $it) {
    $itemLines[] = '· ' . mb_substr((string)($it['name'] ?? ''), 0, 70)
        . ' — ' . (int)($it['qty'] ?? 1) . ' шт. × '
        . number_format((float)($it['price'] ?? 0), 2, ',', ' ') . ' ₽';
}
if (count($items) > 20) {
    $itemLines[] = '· … и ещё ' . (count($items) - 20) . ' поз., смотреть по ссылке';
}
$itemsText = $itemLines ? implode("\n", $itemLines) : '(без позиций из каталога)';
$totalText = number_format($total, 2, ',', ' ');
$orderUrl  = "{$config['site_url']}/orders.php?id={$id}";

/* Полный текст — для российских каналов. */
$full = "Заявка {$id}\n"
    . date('d.m.Y H:i') . "\n\n"
    . "Имя: {$name}\n"
    . "Контакт: {$contact}\n"
    . ($messenger !== '' ? "Удобный чат: {$messenger}\n" : '')
    . ($comment !== '' ? "Комментарий: {$comment}\n" : '')
    . "\n{$itemsText}\n\nИтого: {$totalText} ₽\n"
    . ($attachment !== null ? "Вложение: {$orderUrl}&file=1\n" : '')
    . "\nЗаявка на сайте: {$orderUrl}";

/* Почта. Отправитель — ящик на этом же домене: письмо, отправленное от чужого адреса,
   почтовые службы считают подделкой и кладут в спам. */
if (!empty($config['email_to'])) {
    // Встроенная mail() на этом хостинге заблокирована (проверено 10.09.2026 пятью
    // способами — отказ при любом отправителе), поэтому письмо уходит через SMTP с
    // авторизацией от ящика на домене. См. mailer.php.
    $subjectPlain = 'Заявка ' . $id . ' · ' . count($items) . ' поз. · ' . $totalText . ' ₽';
    $sent = smtp_send($config, $config['email_to'], $subjectPlain, $full);
    // Итог отправки кладём в саму заявку: иначе «письмо не пришло» невозможно отличить
    // от «письмо не отправлялось». При отказе рядом ложится файл с диалогом почтового
    // сервера — по нему сразу видно, на каком шаге сорвалось (логин и пароль в него
    // не попадают, см. mailer.php).
    $record['email_sent'] = $sent['ok'];
    file_put_contents($dir . '/' . $id . '.json',
        json_encode($record, JSON_UNESCAPED_UNICODE), LOCK_EX);
    if (!$sent['ok']) {
        file_put_contents($dir . '/' . $id . '.mail.log', $sent['log'], LOCK_EX);
        // В лог кладём ответы сервера: «письмо не пришло» само по себе не говорит,
        // на каком шаге отказ.
        error_log("zilma: письмо по заявке {$id} не ушло
" . $sent['log']);
    }
}

/* MAX. Официальный Bot API (dev.max.ru): токен идёт в заголовке Authorization
   БЕЗ префикса Bearer, домен platform-api2. */
if (!empty($config['max_token']) && !empty($config['max_chat_id'])) {
    $ctxMax = stream_context_create(['http' => [
        'method'  => 'POST',
        'header'  => "Content-Type: application/json\r\nAuthorization: {$config['max_token']}\r\n",
        'content' => json_encode(['text' => $full], JSON_UNESCAPED_UNICODE),
        'timeout' => 20,
        'ignore_errors' => true,
    ]]);
    $maxUrl = 'https://platform-api2.max.ru/messages?chat_id='
        . rawurlencode((string)$config['max_chat_id']);
    if (@file_get_contents($maxUrl, false, $ctxMax) === false) {
        error_log("zilma: MAX notify failed for {$id}");
    }
}

/* Telegram — только если заполнен токен. Персональных данных не содержит. */
if (!empty($config['telegram_bot_token']) && !empty($config['telegram_chat_id'])) {
    $text = "Новая заявка {$id}\n"
        . count($items) . ' поз. · ' . number_format($total, 0, ',', ' ') . ' ₽'
        . ($attachment !== null ? ' · есть вложение' : '')
        . ($itemLines ? "\n\n" . $itemsText : '')
        . "\n\nИмя и телефон: {$orderUrl}";

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
    // Заявка уже сохранена в РФ. Если канал уведомления не ответит — это не повод терять
    // заказ, поэтому ошибку клиенту не показываем, а пишем в лог.
    if (@file_get_contents(
        "https://api.telegram.org/bot{$config['telegram_bot_token']}/sendMessage",
        false, $ctx) === false) {
        error_log("zilma: telegram notify failed for {$id}");
    }
}


echo json_encode(['ok' => true, 'id' => $id], JSON_UNESCAPED_UNICODE);
