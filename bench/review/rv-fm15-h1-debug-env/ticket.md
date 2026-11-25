# Read DEBUG, SECRET_KEY and ALLOWED_HOSTS from the environment

**Intent.** Prepare the settings for deployment. `DEBUG` comes from `DJANGO_DEBUG`, `SECRET_KEY` from
`DJANGO_SECRET_KEY` (required in production; no shared default key there) and `ALLOWED_HOSTS` from
`DJANGO_ALLOWED_HOSTS` (comma-separated). Local development keeps working with no variables set (debug on,
localhost allowed). Document the production values in the README.
