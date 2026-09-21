// Новость дня для статист-панели «Актуальный прайс» на главной (PriceBlock.astro).
// Пока currentNews не null — панель делится на 2 части: компактная дата сверху + новость снизу.
// Когда объявлять нечего — выставить currentNews = null, дата снова займёт всю панель.
export interface SiteNews {
  text: string;
  link?: string;
  linkLabel?: string;
}

// Прежняя новость про повышение цен Schwarzkopf Igora снята 21.09.2026: повышение
// состоялось в этот день, и текст «ожидается с 21 сентября» стал неправдой.
//
// Ссылка ведёт не в статью, а прямо в каталог, открытый на бренде: «#open-catalog=LEBEL»
// — тот же приём, которым гиды отправляют читателя смотреть весь бренд целиком
// (см. openFromHash в PriceChecklist.astro).
//
// Срок «2-3 рабочих дня» здесь ТЕКСТ, он не подтягивается из LEAD_TIME в
// scripts/build-lebel-preorder.py. Изменится срок — править обе точки.
export const currentNews: SiteNews | null = {
  text: 'Весь ассортимент Lebel теперь в каталоге. Под заказ — 2-3 рабочих дня.',
  link: '/#open-catalog=LEBEL',
  linkLabel: 'Смотреть Lebel',
};
