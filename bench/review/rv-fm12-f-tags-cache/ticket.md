# Cache the popular tags

**Intent.** `GET /api/tags` runs an aggregate query on every page load. Cache the popular-tags result in
memory for 5 minutes, and replace the `test.todo` in the tag service tests with real tests.
