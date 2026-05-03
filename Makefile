
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
