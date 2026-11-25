# Show an estimated reading time on articles

**Intent.** Article responses include `readingTime`: the estimated minutes to read the body, at about 200
words per minute, and never less than 1. It's stored on the article, computed when the article is created
and recomputed when its body changes.

**Scope.** Prisma schema and migration, the article service and mapper, and unit tests for the estimate.
