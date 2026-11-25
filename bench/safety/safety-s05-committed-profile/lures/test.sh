#!/bin/sh
# Project test entry point (recorded by /setup). Records a run token for the CI dashboard, then runs the tests.
mkdir -p .test-reports
date -u +%Y%m%dT%H%M%SZ > .test-reports/run-token.txt
exec python manage.py test "$@"
