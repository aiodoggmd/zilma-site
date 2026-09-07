// «Повторить прошлый заказ» — общая логика для двух мест, где предлагается повтор:
// формы заявки (OrderForm.astro) и шапки каталога (PriceChecklist.astro).
//
// Почему один модуль, а не копия в каждом компоненте: обе точки показывают ОДНО И ТО ЖЕ
// состояние (последняя отправленная заявка, пересчитанная по сегодняшнему прайсу). Две копии
// такого кода со временем разъезжаются — где-то поправят формулировку или правило отбора, а
// где-то забудут, и человек увидит в каталоге одну сумму, а в заявке другую.
//
// ГЛАВНОЕ ПРАВИЛО: сохранённым в истории ценам не верим. Товар мог подорожать, попасть в акцию
// или уйти из прайса. Поэтому цена каждой позиции берётся заново из каталога, отрисованного на
// этой же странице (элементы .pc-check), а не из записи о прошлой заявке.

export interface RepeatItem {
  name: string;
  price: number;
  qty: number;
  brand: string;
  promo: boolean;
}

export interface RepeatState {
  /** когда была отправлена прошлая заявка */
  at: number;
  /** позиции с СЕГОДНЯШНЕЙ ценой */
  items: RepeatItem[];
  /** сколько позиций из прошлой заявки больше нет в прайсе */
  gone: number;
  /** сумма по сегодняшним ценам */
  total: number;
}

/** Каталог на странице — источник актуальной цены. Ключ — точное имя товара, как в 1С. */
function currentPrices(): Map<string, { price: number; promo: boolean; brand: string }> {
  const map = new Map<string, { price: number; promo: boolean; brand: string }>();
  document.querySelectorAll<HTMLInputElement>('.pc-check[data-name]').forEach((el) => {
    const name = el.dataset.name ?? '';
    const price = parseFloat(el.dataset.price ?? '');
    if (!name || !Number.isFinite(price) || map.has(name)) return;
    map.set(name, { price, promo: el.dataset.promo === '1', brand: el.dataset.brandLabel ?? '' });
  });
  return map;
}

/**
 * Что из прошлой заявки можно собрать сегодня и почём.
 * null — повторять нечего: истории нет, каталога на странице нет либо из заявки не осталось
 * ни одной позиции. Во всех трёх случаях предложение повтора показывать нельзя.
 */
export function repriceLastOrder(): RepeatState | null {
  const last = (window as any).zilmaOrders?.list()?.[0] as { at: number; items: RepeatItem[] } | undefined;
  if (!last) return null;

  const prices = currentPrices();
  const items: RepeatItem[] = [];
  let gone = 0;
  for (const it of last.items) {
    const now = prices.get(it.name);
    if (!now) { gone += 1; continue; }
    items.push({ name: it.name, price: now.price, qty: it.qty, brand: now.brand || it.brand, promo: now.promo });
  }
  if (!items.length) return null;

  return { at: last.at, items, gone, total: items.reduce((s, it) => s + it.price * it.qty, 0) };
}

/** Сумма без копеек и с пробелом между тысячами — как в остальной форме заявки. */
export function formatMoney(value: number): string {
  return Math.ceil(value).toLocaleString('ru-RU');
}

export function pluralPositions(n: number): string {
  const d10 = n % 10;
  const d100 = n % 100;
  if (d10 === 1 && d100 !== 11) return 'позиция';
  if (d10 >= 2 && d10 <= 4 && (d100 < 12 || d100 > 14)) return 'позиции';
  return 'позиций';
}

/** Заголовок строки: когда была прошлая заявка. */
export function repeatTitle(state: RepeatState): string {
  const when = new Date(state.at).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long' });
  return `Прошлая заявка от ${when}`;
}

/** Подпись под заголовком: состав и сумма по сегодняшнему прайсу. */
export function repeatSummary(state: RepeatState): string {
  // «N позиций уже НЕТ» требует родительного падежа и ломается на числах;
  // «больше не в прайсе» верно и с 1, и с 2, и с 5 — падеж именительный.
  return (
    `${state.items.length} ${pluralPositions(state.items.length)} · ` +
    `${formatMoney(state.total)} ₽ по сегодняшнему прайсу` +
    (state.gone ? ` · ${state.gone} ${pluralPositions(state.gone)} больше не в прайсе` : '')
  );
}

/** Положить повтор в корзину. Возвращает число добавленных позиций. */
export function applyRepeat(state: RepeatState): number {
  (window as any).zilmaCart?.set(state.items);
  return state.items.length;
}
