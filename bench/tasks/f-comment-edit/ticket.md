# Let people edit their own comments

Readers can add and delete comments on an article, but they can't fix a typo without deleting the comment and posting it again, which also loses its place in the thread. Add a way to edit a comment.

## Acceptance criteria

1. `PUT /api/articles/:slug/comments/:id` with a JSON body `{"comment": {"body": "<new text>"}}` changes the text of comment `:id` on the article `:slug`. It requires a signed-in user, like the other comment endpoints; without a valid token the response is 401.
2. Only the comment's author can edit it. Anyone else gets 403, and the comment stays as it was.
3. When the comment doesn't exist, or exists but belongs to a different article than `:slug`, the response is 404 and nothing changes.
4. The new text is trimmed. If it's missing or blank after trimming, the response is 422 with `{"errors": {"body": ["can't be blank"]}}`, and nothing changes.
5. On success the response is 200 with `{"comment": {...}}`, in the same shape that adding a comment returns (`id`, `createdAt`, `updatedAt`, `body`, and `author` with `username`, `bio`, `image`, `following`). `updatedAt` reflects the edit.
