
dist-clean:
	rm -fr dist

dist-build:
	poetry build

dist-publish:
	poetry publish

docs-html:
	$(MAKE) -C docs html

docs-clean:
	rm -fr docs/_build docs/extensions/protocols docs/extensions/resources

# ---------------------------------------------------------------------------
# Service runtime targets
# ---------------------------------------------------------------------------
#
# ``dev-up`` boots a SQLite-backed local instance with auto-create-schema and
# in-tree dev secrets. It exists to take an operator from a fresh checkout
# to a running webservice in one command. NOT for production.
#
# ``serve-prod`` runs the same one-call bootstrap but assumes the operator
# has already populated PYCHESTRATE_DATABASE_URL / KEK / pepper / etc. via
# the deploy environment (see source/site/automojo/pychestrate/webservice/
# runtime_bootstrap.py for the full env contract). Schema is expected to
# have been created out-of-band (alembic or equivalent).
#
# ``serve-prod-gunicorn`` invokes gunicorn against
# ``build_wsgi_application_for_production`` from app_pychestrate_main —
# the recommended production fronting. Requires gunicorn to be installed
# in the active environment.

dev-up:
	./development/dev-up

serve-prod:
	./development/run-website.sh

serve-prod-gunicorn:
	gunicorn 'app_pychestrate_main:build_wsgi_application_for_production()' \
		--chdir source/site \
		--bind $${PYCHESTRATE_BIND_HOST:-0.0.0.0}:$${PYCHESTRATE_BIND_PORT:-8888} \
		--workers $${PYCHESTRATE_WORKERS:-4} \
		--threads $${PYCHESTRATE_THREADS:-2}

# ``serve-staging-gunicorn`` is the alpha deploy target -- runs
# gunicorn against ``build_wsgi_application_for_production()`` with
# auto-generated dev-tier secrets and
# ``PYCHESTRATE_RUNTIME_ENVIRONMENT=staging``.  Bound to 127.0.0.1
# by default for nginx fronting.  This is what the systemd unit
# installed by ``deployment/deploy-alpha-to-host.sh`` invokes.
serve-staging-gunicorn:
	./development/run-staging-gunicorn

# ---------------------------------------------------------------------------
# Database schema management (alembic)
# ---------------------------------------------------------------------------
#
# All targets read PYCHESTRATE_DATABASE_URL (the same env var the runtime
# bootstrap consumes). Production is expected to use these targets
# exclusively; ``dev-up`` short-circuits with auto_create_schema=true for
# fast local rebuilds (use ``db-upgrade`` against the same SQLite file
# when you want to test the migration path itself).
#
# The MESSAGE variable is required for revision-autogen and is passed
# verbatim as the migration's slug. Always review the generated script
# before committing -- autogenerate catches most-but-not-all schema
# changes.

db-upgrade:
	@if [ -z "$$PYCHESTRATE_DATABASE_URL" ]; then \
		echo "PYCHESTRATE_DATABASE_URL is required" >&2; exit 1; \
	fi
	.venv/bin/alembic -c alembic.ini upgrade head

db-downgrade:
	@if [ -z "$$PYCHESTRATE_DATABASE_URL" ]; then \
		echo "PYCHESTRATE_DATABASE_URL is required" >&2; exit 1; \
	fi
	.venv/bin/alembic -c alembic.ini downgrade -1

db-current:
	@if [ -z "$$PYCHESTRATE_DATABASE_URL" ]; then \
		echo "PYCHESTRATE_DATABASE_URL is required" >&2; exit 1; \
	fi
	.venv/bin/alembic -c alembic.ini current

db-history:
	.venv/bin/alembic -c alembic.ini history --verbose

db-revision-autogen:
	@if [ -z "$$PYCHESTRATE_DATABASE_URL" ]; then \
		echo "PYCHESTRATE_DATABASE_URL is required" >&2; exit 1; \
	fi
	@if [ -z "$$MESSAGE" ]; then \
		echo "Usage: make db-revision-autogen MESSAGE='describe change'" >&2; exit 1; \
	fi
	.venv/bin/alembic -c alembic.ini revision --autogenerate -m "$$MESSAGE"
