# Keep the home page up when the database is briefly unavailable

**Bug.** When the database is briefly unavailable, the home page crashes into the error boundary.

**Intent.** Make the post list degrade gracefully instead of breaking the whole page. Also name the
recent-posts limit.
