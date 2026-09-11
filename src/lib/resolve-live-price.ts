import priceItems from '../data/priceItems.json';
import { AMBIGUOUS, articleOf, buildArticleIndex } from './article-key';

// Как именно считается артикул и что делать с составными кодами и коллизиями — в
// article-key.ts. Тот же индекс использует рантайм страницы статьи для кнопок «+ В заявку»,
// чтобы палитра и таблицы не расходились в том, есть товар в прайсе или нет.
const findByArticle = buildArticleIndex(priceItems);

// Интерактивная палитра (ShadeSwatchGrid) хранит name/price оттенка в data-файле линии,
// вписанные вручную на момент сборки статьи — застывший снимок прайса, как и таблицы
// "Что заказать" в markdown. Пересчитываем его на каждой сборке сайта из актуального
// priceItems.json по (бренд, артикул) — а не полагаемся на то, что было верно в день,
// когда я писал статью.
//
// Ограничение: для оттенков, которых НИ РАЗУ не было в прайсе (name изначально не задан —
// честное "нет в прайсе" без выдумывания цены), артикул физически неоткуда взять — само
// появление такого оттенка в продаже по-прежнему нужно будет добавить в data-файл вручную
// один раз, дальше это будет жить само. Не «магическое» решение в обе стороны, а честное
// закрытие дрейфа для уже известных позиций (изменилась цена или пропала из прайса).
export function resolveLiveShade<T extends { name?: string; price?: number }>(shade: T, brand: string): T {
  if (!shade.name) return shade;
  const live = findByArticle(brand, articleOf(shade.name));
  if (live === AMBIGUOUS) return shade; // не трогаем — не гадаем, какой из нескольких это
  if (!live) {
    const { name, price, promo, oldPrice, discountPct, isNew, ...rest } = shade as Record<string, unknown>;
    return rest as T;
  }
  return {
    ...shade,
    name: live.name,
    price: live.price,
    promo: live.promo,
    oldPrice: live.oldPrice ?? null,
    // Размер скидки и признак новинки — те же данные, что показывает каталог; без них
    // в статьях у акционного оттенка было бы видно «дешевле», но не видно насколько.
    discountPct: 'discountPct' in live ? (live as { discountPct?: number }).discountPct ?? null : null,
    isNew: 'isNew' in live ? (live as { isNew?: boolean }).isNew ?? false : false,
  };
}

export function resolveLiveShades<T extends { name?: string; price?: number }>(shades: T[], brand: string): T[] {
  return shades.map((s) => resolveLiveShade(s, brand));
}
