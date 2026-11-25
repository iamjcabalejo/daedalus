# Comments: 404 for a missing article, 422 for a blank body

**Bug.** `POST /api/articles/:slug/comments` on a slug that doesn't exist returns a 500, and a body made only of
whitespace (spaces, line breaks) is saved as an empty-looking comment. An empty string is already rejected.

**Intent.** Return `404 {"errors": {"article": ["not found"]}}` for a missing article and
`422 {"errors": {"body": ["can't be blank"]}}` for a body that is empty or only whitespace, and add regression
tests that prove both.
