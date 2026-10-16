import { getCollection } from 'astro:content';

// Все статьи сайта. Черновик (`draft: true` во frontmatter) виден на локальном сервере, чтобы
// Олег посмотрел его до публикации, но в сборку для сайта не попадает. Раньше черновик приходилось
// держать в docs/drafts и показать его было нельзя: сайт не прячет даже статьи с будущей датой,
// и любой publish выложил бы статью из src/content (16.10.2026, статья о седине).
export async function getArticles() {
  return getCollection('articles', ({ data }) => !(import.meta.env.PROD && data.draft));
}
