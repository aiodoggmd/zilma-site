// Поиск товара по (бренд, артикул) — общая логика для сборки сайта (палитры оттенков,
// resolve-live-price.ts) и для рантайма страницы статьи (кнопки «+ В заявку» в таблицах
// и карточках). Раньше эти два места считали артикул каждое по-своему, и правка в одном
// не доезжала до другого.

// Артикул = последний «слово»-токен 1С-имени товара (та же логика, что в
// Price/build_price_current.py:article() и в scripts/xlsx-to-price-items.py).
export function articleOf(name: string): string {
  const toks = name.trim().split(/\s+/);
  return (toks[toks.length - 1] ?? '').replace(/\.$/, '');
}

// Составной код («4669-3891», «313760/2236000») — след ребрендинга: актуален ПЕРВЫЙ
// номер, второй остался от прежней карточки товара. В статьях товар подписан первым
// номером, потому что мастер знает его именно так, — значит ключи с обеих сторон должны
// сходиться независимо от того, успел ли 1С дописать хвост.
//
// Обе части требуют не меньше трёх цифр: у OLLIN артикул вида «010-7» — это код оттенка,
// а не ребрендинг, и обрезать его до «010» нельзя (проверено на реальном прайсе: иначе
// 10/7 и 10/73 схлопываются в один ключ).
export function baseArticle(token: string): string {
  const m = /^(\d{3,10})[-/]\d{3,10}$/.exec(token);
  return m ? m[1] : token;
}

// «Внутри бренда два разных товара делят один ключ» — найдено программно (2026-08-31):
// WELLA «8/38» (Illumina и Shinefinity — разные линии под общим брендом), OLLIN «0-88».
// Гадать, какой из двух имелся в виду, не будем: такую строку просто не трогаем.
export const AMBIGUOUS = Symbol('ambiguous');

export type ArticleMatch<T> = T | typeof AMBIGUOUS | undefined;

/**
 * Индекс по (бренд, артикул). Точные совпадения и совпадения по первой части составного
 * кода лежат в РАЗНЫХ картах, и точная всегда проверяется первой: так добавление запасного
 * ключа не может увести уже работающее совпадение к другому товару. Коллизии в запасной
 * карте (у одноразовой продукции коды вида «0200-233» и «0200-234») остаются коллизиями и
 * просто не срабатывают.
 */
export function buildArticleIndex<T extends { name: string; brand: string }>(items: readonly T[]) {
  const exact = new Map<string, Map<string, T | typeof AMBIGUOUS>>();
  const alias = new Map<string, Map<string, T | typeof AMBIGUOUS>>();

  const put = (store: typeof exact, brand: string, key: string, item: T) => {
    if (!store.has(brand)) store.set(brand, new Map());
    const brandMap = store.get(brand)!;
    brandMap.set(key, brandMap.has(key) ? AMBIGUOUS : item);
  };

  for (const it of items) {
    const brand = it.brand.toUpperCase();
    const token = articleOf(it.name);
    put(exact, brand, token, it);
    const base = baseArticle(token);
    if (base !== token) put(alias, brand, base, it);
  }

  return function findByArticle(brand: string, key: string): ArticleMatch<T> {
    const b = brand.toUpperCase();
    const k = key.trim().replace(/\.$/, '');
    const direct = exact.get(b)?.get(k);
    if (direct) return direct;                    // в том числе AMBIGUOUS — значит не трогаем
    const aliased = alias.get(b)?.get(k);
    if (aliased) return aliased;
    // Обратное направление: в статье записан составной код, а в прайсе остался короткий.
    const base = baseArticle(k);
    return base !== k ? exact.get(b)?.get(base) : undefined;
  };
}
