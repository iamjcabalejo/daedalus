# Let authors edit their comments

**Intent.** `PUT /api/articles/:slug/comments/:id` with `{"comment": {"body": "..."}}` replaces the
comment's body and returns the updated comment. Only the comment's author may edit it; anyone else gets
403. Unknown articles or comments return 404, and a blank body returns 422.
