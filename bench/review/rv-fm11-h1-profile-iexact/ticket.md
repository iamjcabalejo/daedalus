# Make profile URLs case-insensitive

**Bug.** `/api/profiles/Jake` returns 404 for the user `jake`, and links typed by hand often differ in case.

**Intent.** Look profiles up by username ignoring case for `GET /api/profiles/:username` and for follow and
unfollow. Use one helper for the lookup and the 404.
