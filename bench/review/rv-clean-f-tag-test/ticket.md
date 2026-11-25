# Test the tag service

**Intent.** `tag.service.test.ts` only has a `test.todo` (its comment says mocking `groupBy` didn't work; the
service uses `findMany`). Add real tests: tag names are mapped to strings, and the signed-in user's own tags
are included in the query.
