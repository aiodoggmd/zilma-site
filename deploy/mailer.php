<?php
/**
 * Отправка письма через SMTP с авторизацией.
 *
 * Почему не встроенная mail(): на этом хостинге она заблокирована наглухо — проверено
 * пятью способами 10.09.2026 (от ящика на домене, от другого адреса, от технического
 * домена, вообще без отправителя) — всегда отказ. Так провайдер защищается от спама:
 * письма принимаются только от ящика, который представился паролем.
 *
 * Своя реализация вместо готовой библиотеки: нужен ровно один сценарий — отправить
 * простое текстовое письмо на один адрес. Тащить ради этого PHPMailer со всеми его
 * зависимостями на общий хостинг смысла нет.
 */

declare(strict_types=1);

/**
 * @return array{ok: bool, log: string} log пригодится, когда письмо не дойдёт:
 *         по ответам сервера сразу видно, на каком шаге отказ.
 */
function smtp_send(array $cfg, string $to, string $subject, string $body, ?array $attach = null): array
{
    $host = (string)($cfg['smtp_host'] ?? '');
    $port = (int)($cfg['smtp_port'] ?? 465);
    $user = (string)($cfg['smtp_user'] ?? '');
    $pass = (string)($cfg['smtp_pass'] ?? '');
    if ($host === '' || $user === '' || $pass === '') {
        return ['ok' => false, 'log' => 'SMTP не настроен'];
    }

    $log = '';
    // Порт 465 — шифрование с первой секунды, 587 — сначала открыто, потом STARTTLS.
    $address = ($port === 465 ? 'ssl://' : '') . $host . ':' . $port;
    $fp = @stream_socket_client($address, $errno, $errstr, 20);
    if (!$fp) {
        return ['ok' => false, 'log' => "нет соединения с {$address}: {$errstr}"];
    }
    stream_set_timeout($fp, 20);

    // Ответ SMTP может быть многострочным; последняя строка отличается пробелом
    // после кода (в промежуточных там дефис) — по нему и понимаем, что ответ дочитан.
    $read = static function () use ($fp): string {
        $data = '';
        while (($line = fgets($fp, 1024)) !== false) {
            $data .= $line;
            if (strlen($line) >= 4 && $line[3] === ' ') {
                break;
            }
        }
        return $data;
    };

    // $secret = true для шагов, где уходят логин и пароль: они передаются закодированной
    // строкой, и её нельзя писать в лог. Реальный случай 10.09.2026: пароль ящика попал в
    // переписку через вывод диагностики, потому что фильтр прятал только цифры.
    $say = static function (string $command, string $expect, bool $secret = false) use ($fp, $read, &$log): bool {
        if ($command !== '') {
            fwrite($fp, $command . "\r\n");
            $log .= ($secret ? '(логин/пароль скрыты)' : $command) . "\n";
        }
        $answer = $read();
        $log .= '  < ' . trim($answer) . "
";
        return str_starts_with(trim($answer), $expect);
    };

    $ok = $say('', '220')
        && $say('EHLO ' . ($cfg['smtp_helo'] ?? 'zilma.pro'), '250');

    if ($ok && $port !== 465) {
        $ok = $say('STARTTLS', '220')
            && @stream_socket_enable_crypto($fp, true, STREAM_CRYPTO_METHOD_TLS_CLIENT)
            && $say('EHLO ' . ($cfg['smtp_helo'] ?? 'zilma.pro'), '250');
    }

    $ok = $ok
        && $say('AUTH LOGIN', '334')
        && $say(base64_encode($user), '334', true)
        && $say(base64_encode($pass), '235', true)
        && $say('MAIL FROM:<' . $user . '>', '250')
        && $say('RCPT TO:<' . $to . '>', '250')
        && $say('DATA', '354');

    if ($ok) {
        $headers = [
            'From: Zilma <' . $user . '>',
            'To: <' . $to . '>',
            // Кириллица в теме иначе приезжает кракозябрами.
            'Subject: =?UTF-8?B?' . base64_encode($subject) . '?=',
            'Date: ' . date('r'),
            'MIME-Version: 1.0',
        ];

        if ($attach !== null) {
            // Письмо с вложением собирается вручную: письмо из двух частей — текст заявки
            // и файл таблицы. Граница между частями должна быть строкой, которой заведомо
            // нет в содержимом, поэтому берём случайную.
            $boundary = 'zilma' . bin2hex(random_bytes(8));
            $headers[] = 'Content-Type: multipart/mixed; boundary="' . $boundary . '"';
            $body = "--{$boundary}\r\n"
                . "Content-Type: text/plain; charset=UTF-8\r\n"
                . "Content-Transfer-Encoding: 8bit\r\n\r\n"
                . str_replace("\n", "\r\n", str_replace("\r\n", "\n", $body)) . "\r\n"
                . "--{$boundary}\r\n"
                . 'Content-Type: ' . $attach['type'] . '; name="' . $attach['name'] . "\"\r\n"
                . "Content-Transfer-Encoding: base64\r\n"
                . 'Content-Disposition: attachment; filename="' . $attach['name'] . "\"\r\n\r\n"
                . chunk_split(base64_encode($attach['body'])) . "\r\n"
                . "--{$boundary}--\r\n";
        } else {
            $headers[] = 'Content-Type: text/plain; charset=UTF-8';
            $headers[] = 'Content-Transfer-Encoding: 8bit';
        }
        // Строка из одной точки завершает письмо, поэтому такую строку в тексте
        // экранируют второй точкой — иначе письмо оборвётся на середине.
        $safeBody = preg_replace('/^\./m', '..', str_replace("\r\n", "\n", $body));
        $safeBody = str_replace("\n", "\r\n", (string)$safeBody);
        fwrite($fp, implode("\r\n", $headers) . "\r\n\r\n" . $safeBody . "\r\n.\r\n");
        $ok = $say('', '250');
    }

    $say('QUIT', '221');
    fclose($fp);

    return ['ok' => $ok, 'log' => $log];
}
