## Settings ignore my `.env`

`SECRET_KEY` and `DEBUG` are hard-coded in `conduit/settings.py`, so the values in my local `.env` are
ignored. Debug the config loading: make settings read `DJANGO_SECRET_KEY` and `DJANGO_DEBUG` from the
environment, loading a `.env` file at the repo root when there is one (no new dependencies), and keep the
current development values as fallbacks. Add a `.env.example` that documents the variables.
