// Обновление прайса: положить новый файл в public/prices/ и поправить обе строки ниже.
// Ничего больше менять не нужно — блок на сайте подтянет новую дату сам.
//
// Имя файла содержит дату (просьба пользователя 2026-09-10): клиент скачивает
// «2026-09-10-zilma-price.xlsx» и потом видит у себя в загрузках, за какое он число, а не
// безымянный «price-current». Побочная польза — новый адрес каждый раз, значит ни браузер,
// ни CDN не отдадут вчерашний файл вместо сегодняшнего.
// price-current.xlsx остаётся рабочим файлом пайплайна: его пишет build_price_current.py и
// читает xlsx-to-price-items.py. Датированная копия делается ПОСЛЕ полной сборки прайса —
// иначе клиент скачает файл, не совпадающий с каталогом на сайте.

export const contacts = {
  telegram: { label: 'Telegram', href: 'https://t.me/Oleg_Zilma', value: '@Oleg_Zilma' },
  whatsapp: { label: 'WhatsApp', href: 'https://wa.me/79653542256', value: 'wa.me/79653542256' },
  bip: { label: 'Bip', href: 'https://dl.bip.com/egbuXYcQ', value: 'Bip' },
  email: { label: 'Почта', href: 'mailto:127LR@mail.ru', value: '127LR@mail.ru' },
};

export const currentPrice = {
  file: '/prices/2026-09-10-zilma-price.xlsx',
  date: '2026-09-10',
};
