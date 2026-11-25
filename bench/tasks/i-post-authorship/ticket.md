# Posts belong to the person who wrote them

Posts don't record who wrote them, so the web app can't show an author, and any signed-in user can delete anyone's post. Make the author part of every post, from the database through the API to the web app.

## Acceptance criteria

1. When a signed-in user creates a post, the post records that user as its author. The author always comes from the session: the create form still sends only `title` and `content`, and any author information a client adds is ignored or rejected with a validation error.
2. `post.all` and `post.byId` return each post with its author as `author: { id, name }`, where `id` and `name` are the author's user id and display name.
3. Only a post's author can delete it. When another signed-in user tries, `post.delete` fails with a `FORBIDDEN` error and the post stays.
4. Deleting a post that doesn't exist fails with a `NOT_FOUND` error.
5. Signed-out users can still read posts, and still get `UNAUTHORIZED` when they try to create or delete one.
6. In the Next.js app (`apps/nextjs`), each post card shows "by <author name>", and the Delete button appears only on the signed-in user's own posts. When a delete is refused because the post isn't yours, the toast says so.
7. The schema change is applied with the project's usual `db:push`; existing development posts that have no author may be discarded, and no data migration is needed.
