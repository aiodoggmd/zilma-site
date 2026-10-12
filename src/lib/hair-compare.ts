// Сравнение техник на голове со спины (12.10.2026): две головы рядом и ползунок «сразу после ↔ через 3 мес.».
// Геометрия и цвета — из схем мульт-урока (мультики/episodes/vs-01…/schemes.py). Рисунок — схема, не фото.
// В markdown статьи: <div class="hair-compare" data-left="hl" data-right="bl"></div>
// Техники: hl — мелирование, bl — бейбилайтс, tz — тизилайт, fo — фойляж, ll — лоулайтс;
// открытые и растяжки (вторая часть, 12.10.2026): ba — балаяж, sh — шатуш, at — аиртач, om — омбре, so — сомбре;
// сочетания (третья часть): hlll — мелирование + лоулайтс, babl — балаяж + бейбилайтс, focm — фойляж + колор-мелт,
// zone — мелирование сверху и балаяж снизу. data-grow="0" — без ползунка отрастания.

type RGB = [number, number, number];
type State = 'hl' | 'bl' | 'tz' | 'fo' | 'll' | 'ba' | 'sh' | 'at' | 'om' | 'so' | 'hlll' | 'babl' | 'focm' | 'zone';

const DARK: RGB = [64, 41, 28];
const BLONDE: RGB = [236, 219, 184];
const LOWC: RGB = [112, 74, 46];
const CARAMEL: RGB = [212, 168, 112];                // открытый воздух осветляет слабее фольги
const SOFT: RGB = [150, 106, 68];                    // сомбре: не больше 2–3 тонов от корня
const CAPE = 'rgb(34,34,38)';
const NS = 170;

const mix = (a: RGB, b: RGB, k: number): RGB => [0, 1, 2].map((i) => Math.round(a[i] + (b[i] - a[i]) * k)) as RGB;
const ease = (x: number) => { x = Math.min(Math.max(x, 0), 1); return x * x * (3 - 2 * x); };

