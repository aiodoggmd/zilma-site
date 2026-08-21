import type { APIRoute } from 'astro';

export const prerender = false;

export const POST: APIRoute = async ({ request }) => {
  let data: Record<string, unknown>;
  try {
    data = await request.json();
  } catch {
    return new Response(JSON.stringify({ ok: false, error: 'bad_json' }), { status: 400 });
  }

  const name = String(data.name ?? '').trim();
  const contact = String(data.contact ?? '').trim();
  const comment = String(data.comment ?? '').trim();

  if (!name || !contact) {
    return new Response(JSON.stringify({ ok: false, error: 'missing_fields' }), { status: 400 });
  }
  if (name.length > 200 || contact.length > 200 || comment.length > 2000) {
    return new Response(JSON.stringify({ ok: false, error: 'too_long' }), { status: 400 });
  }

  const token = import.meta.env.TELEGRAM_BOT_TOKEN;
  const chatId = import.meta.env.TELEGRAM_CHAT_ID;
  if (!token || !chatId) {
    console.error('order.ts: TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID не заданы');
    return new Response(JSON.stringify({ ok: false, error: 'server_not_configured' }), { status: 500 });
  }

  const esc = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const text =
    `<b>Новая заявка с сайта Zilma</b>\n\n` +
    `<b>Имя:</b> ${esc(name)}\n` +
    `<b>Контакт:</b> ${esc(contact)}` +
    (comment ? `\n<b>Комментарий:</b> ${esc(comment)}` : '');

  const tgRes = await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ chat_id: chatId, text, parse_mode: 'HTML' }),
  });

  if (!tgRes.ok) {
    console.error('order.ts: Telegram API error', await tgRes.text());
    return new Response(JSON.stringify({ ok: false, error: 'telegram_failed' }), { status: 502 });
  }

  return new Response(JSON.stringify({ ok: true }), { status: 200 });
};
