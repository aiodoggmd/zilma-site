<?php
/**
 * Настройки приёма заявок. Скопировать в config.php рядом с order.php и заполнить.
 *
 * ВАЖНО: и config.php, и папка с заявками должны лежать ВНЕ public_html — иначе их
 * содержимое можно открыть прямой ссылкой из браузера. На SpaceWeb структура обычно
 * такая: /home/логин/zilma.pro/public_html — значит data_dir ставим в /home/логин/zilma-data.
 *
 * Настоящий config.php в Git не попадает (см. .gitignore) — в нём токен бота и пароль.
 */

return [
    // Папка для заявок и вложений. ВНЕ public_html. Создастся сама при первой заявке.
    'data_dir' => '/home/ЛОГИН/zilma-data',

    // Тот же бот, что ведёт канал: @wella_news_bot
    'telegram_bot_token' => 'ТОКЕН',
    'telegram_chat_id'   => 'ID ЧАТА',

    // Пароль на просмотр заявок (orders.php). Длинный, не тот, что от панели хостинга.
    'view_password' => 'ПАРОЛЬ',

    // Адрес сайта — из него собирается ссылка в уведомлении.
    'site_url' => 'https://www.zilma.pro',

    // Вложение к заявке. 8 МБ — фото с телефона помещается с запасом.
    'max_file_bytes' => 8 * 1024 * 1024,

    // Разрешаем по РЕАЛЬНОМУ типу файла, а не по расширению.
    'allowed_mime' => [
        'image/jpeg', 'image/png', 'image/webp', 'image/heic',
        'application/pdf',
        'application/msword',
        'application/vnd.ms-excel',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    ],
];
