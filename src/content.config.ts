import { defineCollection } from 'astro:content';
import { glob } from 'astro/loaders';
import { z } from 'astro/zod';

const articles = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/articles' }),
  schema: z.object({
    title: z.string(),
    description: z.string(),
    brand: z.string(),
    line: z.string(),
    tags: z.array(z.enum(['окрашивание', 'уход', 'акции', 'цены'])),
    coverImage: z.string(),
    paletteImage: z.string().optional(),
    publishDate: z.coerce.date(),
    verifiedDate: z.coerce.date(),
    accent: z.enum(['blue', 'red']).default('blue'),
  }),
});

export const collections = { articles };
