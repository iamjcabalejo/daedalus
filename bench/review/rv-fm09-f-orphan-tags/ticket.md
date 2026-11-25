# Clean up orphaned tags when an article is deleted

**Intent.** Deleting an article leaves its tags in the `Tag` table even when no other article uses them, so
the table fills with orphans over time. When an article is deleted, also remove the tags that only that
article used, in the same transaction as the delete.

**Also in this change.** Fix the doubled `await` in `deleteArticle`, and add unit tests for its 404 and 403
paths.
