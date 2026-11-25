# Moderate new posts before saving them

**Intent.** Every new post is checked by the moderation service before it's saved. The service takes
`POST {"text": "..."}` and answers `{"flagged": boolean}`. Flagged posts are rejected with BAD_REQUEST
"This post was flagged by moderation". When the service is rate-limiting, tell the user to try again. The
service URL comes from `MODERATION_API_URL`, validated by both web apps' env schemas and declared to turbo.