function rng(seed: number) {
  return () => {
    seed |= 0; seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const R = rng(5);
const rint = (a: number, b: number) => a + Math.floor(R() * (b - a + 1));
const arr = <T,>(f: () => T) => Array.from({ length: NS }, f);

const BASE = arr(() => mix(DARK, [88, 58, 38], R() * 0.7));
function groups(w0: number, w1: number, g0: number, g1: number, edge: boolean) {
  const out = new Array(NS).fill(0);
  let i = rint(1, 5);
  while (i < NS) {
    const w = rint(w0, w1);
    for (let j = 0; j < w && i + j < NS; j++) out[i + j] = edge && (j === 0 || j === w - 1) ? 0.6 : 1;
    i += w + rint(g0, g1);
  }
  return out;
}
const HL = groups(4, 7, 8, 14, true);                 // мелирование: заметные ленты от корня
const TZ = arr(() => R() < 0.36);                     // тизилайт: тонкие пряди, мягкий вход у корня
const TZ0 = arr(() => R() * 0.16);
const BL = arr(() => R() < 0.55);                     // бейбилайтс: больше половины волос, очень тонко
const BL0 = arr(() => R() * 0.04);
const FO = groups(3, 5, 3, 6, false);                 // фойляж: выборочные пряди, к кончикам светлее
const LIGHT = arr(() => mix([214, 186, 140], [238, 222, 190], R()));
const LL = groups(2, 4, 5, 9, false);                 // лоулайтс: тёмные пряди на светлой базе
// Новые массивы — строго ПОСЛЕ старых: иначе сдвинется случайная последовательность и головы первой части.
const BA = groups(3, 7, 1, 4, false);                 // балаяж: мазки по выборочным прядям, у корня почти нет состава
const BA0 = arr(() => 0.1 + R() * 0.12);
const SH = groups(6, 12, 3, 14, false);                // шатуш: крупные и средние пряди, хаотично
const SH0 = arr(() => 0.18 + R() * 0.3);              // начёс: у каждого волоса граница на своей высоте
const AT = groups(5, 9, 1, 3, false);                 // аиртач: пряди, из которых выдули короткие волоски
const ATK = arr(() => R() < 0.5);                    // в руке остаётся 30–50% пряди — их и осветляют
const AT0 = arr(() => 0.06 + R() * 0.08);
const OM0 = arr(() => 0.44 + R() * 0.05);             // омбре: заметный переход на середине длины
const SO0 = arr(() => 0.08 + R() * 0.12);             // сомбре: переход почти от корня, хаотичные тонкие мазки
const SOK = arr(() => 0.55 + R() * 0.45);
const LLD = groups(3, 5, 3, 6, false).map((v, i) => (HL[i] ? 0 : v));   // лоулайтс между светлыми прядями
const DEEP: RGB = [22, 13, 9];                       // на 2–3 тона темнее основного цвета
const MELT: RGB[] = [[96, 64, 42], [150, 108, 72]];   // колор-мелт: промежуточный и самый светлый оттенок
// «Верх» головы на схеме со спины — пряди, которые начинаются у макушки (середина дуги).
const crown = (i: number) => i > NS * 0.3 && i < NS * 0.7;
// Бейбилайтс на макушке: к краю зоны прядей всё меньше, чтобы не было резкого «столба».
const crownBL = (i: number) => BL[i] && ((i * 37) % 100) / 100 < 1 - Math.abs(i / NS - 0.5) / 0.2;

function strandPts(u: number, n: number) {
  const c = 2 * (u - 0.5), a = Math.PI * (1 - u);
  const p = [[0.5 + 0.19 * Math.cos(a), 0.31 - 0.19 * Math.sin(a)], [0.5 + c * 0.26, 0.24 + 0.05 * c * c],
    [0.5 + c * 0.27, 0.62], [0.5 + c * 0.2, 0.95 - 0.1 * c * c]];
  const pts: [number, number, number][] = [];
  for (let k = 0; k <= n; k++) {
    const s = k / n, q = 1 - s;
    const f = (i: number) => q ** 3 * p[0][i] + 3 * q * q * s * p[1][i] + 3 * q * s * s * p[2][i] + s ** 3 * p[3][i];
    pts.push([f(0), f(1), s]);
  }
  return pts;
}
const PTS = Array.from({ length: NS }, (_, i) => strandPts(i / (NS - 1), 60));

function color(i: number, s: number, state: State, g: number): RGB {   // g — отросший корень, доля длины
  const base = BASE[i];
  switch (state) {
    case 'hl': return s < g ? base : mix(base, BLONDE, HL[i]);
    case 'tz': {
      if (s < g || !TZ[i]) return base;
      const s0 = Math.max(TZ0[i], g);
      return mix(base, BLONDE, ease((s - s0) / 0.14) * (0.55 + 0.35 * s));
    }
    case 'bl': {
      if (!BL[i]) return base;
      const s0 = g > 0 ? g + BL0[i] : 0;
      if (s < s0) return base;
      return mix(base, BLONDE, (0.42 + 0.12 * s) * (g > 0 ? ease((s - s0) / 0.07) : 1));
    }
    case 'fo': return FO[i] ? mix(base, BLONDE, ease((s - g - 0.18) / 0.55) * 0.95) : base;
    case 'll': return LL[i] && s > g + 0.03 ? mix(LIGHT[i], LOWC, 0.85) : LIGHT[i];
    case 'ba': return BA[i] ? mix(base, CARAMEL, Math.min(1, ease((s - g - BA0[i]) / 0.7) * 1.08)) : base;
    case 'sh': return SH[i] ? mix(base, CARAMEL, ease((s - g - SH0[i]) / 0.3) * 0.95) : base;
    case 'at': return AT[i] && ATK[i] ? mix(base, BLONDE, ease((s - g - AT0[i]) / 0.5) * 0.95) : base;
    case 'om': return mix(base, BLONDE, ease((s - g - OM0[i]) / 0.14) * 0.9);
    case 'so': return mix(base, SOFT, ease((s - g - SO0[i]) / 0.4) * SOK[i]);
    case 'hlll':
      if (HL[i]) return color(i, s, 'hl', g);
      return LLD[i] && s > g + 0.03 ? mix(base, DEEP, 0.95) : base;
    case 'babl': {
      const a = color(i, s, 'ba', g);
      if (!crownBL(i)) return a;
      const b = color(i, s, 'bl', g);
      return a[0] + a[1] + a[2] >= b[0] + b[1] + b[2] ? a : b;
    }
    case 'focm': {
      const k = ease((s - 0.12) / 0.5), melt = k < 0.5 ? mix(base, MELT[0], k * 2) : mix(MELT[0], MELT[1], k * 2 - 1);
      return FO[i] ? mix(melt, BLONDE, ease((s - 0.18) / 0.55) * 0.95) : melt;
    }
    case 'zone': return color(i, s, crown(i) ? 'hl' : 'ba', g);
  }
}

const NAMES: Record<State, string> = { hl: 'Мелирование', bl: 'Бейбилайтс', tz: 'Тизилайт', fo: 'Фойляж', ll: 'Лоулайтс',
  ba: 'Балаяж', sh: 'Шатуш', at: 'Аиртач', om: 'Омбре', so: 'Сомбре',
  hlll: 'Мелирование + лоулайтс', babl: 'Балаяж + бейбилайтс', focm: 'Фойляж + колор-мелт', zone: 'Мелирование и балаяж по зонам' };
const CAPS: Record<State, [string, string]> = {
  hl: ['чёткие светлые ленты от корня', 'резкая граница отросшего корня'],
  bl: ['сверхтонкие пряди, мягкое сияние', 'разница цвета едва заметна'],
  tz: ['тонкие пряди, мягкий корень', 'граница размыта начёсом'],
  fo: ['корень свой, к кончикам светлее', 'корень не осветляли — границы нет'],
  ll: ['тёмные пряди на светлой базе', 'тёмные пряди отходят от корня'],
  ba: ['мазки к кончикам, у корня почти нет состава', 'корень отрастает без чёткой границы'],
  sh: ['растяжка: тёмный корень, светлые концы', 'граница размыта начёсом'],
  at: ['плавный переход к светлым концам', 'отрастание почти незаметно'],
  om: ['заметный переход на середине длины', 'корень свой — переход ушёл ниже'],
  so: ['мягкий переход почти от корня', 'граница размыта, корень свой'],
  hlll: ['светлые и тёмные пряди вместе — объём цвета', 'у светлых прядей граница корня заметна'],
  babl: ['балаяж по длине, бейбилайтс на макушке', 'корень отрастает без чёткой границы'],
  focm: ['кончики осветлены, переход к корню сглажен', 'кончики осветлены, переход к корню сглажен'],
  zone: ['сверху мелирование, снизу балаяж', 'сверху граница заметна, снизу — нет'],
};

function draw(cv: HTMLCanvasElement, state: State, months: number) {
  const w = cv.getBoundingClientRect().width;
  if (!w) return;
  const S = Math.round(w * Math.min(window.devicePixelRatio || 1, 2));
  if (cv.width !== S) { cv.width = S; cv.height = S; }
  const ctx = cv.getContext('2d');
  if (!ctx) return;
  const g = (0.18 * months) / 3;                    // 3 месяца ≈ 18% длины на схеме
  ctx.clearRect(0, 0, S, S);
  ctx.fillStyle = CAPE;
  ctx.beginPath();
  if (ctx.roundRect) ctx.roundRect(0.16 * S, 0.62 * S, 0.68 * S, 0.46 * S, 0.12 * S);
  else ctx.rect(0.16 * S, 0.62 * S, 0.68 * S, 0.46 * S);
  ctx.fill();
  for (let i = 0; i < NS; i++) {
    const thin = (state === 'bl' && BL[i]) || (state === 'tz' && TZ[i]) || (state === 'babl' && crownBL(i));
    ctx.lineWidth = Math.max(1, (thin ? 0.004 : 0.0058) * S);
    const p = PTS[i];
    let prev = '';
    for (let k = 0; k < p.length - 1; k++) {
      const c = color(i, p[k][2], state, g).join(',');
      if (c !== prev) {
        if (prev) ctx.stroke();
        ctx.strokeStyle = `rgb(${c})`;
        ctx.beginPath();
        ctx.moveTo(p[k][0] * S, p[k][1] * S);
        prev = c;
      }
      ctx.lineTo(p[k + 1][0] * S, p[k + 1][1] * S);
    }
    ctx.stroke();
  }
}

const monthsLabel = (m: number) =>
  m < 0.05 ? 'сразу после окрашивания' : `через ${m.toFixed(1).replace('.0', '').replace('.', ',')} мес.`;

function build(box: HTMLElement, n: number) {
  const states = [box.dataset.left || 'hl', box.dataset.right || 'bl'] as State[];
  const grow = box.dataset.grow !== '0';
  box.setAttribute('role', 'group');
  box.setAttribute('aria-label', `Схема: ${NAMES[states[0]]} и ${NAMES[states[1]]}` + (grow ? ' сразу после окрашивания и через 3 месяца' : ''));
  box.innerHTML = `<div class="hc-heads">${states.map((s) => `
      <figure class="hc-head"><canvas aria-hidden="true"></canvas>
        <figcaption><b>${NAMES[s]}</b><span data-cap="${s}"></span></figcaption></figure>`).join('')}
    </div>
    <div class="hc-grow"${grow ? '' : ' hidden'}>
      <button type="button" class="hc-play">▶ Показать отрастание</button>
      <input type="range" id="hc-range-${n}" min="0" max="3" step="0.01" value="0" aria-label="Сколько времени прошло, месяцев">
      <output for="hc-range-${n}"></output>
    </div>
    <p class="hc-note">Схема, не фото: показан рисунок прядей${grow ? ' и граница отросшего корня' : ''}.</p>`;
  const canvases = [...box.querySelectorAll('canvas')];
  const input = box.querySelector('input') as HTMLInputElement;
  const out = box.querySelector('output') as HTMLOutputElement;
  const caps = [...box.querySelectorAll<HTMLElement>('[data-cap]')];
  const render = () => {
    const m = +input.value;
    out.textContent = monthsLabel(m);
    canvases.forEach((cv, i) => draw(cv, states[i], m));
    caps.forEach((el) => { el.textContent = CAPS[el.dataset.cap as State][grow && m > 1.5 ? 1 : 0]; });
  };
  let raf = 0;
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  box.querySelector('.hc-play')?.addEventListener('click', () => {
    cancelAnimationFrame(raf);
    const from = +input.value, to = from > 2.9 ? 0 : 3;
    if (reduce) { input.value = String(to); render(); return; }
    const t0 = performance.now(), dur = (2600 * Math.abs(to - from)) / 3 + 1;
    const tick = (t: number) => {
      const k = ease((t - t0) / dur);
      input.value = String(from + (to - from) * k);
      render();
      if (k < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
  });
  input.addEventListener('input', () => { cancelAnimationFrame(raf); render(); });
  // Рисуем сразу и заново при смене ширины блока (поворот телефона).
  new ResizeObserver(render).observe(box);
}

export function initHairCompare() {
  document.querySelectorAll<HTMLElement>('.hair-compare').forEach((box, i) => build(box, i));
}
