import type { APIRoute } from 'astro';

export const prerender = false;

interface SelectedItem {
  name: string;
  price: number;
  qty: number;
  brand: string;
  promo: boolean;
}

const MAX_FILE_BYTES = 4 * 1024 * 1024;
// Telegram режет сообщение на 4096 символов — длинный свободный комментарий (если кто-то
// вручную впишет много текста) уходит отдельным .txt вместо того, чтобы резать/ронять заявку.
const INLINE_COMMENT_LIMIT = 3500;

// Человеку физически не хватит времени увидеть форму и отправить её быстрее этого порога —
// более быстрая отправка почти наверняка бот, заполняющий поля сразу после загрузки страницы.
const MIN_SUBMIT_MS = 800;

// Rate-limit по IP — best-effort, не полноценная защита: карта живёт в памяти одного
// serverless-инстанса Vercel и обнуляется при холодном старте/новом деплое (без БД/Redis
// постоянного стораджа для этого нет). Отсекает грубый спам-скрипт, не защищает от
// распределённой атаки с разных IP — для B2B-сайта без корзины с оплатой этого достаточно.
const RATE_LIMIT_WINDOW_MS = 10 * 60 * 1000;
const RATE_LIMIT_MAX = 5;
const rateLimitHits = new Map<string, number[]>();

// Клиентский accept=".pdf,.doc..." — чисто визуальная подсказка, обходится тривиально
// (переименовать файл). Сервер сверяет реальные первые байты файла с ожидаемой сигнатурой
// формата, а не только расширение из имени — расширение можно вписать любое.
const ALLOWED_EXTENSIONS = new Set(['jpg', 'jpeg', 'png', 'webp', 'gif', 'pdf', 'doc', 'docx', 'xls', 'xlsx']);

function getFileExtension(filename: string): string {
  const match = /\.([a-z0-9]+)$/i.exec(filename);
  return match ? match[1].toLowerCase() : '';
}

async function hasValidFileSignature(file: File, ext: string): Promise<boolean> {
  const head = new Uint8Array(await file.slice(0, 12).arrayBuffer());
  switch (ext) {
    case 'jpg':
    case 'jpeg':
      return head[0] === 0xff && head[1] === 0xd8 && head[2] === 0xff;
    case 'png':
      return head[0] === 0x89 && head[1] === 0x50 && head[2] === 0x4e && head[3] === 0x47;
    case 'gif':
      return head[0] === 0x47 && head[1] === 0x49 && head[2] === 0x46;
    case 'webp':
      return (
        head[0] === 0x52 &&
        head[1] === 0x49 &&
        head[2] === 0x46 &&
        head[3] === 0x46 &&
        head[8] === 0x57 &&
        head[9] === 0x45 &&
        head[10] === 0x42 &&
        head[11] === 0x50
      );
    case 'pdf':
      return head[0] === 0x25 && head[1] === 0x50 && head[2] === 0x44 && head[3] === 0x46; // %PDF
    case 'doc':
    case 'xls':
      // Старый формат Office (OLE Compound File).
      return head[0] === 0xd0 && head[1] === 0xcf && head[2] === 0x11 && head[3] === 0xe0;
    case 'docx':
    case 'xlsx':
      // Новый формат Office — это ZIP-архив (PK\x03\x04).
      return head[0] === 0x50 && head[1] === 0x4b;
    default:
      return false;
  }
}

function getClientIp(request: Request): string {
  const fwd = request.headers.get('x-forwarded-for');
  if (fwd) return fwd.split(',')[0].trim();
  return request.headers.get('x-real-ip') ?? 'unknown';
}

function isRateLimited(ip: string): boolean {
  const now = Date.now();
  const hits = (rateLimitHits.get(ip) ?? []).filter((t) => now - t < RATE_LIMIT_WINDOW_MS);
  hits.push(now);
  rateLimitHits.set(ip, hits);

  // Самоочистка карты, чтобы она не росла бесконечно на долгоживущем тёплом инстансе.
  if (rateLimitHits.size > 2000) {
    for (const [key, arr] of rateLimitHits) {
      if (!arr.some((t) => now - t < RATE_LIMIT_WINDOW_MS)) rateLimitHits.delete(key);
    }
  }

  return hits.length > RATE_LIMIT_MAX;
}

