"""The unsafe-command vocabulary (moved verbatim from detect-stack.py; P2 extends it, roadmap §6.1).

A command whose text matches UNSAFE_RE, or whose body (script body, recipe) matches UNSAFE_BODY_RE, is
marked `unsafe` and never runs without asking. detect-stack.py's rules_digest hashes this file, so changing
the vocabulary marks every profile stale.
"""
from __future__ import annotations

import re

UNSAFE_RE = re.compile(r"\b(deploy|migrate|migration|prod|production|publish|release|destroy|drop)\b", re.I)
# Applied to what a command runs (script bodies, recipes). Omits prod/production on purpose: builds often say
# `--mode production` or `NODE_ENV=production` without touching anything live.
UNSAFE_BODY_RE = re.compile(
    r"\b(deploy|migrate|migrations?:\w+|publish|release|destroy|drop\s+(?:table|database|schema)|dropdb|db\s+push|"
    r"schema:(?:drop|sync)|db:(?:drop|reset|setup|migrate|seed|push)|drizzle-kit\s+(?:push|migrate)|"
    r"alembic\s+upgrade|terraform\s+apply|cdk\s+deploy|sls\s+deploy|serverless\s+deploy|kubectl\s+apply|"
    r"helm\s+(?:install|upgrade)|aws\s+s3\s+(?:sync|cp)|twine\s+upload|npm\s+publish|dbt\s+(?:build|run|seed|snapshot))\b",
    re.I)
