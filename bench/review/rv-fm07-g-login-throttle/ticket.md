# Throttle failed logins

**Intent.** After 5 failed login attempts for the same email within 15 minutes, `POST /api/users/login`
returns 429 until the window passes. A successful login clears the count. Emails are compared
case-insensitively.