function parseSelectedItems(raw: string): SelectedItem[] {
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((x) => x && typeof x.name === 'string' && x.name.trim())
      .map((x) => ({
        name: String(x.name).slice(0, 300),
        price: Number(x.price) || 0,
        qty: Math.max(1, Math.min(9999, Math.floor(Number(x.qty)) || 1)),
        brand: typeof x.brand === 'string' ? x.brand.slice(0, 100) : '',
        promo: x.promo === true,
      }));
  } catch {
    return [];
  }
}

// Таблица в стиле накладной 1С: группировка по бренду, № / Товар / Кол-во / Акция / Цена / Сумма + итого.
// BOM в начале — чтобы Excel на Windows сразу распознал UTF-8 и не показал кракозябры.
function buildCsv(items: SelectedItem[]): string {
  const cell = (v: string | number) => {
    const s = String(v);
    return /[;"\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };

  const rows: string[] = [];
  rows.push(['№', 'Товар', 'Кол-во', 'Акция', 'Цена', 'Сумма'].map(cell).join(';'));

  let total = 0;
  let n = 0;
  let lastBrand: string | null = null;
  for (const it of items) {
    const brand = it.brand || 'Без бренда';
    if (brand !== lastBrand) {
      rows.push(cell(brand));
      lastBrand = brand;
    }
    n += 1;
    const sum = Math.round(it.price * it.qty * 100) / 100;
    total += sum;
    rows.push([n, it.name, it.qty, it.promo ? 'Да' : '', it.price, sum].map(cell).join(';'));
  }
  total = Math.round(total * 100) / 100;
  rows.push(['', '', '', '', 'Итого:', total].map(cell).join(';'));
  rows.push('');
  rows.push(cell(`Всего наименований: ${items.length}, на сумму ${total.toFixed(2)} руб.`));

  return '﻿' + rows.join('\r\n');
}

// Метка даты+времени (Europe/Moscow) для имени файла — без БД полноценную порядковую нумерацию
// не сделать, но метка даёт уникальное имя на каждую заявку, чтобы файлы не перезаписывали друг друга.
function fileTimestamp(): string {
  const parts = new Intl.DateTimeFormat('ru-RU', {
    timeZone: 'Europe/Moscow',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).formatToParts(new Date());
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? '00';
  return `${get('year')}-${get('month')}-${get('day')}-${get('hour')}${get('minute')}${get('second')}`;
}

const WHATSAPP_API_VERSION = 'v21.0';

// Отправка заявки в WhatsApp через Meta Cloud API — необязательная, best-effort: если переменные
// не заданы или Meta вернёт ошибку (например, не подтверждён номер-получатель, или нужен
// заранее одобренный шаблон вне 24-часового окна диалога), заявка всё равно считается успешной —
// Telegram-доставка выше уже прошла и остаётся основным каналом.
async function sendWhatsappOrder(params: {
  token: string;
  phoneId: string;
  recipient: string;
  name: string;
  contact: string;
  messenger: string;
  comment: string;
  commentAsFile: boolean;
  selectedItems: SelectedItem[];
  itemsTotal: number;
  timestamp: string;
  file: File | null;
}): Promise<void> {
  const { token, phoneId, recipient, name, contact, messenger, comment, commentAsFile, selectedItems, itemsTotal, timestamp, file } = params;
  const base = `https://graph.facebook.com/${WHATSAPP_API_VERSION}/${phoneId}`;
  const authHeaders = { Authorization: `Bearer ${token}` };

  async function callApi(body: Record<string, unknown>) {
    const res = await fetch(`${base}/messages`, {
      method: 'POST',
      headers: { ...authHeaders, 'Content-Type': 'application/json' },
      body: JSON.stringify({ messaging_product: 'whatsapp', to: recipient, ...body }),
    });
    if (!res.ok) console.error('order.ts: WhatsApp API error', await res.text());
    return res;
  }

  async function uploadMedia(blob: Blob, filename: string, mimeType: string): Promise<string | null> {
    const form = new FormData();
    form.set('messaging_product', 'whatsapp');
    form.set('file', blob, filename);
    form.set('type', mimeType);
    const res = await fetch(`${base}/media`, { method: 'POST', headers: authHeaders, body: form });
    if (!res.ok) {
      console.error('order.ts: WhatsApp media upload error', await res.text());
      return null;
    }
    const data = (await res.json()) as { id?: string };
    return data.id ?? null;
  }

  const text =
    `*Новая заявка с сайта Zilma*\n\n` +
    `*Имя:* ${name}\n` +
    `*Контакт:* ${contact}` +
    (messenger ? `\n*Удобный мессенджер:* ${messenger}` : '') +
    (selectedItems.length
      ? `\n*Товары из прайса:* ${selectedItems.length} поз. на ${itemsTotal.toFixed(2)} ₽ — таблица во вложении`
      : '') +
    (comment
      ? commentAsFile
        ? `\n*Комментарий:* список большой — смотрите приложенный файл (${comment.length} симв.)`
        : `\n*Комментарий:* ${comment}`
      : '') +
    (file ? `\n*Приложен файл:* ${file.name}` : '');

  await callApi({ type: 'text', text: { body: text } });

  if (selectedItems.length) {
    const csvId = await uploadMedia(
      new Blob([buildCsv(selectedItems)], { type: 'text/csv' }),
      `zayavka-tovary-${timestamp}.csv`,
      'text/csv'
    );
    if (csvId) {
      await callApi({ type: 'document', document: { id: csvId, filename: `zayavka-tovary-${timestamp}.csv` } });
    }
  }

  if (commentAsFile) {
    const commentId = await uploadMedia(
      new Blob([comment], { type: 'text/plain' }),
      `zayavka-kommentariy-${timestamp}.txt`,
      'text/plain'
    );
    if (commentId) {
      await callApi({ type: 'document', document: { id: commentId, filename: `zayavka-kommentariy-${timestamp}.txt` } });
    }
  }

  if (file) {
    const isImage = file.type.startsWith('image/');
    const mediaId = await uploadMedia(file, file.name, file.type || 'application/octet-stream');
    if (mediaId) {
      await callApi(
        isImage ? { type: 'image', image: { id: mediaId } } : { type: 'document', document: { id: mediaId, filename: file.name } }
      );
    }
  }
}

export const POST: APIRoute = async ({ request }) => {
  if (isRateLimited(getClientIp(request))) {
    return new Response(JSON.stringify({ ok: false, error: 'rate_limited' }), { status: 429 });
  }

  let form: FormData;
  try {
    form = await request.formData();
  } catch {
    return new Response(JSON.stringify({ ok: false, error: 'bad_form' }), { status: 400 });
  }

  const name = String(form.get('name') ?? '').trim();
  const contact = String(form.get('contact') ?? '').trim();
  const messenger = String(form.get('messenger') ?? '').trim().slice(0, 50);
  const comment = String(form.get('comment') ?? '').trim();
  const attachment = form.get('attachment');
  const file = attachment instanceof File && attachment.size > 0 ? attachment : null;
  const selectedItems = parseSelectedItems(String(form.get('items_json') ?? ''));

  // Honeypot + слишком быстрая отправка — почти наверняка бот. Отвечаем притворным
  // успехом, ничего никуда не отправляя: так бот не понимает, что его поймали, и не
  // подстраивается (в отличие от явной ошибки).
  const honeypot = String(form.get('hp_field') ?? '').trim();
  const renderedAt = Number(form.get('form_rendered_at') ?? NaN);
  // Форме и так нужен JS для отправки (submit идёт через fetch, у <form> нет action) —
  // значит у настоящего браузера метка времени всегда проставлена. Её отсутствие/некорректность
  // само по себе подозрительно, как и отправка раньше MIN_SUBMIT_MS после рендера формы.
  const timingSuspicious = !Number.isFinite(renderedAt) || Date.now() - renderedAt < MIN_SUBMIT_MS;
  if (honeypot || timingSuspicious) {
    return new Response(JSON.stringify({ ok: true }), { status: 200 });
  }

  if (!name || !contact) {
    return new Response(JSON.stringify({ ok: false, error: 'missing_fields' }), { status: 400 });
  }
  if (name.length > 200 || contact.length > 200) {
    return new Response(JSON.stringify({ ok: false, error: 'too_long' }), { status: 400 });
  }
  if (file && file.size > MAX_FILE_BYTES) {
    return new Response(JSON.stringify({ ok: false, error: 'file_too_large' }), { status: 400 });
  }
  if (file) {
    const ext = getFileExtension(file.name);
    if (!ALLOWED_EXTENSIONS.has(ext) || !(await hasValidFileSignature(file, ext))) {
      return new Response(JSON.stringify({ ok: false, error: 'file_type_invalid' }), { status: 400 });
    }
  }

  const token = import.meta.env.TELEGRAM_BOT_TOKEN;
  const chatId = import.meta.env.TELEGRAM_CHAT_ID;
  if (!token || !chatId) {
    console.error('order.ts: TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID не заданы');
    return new Response(JSON.stringify({ ok: false, error: 'server_not_configured' }), { status: 500 });
  }

  const esc = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const commentAsFile = comment.length > INLINE_COMMENT_LIMIT;
  const itemsTotal = Math.round(selectedItems.reduce((s, it) => s + it.price * it.qty, 0) * 100) / 100;

  const messageText =
    `<b>Новая заявка с сайта Zilma</b>\n\n` +
    `<b>Имя:</b> ${esc(name)}\n` +
    `<b>Контакт:</b> ${esc(contact)}` +
    (messenger ? `\n<b>Удобный мессенджер:</b> ${esc(messenger)}` : '') +
    (selectedItems.length
      ? `\n<b>Товары из прайса:</b> ${selectedItems.length} поз. на ${itemsTotal.toFixed(2)} ₽ — таблица во вложении`
      : '') +
    (comment
      ? commentAsFile
        ? `\n<b>Комментарий:</b> список большой — смотрите приложенный файл (${comment.length} симв.)`
        : `\n<b>Комментарий:</b> ${esc(comment)}`
      : '') +
    (file ? `\n<b>Приложен файл:</b> ${esc(file.name)}` : '');

  const tgRes = await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ chat_id: chatId, text: messageText, parse_mode: 'HTML' }),
  });

  if (!tgRes.ok) {
    console.error('order.ts: Telegram API error', await tgRes.text());
    return new Response(JSON.stringify({ ok: false, error: 'telegram_failed' }), { status: 502 });
  }

  const timestamp = fileTimestamp();

  if (selectedItems.length) {
    const csvForm = new FormData();
    csvForm.set('chat_id', chatId);
    csvForm.set(
      'document',
      new Blob([buildCsv(selectedItems)], { type: 'text/csv; charset=utf-8' }),
      `zayavka-tovary-${timestamp}.csv`
    );
    const csvRes = await fetch(`https://api.telegram.org/bot${token}/sendDocument`, {
      method: 'POST',
      body: csvForm,
    });
    if (!csvRes.ok) {
      // Шапка заявки уже доставлена — таблица best-effort, не проваливаем весь запрос.
      console.error('order.ts: Telegram CSV send error', await csvRes.text());
    }
  }

  if (commentAsFile) {
    const commentForm = new FormData();
    commentForm.set('chat_id', chatId);
    commentForm.set('document', new Blob([comment], { type: 'text/plain; charset=utf-8' }), `zayavka-kommentariy-${timestamp}.txt`);

    const commentRes = await fetch(`https://api.telegram.org/bot${token}/sendDocument`, {
      method: 'POST',
      body: commentForm,
    });
    if (!commentRes.ok) {
      console.error('order.ts: Telegram comment-file send error', await commentRes.text());
    }
  }

  if (file) {
    const isImage = file.type.startsWith('image/');
    const method = isImage ? 'sendPhoto' : 'sendDocument';
    const field = isImage ? 'photo' : 'document';

    const fileForm = new FormData();
    fileForm.set('chat_id', chatId);
    fileForm.set(field, file, file.name);

    const fileRes = await fetch(`https://api.telegram.org/bot${token}/${method}`, {
      method: 'POST',
      body: fileForm,
    });

    if (!fileRes.ok) {
      // Текст заявки уже доставлен — файл best-effort, не проваливаем весь запрос из-за него.
      console.error('order.ts: Telegram file send error', await fileRes.text());
      return new Response(JSON.stringify({ ok: true, warning: 'file_not_delivered' }), { status: 200 });
    }
  }

  const waToken = import.meta.env.WHATSAPP_TOKEN;
  const waPhoneId = import.meta.env.WHATSAPP_PHONE_ID;
  const waRecipient = import.meta.env.WHATSAPP_RECIPIENT;
  if (waToken && waPhoneId && waRecipient) {
    try {
      await sendWhatsappOrder({
        token: waToken,
        phoneId: waPhoneId,
        recipient: waRecipient,
        name,
        contact,
        messenger,
        comment,
        commentAsFile,
        selectedItems,
        itemsTotal,
        timestamp,
        file,
      });
    } catch (err) {
      // Best-effort: Telegram (основной канал) уже доставлен выше, WhatsApp не должен ронять заявку.
      console.error('order.ts: WhatsApp send failed', err);
    }
  }

  return new Response(JSON.stringify({ ok: true }), { status: 200 });
};
