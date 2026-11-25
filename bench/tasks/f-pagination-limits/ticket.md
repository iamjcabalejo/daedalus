# Keep article lists to a sensible page size

Clients can ask `GET /api/articles` and `GET /api/articles/feed` for any number of articles at once, and odd values for `limit` or `offset` (a negative offset, a fractional limit) reach the database as they are. A single request for `limit=100000` can load the whole table. Put firm, predictable bounds on paging.

## Acceptance criteria

1. `limit` is the page size. A whole number from 1 to 100 is used as given. A whole number above 100 is treated as 100.
2. When `limit` is missing, isn't a whole number (for example `abc` or `2.5`), or is below 1, the page size is the default of 10.
3. `offset` is the number of articles skipped. A whole number of 0 or more is used as given. When it's missing, isn't a whole number, or is negative, it's 0.
4. The same rules apply to `GET /api/articles` and to `GET /api/articles/feed`.
5. Nothing else changes: the responses keep their current shape (`articles` and `articlesCount`), out-of-range values are corrected rather than rejected, and the existing `tag`, `author` and `favorited` filters work as before.
