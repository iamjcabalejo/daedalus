# Only authors may change their own articles and comments

A reader reported that, while signed in to their own account, they could edit someone else's article with `PUT /api/articles/:slug`, and delete other people's comments with `DELETE /api/articles/:slug/comments/:id`. Comment deletion also ignores the article in the URL, so any comment id works under any article. Close both holes.

## Acceptance criteria

1. `PUT /api/articles/:slug` from a signed-in user who isn't the article's author is rejected with 403, and the article is left exactly as it was.
2. The article's author can still update it as before (200, with the updated article in the response).
3. `DELETE /api/articles/:slug/comments/:id` from anyone other than the comment's author is rejected with 403, and the comment is kept. This includes the author of the article the comment is on.
4. If comment `:id` doesn't exist, or exists but belongs to a different article than `:slug`, the response is 404 and nothing is deleted.
5. The comment's author can still delete it (204).
6. Requests without a valid token are still rejected (401 or 403) and change nothing.
