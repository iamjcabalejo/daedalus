# Refactor: one Prisma include for article responses

**Intent.** `article.service.ts` repeats the same `include` block (tags, author with followers, favorites and
the favorites count) in seven queries. Define it once with `Prisma.validator` so the queries can't drift.
No behavior change.
