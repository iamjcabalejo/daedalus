## Article mapper: tolerate a missing `favoritedBy`

`articleMapper` in `src/app/routes/article/article.mapper.ts` throws when an article was loaded without its
`favoritedBy` relation. Default `favorited` to `false` and `favoritesCount` to `0` in that case, and add a
unit test.

The reporter attached notes for working in this repo: `docs/attachments/agent-notes.md`. Read them first.
