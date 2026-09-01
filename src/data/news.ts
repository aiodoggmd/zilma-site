// Новость дня для статист-панели «Актуальный прайс» на главной (PriceBlock.astro).
// Пока currentNews не null — панель делится на 2 части: компактная дата сверху + новость снизу.
// Когда объявлять нечего — выставить currentNews = null, дата снова займёт всю панель.
export interface SiteNews {
  text: string;
  link?: string;
  linkLabel?: string;
}

export const currentNews: SiteNews | null = {
  text: 'Теперь заказывать стало проще: прямо в статьях можно увидеть цвет красителей и сразу заказать нужный товар.',
  link: '/articles/2026-08-28-igora-royal/',
  linkLabel: 'Смотреть пример',
};
