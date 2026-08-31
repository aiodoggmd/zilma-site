import priceItems from '../data/priceItems.json';

// Последний "слово"-токен в 1С-имени товара — это и есть артикул (та же логика, что в
// Price/build_price_current.py:article() и в scripts/xlsx-to-price-items.py).
function articleOf(name: string): string {
  const toks = name.trim().split(/\s+/);
  return toks[toks.length - 1] ?? '';
}

// Сигнал "внутри этого бренда два разных товара делят один и тот же артикул-токен" —
// найдено программно (2026-08-31): WELLA "8/38" (Illumina и Shinefinity — это РАЗНЫЕ
// линии, но в прайсе у них общий брэнд WELLA) и OLLIN "0-88". Настоящие числовые SKU
// (647, 5192 и т.п.) уникальны по всему прайсу — коллизии бывают только у коротких
// "тоновых" кодов, которые разные линии одного бренда совпадают друг с другом. Гадать,
// какой из двух это на самом деле, не будем — для такого ключа оттенок просто не трогаем
// (остаётся с тем, что уже было в data-файле), вместо того чтобы молча подставить не тот
// товар или ошибочно пометить как "нет в наличии".
const AMBIGUOUS = Symbol('ambiguous');

const priceByBrandArticle = new Map<string, Map<string, (typeof priceItems)[number] | typeof AMBIGUOUS>>();
for (const it of priceItems) {
  const brand = it.brand.toUpperCase();
  if (!priceByBrandArticle.has(brand)) priceByBrandArticle.set(brand, new Map());
  const brandMap = priceByBrandArticle.get(brand)!;
  const key = articleOf(it.name);
  brandMap.set(key, brandMap.has(key) ? AMBIGUOUS : it);
}

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
  const live = priceByBrandArticle.get(brand.toUpperCase())?.get(articleOf(shade.name));
  if (live === AMBIGUOUS) return shade; // не трогаем — не гадаем, какой из нескольких это
  if (!live) {
    const { name, price, ...rest } = shade as Record<string, unknown>;
    return rest as T;
  }
  return { ...shade, name: live.name, price: live.price };
}

export function resolveLiveShades<T extends { name?: string; price?: number }>(shades: T[], brand: string): T[] {
  return shades.map((s) => resolveLiveShade(s, brand));
}
