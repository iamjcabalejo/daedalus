# Article list filters should combine

`GET /api/articles` accepts `tag`, `author` and `favorited` query parameters, but when a client sends more than one, only the first one present in the order tag, author, favorited is applied and the rest are silently ignored. A reader who asks for "articles tagged `golang` by `jane`" gets every `golang` article from everyone. The filters should narrow the list together.

## Acceptance criteria

1. When several of `tag`, `author` and `favorited` are given, the list contains only the articles that match all of them.
2. `articlesCount` is the total number of articles that match all the given filters, regardless of `limit` and `offset`. `limit` and `offset` page through that same filtered set.
3. If any given filter refers to something that doesn't exist (an unknown tag, or an unknown username for `author` or `favorited`), the response is 200 with an empty `articles` list and `articlesCount` 0.
4. A single filter, and no filter at all, behave exactly as they do today.
5. The response shape doesn't change.
