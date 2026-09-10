// @ts-check
// Конфиг для российского хостинга. В день переезда заменит astro.config.mjs.
//
// Отличий всего два, потому что сайт к этому давно готов: у ВСЕХ страниц уже стоит
// prerender = true, то есть они и так собираются в готовые файлы. Серверным был ровно
// один маршрут — приём заявки, и его заменяет deploy/order.php на самом хостинге.
//
//   1. output: 'static' вместо 'server' и без адаптера Vercel — на выходе обычные
//      html-файлы, которые кладутся в public_html.
//   2. Аналитика Vercel не подключается (её и так убираем по 152-ФЗ: она собирает
//      данные посетителей на зарубежных серверах). Яндекс.Метрика остаётся.
//
// Перед заменой не забыть: удалить src/pages/api/order.ts (он требует сервера) и убрать
// <Analytics /> с <SpeedInsights /> из BaseLayout.astro — иначе сборка упадёт.
import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';

export default defineConfig({
  site: 'https://www.zilma.pro',
  output: 'static',
  integrations: [sitemap()],
  build: {
    // Astro по умолчанию кладёт страницу как order/index.html — это ровно то, что нужно
    // обычному хостингу: адрес /order/ открывается без единой настройки.
    format: 'directory',
  },
});
