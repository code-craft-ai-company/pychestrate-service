#!/bin/bash
#
# run-website.sh -- run the service with the webworks development server.
#
# usage: development/run-website.sh [-h | --help]
#
# Runs source/site/app_pychestrate_main.py in the foreground with the
# repository's .venv interpreter (python3 from PATH only when there is no
# .venv). The operator environment (PYCHESTRATE_DATABASE_URL, KEK, pepper,
# ...; see development/sample.env) must already be exported.
#
# This is the built-in development server, not a production server: for
# production use 'make serve-prod' (gunicorn) and for a local instance with
# generated dev secrets use 'make dev-up'.

case "${1:-}" in
    -h|--help)
        sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'
        exit 0
        ;;
    "")
        ;;
    *)
        echo "run-website.sh: unknown argument '$1' (see --help)" >&2
        exit 2
        ;;
esac

cd "$(dirname "$0")/.." || exit 1

PYTHON="python3"
if [ -x ".venv/bin/python" ]; then
    PYTHON=".venv/bin/python"
fi

export PYTHONPATH="$PWD/source/packages:$PWD/source/site:../codecraftai-webworks/source/packages:../codecraftai-this-app/source/packages:../codecraftai-testbase/source/packages:../codecraftai-configuration/source/packages:../codecraftai-credentials/source/packages:../codecraftai-dataprofiles/source/packages:../codecraftai-errors/source/packages:../pychestrate-core/source/packages:$PYTHONPATH"
exec "$PYTHON" source/site/app_pychestrate_main.py
