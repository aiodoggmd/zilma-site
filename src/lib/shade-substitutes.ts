// Честная замена оттенка: чего нет в одной линейке, то может быть в другой.
//
// Зачем: мастер открывает палитру, тыкает в нужный оттенок, а он серый — «нет в прайсе», —
// и на этом уходит. При этом ровно тот же цвет часто лежит в соседней линейке в наличии.
//
// ПРАВИЛА ЭКВИВАЛЕНТНОСТИ — не расширять без подтверждения от пользователя:
//
// 1. Совпадают по номеру И по цвету только линейки семьи Wella/Londa:
//    Koleston Perfect ↔ Londa Professional (обе аммиачные, перманент),
//    Color Touch ↔ Londa безаммиачная (обе деми).
//    Illumina и Shinefinity в подмену НЕ входят — у них другая технология, при том же
//    номере результат другой. Matrix, Igora, Ollin — своя нумерация, там 8/0 это иной цвет.
//
// 2. Кросс-замена между аммиачным и безаммиачным РАЗРЕШЕНА, но помечается явно —
//    решение пользователя 2026-09-07: «мастер сам решит, если какого-то красителя нет
//    в аммиачной — брать или нет в безаммиачном». Цвет тот же, стойкость разная.
//
// 3. Код нормализуется по тем же правилам, что и поиск: 6/0 = 6/00 = 66/0 = 6/ = 06/0
//    (натуральный ряд — один оттенок, удвоенная глубина — усиленное закрашивание седины).

export type SubstituteLine = {
  /** ключ статьи-линейки, как в PALETTE_SHADES */
  key: string;
  /** как назвать линейку человеку */
  label: string;
  /** аммиачный перманент или безаммиачный деми */
  type: 'перманент' | 'деми';
};

export const SUBSTITUTE_LINES: SubstituteLine[] = [
  { key: 'koleston', label: 'Koleston Perfect', type: 'перманент' },
  { key: 'londa', label: 'Londa Professional', type: 'перманент' },
  { key: 'colortouch', label: 'Color Touch', type: 'деми' },
  { key: 'londa-demi', label: 'Londa безаммиачная', type: 'деми' },
];

/** Родительный падеж для фразы «деми вместо перманента» */
const GENITIVE: Record<SubstituteLine['type'], string> = {
  'перманент': 'перманента',
  'деми': 'деми',
};

export type ShadeLike = {
  code: string;
  name?: string;
  price?: number;
  promo?: boolean;
};

export type Substitute = {
  line: string;
  code: string;
  name: string;
  price: number;
  promo: boolean;
  /** true — та же стойкость; false — деми вместо перманента или наоборот */
  sameType: boolean;
  note: string;
};

/** Приводит код к «семейному» виду: 6/0, 6/00, 66/0, 6/, 06/0 -> 6/0 */
export function familyKey(code: string): string | null {
  const m = /^(\d{1,2})\/?([0-9a-zа-я+]*)$/i.exec(code.trim().replace(/[.,-]/g, '/'));
  if (!m) return null;
  let depth = m[1];
  // 06 -> 6; 66 -> 6, но 11 оставляем как есть (это реальная глубина 11, а не удвоение)
  if (depth.length === 2 && depth[0] === '0') depth = depth[1];
  else if (depth.length === 2 && depth[0] === depth[1] && depth[0] >= '2') depth = depth[0];
  const tone = m[2].toLowerCase();
  // натуральный ряд: пусто, 0 и 00 — одно и то же
  const canonTone = tone === '' || tone === '0' || tone === '00' ? '0' : tone;
  return `${depth}/${canonTone}`;
}

/**
 * Для каждой линейки строит карту «код оттенка, которого нет в прайсе» -> замены.
 * На вход идут УЖЕ пересчитанные под актуальный прайс оттенки (resolveLiveShades),
 * иначе замена предложит товар по вчерашней цене или тот, что уже кончился.
 */
export function buildSubstitutes(
  palettes: Record<string, ShadeLike[]>
): Record<string, Record<string, Substitute[]>> {
  // семейный ключ -> список доступных товаров по линейкам
  const available = new Map<string, { line: SubstituteLine; shade: ShadeLike }[]>();
  for (const line of SUBSTITUTE_LINES) {
    for (const shade of palettes[line.key] ?? []) {
      if (!shade.name || typeof shade.price !== 'number') continue;
      const key = familyKey(shade.code);
      if (!key) continue;
      if (!available.has(key)) available.set(key, []);
      available.get(key)!.push({ line, shade });
    }
  }

  const out: Record<string, Record<string, Substitute[]>> = {};
  for (const line of SUBSTITUTE_LINES) {
    const map: Record<string, Substitute[]> = {};
    for (const shade of palettes[line.key] ?? []) {
      if (shade.name) continue;                       // этот оттенок и так в наличии
      const key = familyKey(shade.code);
      if (!key) continue;
      const donors = (available.get(key) ?? []).filter((d) => d.line.key !== line.key);
      if (!donors.length) continue;

      const subs: Substitute[] = donors.map((d) => {
        const sameType = d.line.type === line.type;
        return {
          line: d.line.label,
          code: d.shade.code,
          name: d.shade.name!,
          price: d.shade.price!,
          promo: Boolean(d.shade.promo),
          sameType,
          note: sameType
            ? `${d.line.label} — тот же тон и та же стойкость`
            // «вместо перманент» — не по-русски, нужен родительный падеж; «деми» не склоняется
            : `${d.line.label} — тот же тон, но ${d.line.type} вместо ${GENITIVE[line.type]}`,
        };
      });
      // та же стойкость идёт первой: это замена без оговорок
      subs.sort((a, b) => Number(b.sameType) - Number(a.sameType) || a.price - b.price);
      map[shade.code] = subs;
    }
    out[line.key] = map;
  }
  return out;
}
