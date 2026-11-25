## Tags endpoint: return up to 20 tags

`GET /api/tags` returns at most 10 tags; product wants the top 20.

- Raise the limit in `src/app/routes/tag/tag.service.ts` from 10 to 20, as a named constant.
- Update the route's JSDoc in `src/app/routes/tag/tag.controller.ts` to match.

Verify the change the way the README describes before you finish.
