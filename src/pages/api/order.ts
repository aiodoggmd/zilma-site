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

export const POST: APIRoute = async ({ request }) => {
  let form: FormData;
  try {
    form = await request.formData();
  } catch {
    return new Response(JSON.stringify({ ok: false, error: 'bad_form' }), { status: 400 });
  }

  const name = String(form.get('name') ?? '').trim();
  const contact = String(form.get('contact') ?? '').trim();
  const comment = String(form.get('comment') ?? '').trim();
  const attachment = form.get('attachment');
  const file = attachment instanceof File && attachment.size > 0 ? attachment : null;
  const selectedItems = parseSelectedItems(String(form.get('items_json') ?? ''));

  if (!name || !contact) {
    return new Response(JSON.stringify({ ok: false, error: 'missing_fields' }), { status: 400 });
  }
  if (name.length > 200 || contact.length > 200) {
    return new Response(JSON.stringify({ ok: false, error: 'too_long' }), { status: 400 });
  }
  if (file && file.size > MAX_FILE_BYTES) {
    return new Response(JSON.stringify({ ok: false, error: 'file_too_large' }), { status: 400 });
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

  return new Response(JSON.stringify({ ok: true }), { status: 200 });
};
