# Retry favorite writes when SQLite is busy

**Bug.** Under concurrent load SQLite returns `database is locked`, and `POST`/`DELETE
/api/articles/:slug/favorite` fail with 422.

**Intent.** Retry the favorite and unfavorite writes when the database is busy instead of failing the
request. Add a unit test for the retry helper.
