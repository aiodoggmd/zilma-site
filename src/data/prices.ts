// Обновление прайса: заменить файл в public/prices/ на новый и поправить date здесь.
// Ничего больше менять не нужно — блок на сайте подтянет новую дату сам.

export const contacts = {
  telegram: { label: 'Telegram', href: 'https://t.me/Oleg_Zilma', value: '@Oleg_Zilma' },
  whatsapp: { label: 'WhatsApp', href: 'https://wa.me/79653542256', value: 'wa.me/79653542256' },
  bip: { label: 'Bip', href: 'https://dl.bip.com/egbuXYcQ', value: 'Bip' },
  email: { label: 'Почта', href: 'mailto:127LR@mail.ru', value: '127LR@mail.ru' },
};

export const currentPrice = {
  file: '/prices/price-current.xlsx',
  date: '2026-08-28',
};

// Карточки акционного товара — заполняются по мере появления акций.
// { image: '/images/promo/xxx.jpg', name: 'Matrix SoColor 5N', price: '650 ₽' }
export const promoItems: { image: string; name: string; price: string }[] = [];
