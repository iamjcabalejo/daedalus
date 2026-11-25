# Refactor: one article lookup in the favorite view

**Intent.** `ArticlesFavoriteAPIView.post` and `.delete` repeat the same "get the article or 404" block.
Extract it into one method with the same query and the same error message. No behavior change.
