import { defineCollection } from 'astro:content';
import { glob } from 'astro/loaders';
import { z } from 'astro/zod';

const articles = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/articles' }),
  schema: z.object({
    title: z.string(),
    // Короткий заголовок ТОЛЬКО для вкладки браузера и поисковой выдачи (≈57 символов,
    // чтобы вместе с « — Zilma» уложиться в 65 — дальше поисковик обрезает многоточием).
    // На самой странице и на карточке в ленте по-прежнему показывается полный title.
    seoTitle: z.string().optional(),
    description: z.string(),
    // Короткий ответ на главный вопрос статьи (25.09.2026) — рамка «Коротко» НАД палитрой.
    // Нужна поисковикам и ИИ-ответам (Алиса, Нейро): до неё на странице стояла палитра из
    // сотен кодов оттенков, и первый связный текст начинался с ~380-го слова. Палитру вниз
    // не переносим (решение пользователя 05.09), поэтому над ней — только эти 2–3 фразы.
    answer: z.string().optional(),
    brand: z.string(),
    line: z.string(),
    tags: z.array(z.enum(['колористика', 'уход и восстановление', 'база знаний', 'акции', 'цены'])),
    coverImage: z.string(),
    publishDate: z.coerce.date(),
    verifiedDate: z.coerce.date(),
  }),
});

export const collections = { articles };
