# Stop duplicate posts on retry

**Bug.** Users who retry after a timeout, or click Create twice, end up with duplicate posts.

**Intent.** Make post creation idempotent. The client sends an idempotency key with each new post, and the
server ignores a create whose key it has already stored. Also disable the Create button while a create is in
flight.
