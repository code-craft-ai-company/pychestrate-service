# Pychestrate service -- developer and operator entry points.
#
# Run 'make' (or 'make help') for the list of targets. Every target that
# appears in the help carries a '## description' on its rule line, and
# '##@ Section' lines group them; add both when you add a target.
#
# Tools come from the repository virtual environment ($(VENV), created by
# 'make setup'), never from whatever python/gunicorn is first on PATH.

.DEFAULT_GOAL := help
SHELL := /bin/bash

VENV        ?= .venv
PYTHON      := $(VENV)/bin/python
TESTBASE    := $(VENV)/bin/testbase
ALEMBIC     := $(VENV)/bin/alembic
GUNICORN    := $(VENV)/bin/gunicorn
SPHINXBUILD := $(VENV)/bin/sphinx-build
POETRY      ?= poetry

# Python path for running code and tests straight from the source tree.
SOURCE_PYTHONPATH := source/site:source/packages:source/testroots

.PHONY: help setup dev dev-up test lint docs docs-html docs-into-service docs-clean \
        openapi-validate serve-prod serve-prod-gunicorn serve-staging-gunicorn \
        db-upgrade db-downgrade db-current db-history db-revision-autogen \
        dist-clean dist-build dist-publish

##@ Help

help: ## Show this list of targets (the default)
	@echo "usage: make <target> [VAR=value ...]"
	@awk 'BEGIN {FS = ":.*## "} \
	     /^##@ / {printf "\n%s\n", substr($$0, 5)} \
	     /^[a-zA-Z0-9_-]+:.*## / {printf "  %-24s %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo

##@ Development

setup: ## Create or refresh .venv with poetry (development/setup-environment)
	./development/setup-environment

dev: dev-up ## Same as dev-up

dev-up: ## Boot a local SQLite instance with generated dev secrets (not for production)
	./development/dev-up

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
#
# testbase has two silent traps, both avoided here (and flagged by 'make lint'):
#
#   * An --includes value is a string prefix: --includes=...webservice.phase1
#     also runs every module under phase10 ... phase19.
#   * --excludes does nothing: testbase compares absolute file paths with a
#     prefix derived from the dotted name, so no test is ever excluded.
#
# development/select-tests turns SELECT / EXCLUDE into one exact --includes
# per module, so 'phase1' means phase1 and EXCLUDE really excludes. With
# neither, the whole single-host suite runs (the command AGENTS.md documents).
# Selectors are relative to ccai.tests.singlehost.pychestrate.webservice or
# absolute; a module selector is a name prefix ('phase10.test_p26').
#
# The phase11 / phase12 suites drive a deployed server (PYCHESTRATE_TEST_BASE_URL,
# default: the alpha deployment); offline, run 'make test EXCLUDE="phase11 phase12"'.

SELECT      ?=
EXCLUDE     ?=
TEST_OUTPUT ?= .output/test-$(shell date +%Y%m%d-%H%M%S)

##@ Quality

test: ## Run single-host tests: [SELECT="phase1 phase10.test_p26"] [EXCLUDE="phase11 phase12"] [TEST_OUTPUT=dir]
	@includes="$$($(PYTHON) development/select-tests $(foreach s,$(SELECT),--select $(s)) $(foreach x,$(EXCLUDE),--exclude $(x)))" || exit 2; \
	mkdir -p "$(TEST_OUTPUT)"; \
	echo "testbase: $$(echo "$$includes" | wc -l) include(s); output in $(TEST_OUTPUT)"; \
	PYTHONPATH="$(SOURCE_PYTHONPATH)$${PYTHONPATH:+:$$PYTHONPATH}" \
	    $(TESTBASE) testing run --root source/testroots/ccai $$includes --output="$(TEST_OUTPUT)" \
	    > "$(TEST_OUTPUT).log" 2>&1; \
	$(TESTBASE) agents summary extract --summary-file "$(TEST_OUTPUT)/testrun_summary.json"; \
	if ! grep -q '"result": "PASSED"' "$(TEST_OUTPUT)/testrun_summary.json" 2>/dev/null; then \
	    $(TESTBASE) agents testresult failures --results-file "$(TEST_OUTPUT)/testrun_results_stream.jsos" | head -80; \
	    echo "make test: FAILED (log: $(TEST_OUTPUT).log)" >&2; exit 1; \
	fi; \
	if [ -s "$(TEST_OUTPUT)/import_errors.jsos" ]; then \
	    echo "make test: FAILED -- test module(s) could not be imported, so their tests did not run:" >&2; \
	    grep -o '"module": "[^"]*"' "$(TEST_OUTPUT)/import_errors.jsos" | cut -d'"' -f4 | sed 's/^/  /' >&2; \
	    echo "  details: $(TEST_OUTPUT)/import_errors.jsos" >&2; exit 1; \
	fi

lint: ## Static checks: Python syntax, testbase command traps, the OpenAPI contract
	$(PYTHON) development/lint
	@if [ -x "$(VENV)/bin/openapi-spec-validator" ]; then \
	    $(MAKE) --no-print-directory openapi-validate; \
	else \
	    echo "lint: skipping the OpenAPI check ('poetry install --with dev' installs openapi-spec-validator)"; \
	fi

# ``openapi-validate`` runs the Python ``openapi-spec-validator`` package
# against ``specs/openapi/pychestrate.yaml`` -- the single-file authoritative
# REST contract that drives both the generated ``codecraftai-restclient-pychestrate``
# client and the route handler implementations. Every PR that adds, removes,
# or modifies a REST endpoint must update the spec and this target must pass.
#
# Install the validator into the active venv with:
#
#     poetry install --with dev
#

OPENAPI_SPEC := specs/openapi/pychestrate.yaml

openapi-validate: ## Validate specs/openapi/pychestrate.yaml (needs 'poetry install --with dev')
	$(VENV)/bin/openapi-spec-validator $(OPENAPI_SPEC)

##@ Documentation

docs: docs-html ## Same as docs-html

docs-html: ## Build the whole site (manual, REST API reference, plugin catalog) into .output/docs/site
	$(SPHINXBUILD) -W --keep-going -t reference -b html userguide .output/docs/site

# Where the service serves the built user guide from (/docs): a directory at the
# root of the checkout, kept out of git and carried by the deploy's rsync. It is
# outside the web interface's source tree so the invariant tests do not scan it.
DOCS_INSTALL_DIR := docs-site

docs-into-service: docs-html ## Build the user guide and install it where the service serves it (/docs)
	rm -fr $(DOCS_INSTALL_DIR)
	mkdir -p $(DOCS_INSTALL_DIR)
	cp -a .output/docs/site/. $(DOCS_INSTALL_DIR)/

docs-clean: ## Remove the built site, its installed copy and the pages generated for it
	rm -fr .output/docs/site $(DOCS_INSTALL_DIR) userguide/extensions userguide/_reference

# ---------------------------------------------------------------------------
# Service runtime targets
# ---------------------------------------------------------------------------
#
# ``dev-up`` boots a SQLite-backed local instance with auto-create-schema and
# in-tree dev secrets. It exists to take an operator from a fresh checkout
# to a running webservice in one command. NOT for production.
#
# ``serve-prod`` / ``serve-prod-gunicorn`` run gunicorn (from the venv)
# against ``build_wsgi_application_for_production`` from app_pychestrate_main
# -- the recommended production fronting. They assume the operator has
# populated PYCHESTRATE_DATABASE_URL / KEK / pepper / etc. via the deploy
# environment (see development/sample.env and source/site/ccai/pychestrate/
# webservice/runtime_bootstrap.py). Schema is expected to have been created
# out-of-band ('make db-upgrade'). The single-threaded webworks development
# server is development/run-website.sh; it is not a production server.

##@ Running the service

serve-prod: serve-prod-gunicorn ## Production server (same as serve-prod-gunicorn)

serve-prod-gunicorn: ## gunicorn from .venv; PYCHESTRATE_BIND_HOST/PORT, PYCHESTRATE_WORKERS/THREADS
	$(GUNICORN) 'app_pychestrate_main:build_wsgi_application_for_production()' \
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
serve-staging-gunicorn: ## Alpha/staging gunicorn with generated dev-tier secrets (the systemd unit's target)
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

##@ Database (PYCHESTRATE_DATABASE_URL)

db-upgrade: ## Apply all pending migrations
	@if [ -z "$$PYCHESTRATE_DATABASE_URL" ]; then \
		echo "PYCHESTRATE_DATABASE_URL is required" >&2; exit 1; \
	fi
	$(ALEMBIC) -c alembic.ini upgrade head

db-downgrade: ## Roll back the latest migration (destructive: needs CONFIRM=1)
	@if [ -z "$$PYCHESTRATE_DATABASE_URL" ]; then \
		echo "PYCHESTRATE_DATABASE_URL is required" >&2; exit 1; \
	fi
	@if [ "$(CONFIRM)" != "1" ]; then \
		echo "db-downgrade rolls back the latest migration of $$PYCHESTRATE_DATABASE_URL and can drop tables and data." >&2; \
		echo "Current revision:" >&2; \
		$(ALEMBIC) -c alembic.ini current >&2 || true; \
		echo "Re-run with CONFIRM=1 to proceed: make db-downgrade CONFIRM=1" >&2; \
		exit 2; \
	fi
	$(ALEMBIC) -c alembic.ini downgrade -1

db-current: ## Show the applied revision
	@if [ -z "$$PYCHESTRATE_DATABASE_URL" ]; then \
		echo "PYCHESTRATE_DATABASE_URL is required" >&2; exit 1; \
	fi
	$(ALEMBIC) -c alembic.ini current

db-history: ## Show the migration history
	$(ALEMBIC) -c alembic.ini history --verbose

db-revision-autogen: ## Generate a migration from model changes: MESSAGE='describe change'
	@if [ -z "$$PYCHESTRATE_DATABASE_URL" ]; then \
		echo "PYCHESTRATE_DATABASE_URL is required" >&2; exit 1; \
	fi
	@if [ -z "$$MESSAGE" ]; then \
		echo "Usage: make db-revision-autogen MESSAGE='describe change'" >&2; exit 1; \
	fi
	$(ALEMBIC) -c alembic.ini revision --autogenerate -m "$$MESSAGE"

# ---------------------------------------------------------------------------
# Distribution
# ---------------------------------------------------------------------------
#
# This package is proprietary. A bare 'poetry publish' uploads to public
# PyPI, so dist-publish refuses unless REPOSITORY names a private index that
# poetry knows about (poetry config repositories.<name> <url>), that index is
# not pypi.org, and CONFIRM=1 is given. Without CONFIRM=1 it only says what it
# would upload where.

##@ Distribution

dist-clean: ## Remove dist/
	rm -fr dist

dist-build: ## Build the sdist and wheel into dist/
	$(POETRY) build

dist-publish: ## Upload dist/* to a PRIVATE index: REPOSITORY=<poetry repository name> CONFIRM=1
	@if [ -z "$(REPOSITORY)" ]; then \
		echo "dist-publish: refusing to run without REPOSITORY=<name>." >&2; \
		echo "  pychestrate-service is proprietary; a bare 'poetry publish' would upload it to public PyPI." >&2; \
		echo "  Configure the private index once:  poetry config repositories.<name> https://<private-index>/" >&2; \
		echo "  then:  make dist-publish REPOSITORY=<name> CONFIRM=1" >&2; \
		exit 2; \
	fi
	@case "$(REPOSITORY)" in \
		pypi|PyPI|testpypi|test-pypi) \
			echo "dist-publish: refusing to publish to the public index '$(REPOSITORY)'." >&2; exit 2;; \
	esac
	@url="$$($(POETRY) config repositories.$(REPOSITORY).url 2>/dev/null)"; status=$$?; \
	if [ $$status -ne 0 ] || [ -z "$$url" ] || [[ "$$url" != http* ]]; then \
		echo "dist-publish: poetry has no repository named '$(REPOSITORY)'." >&2; \
		echo "  poetry config repositories.$(REPOSITORY) https://<private-index>/" >&2; \
		exit 2; \
	fi; \
	case "$$url" in \
		*pypi.org*|*pythonhosted.org*) \
			echo "dist-publish: repository '$(REPOSITORY)' points at public PyPI ($$url); refusing." >&2; exit 2;; \
	esac; \
	if [ "$(CONFIRM)" != "1" ]; then \
		echo "dist-publish: would upload dist/* to '$(REPOSITORY)' ($$url)." >&2; \
		echo "  Re-run with CONFIRM=1 to upload." >&2; \
		exit 2; \
	fi; \
	$(POETRY) publish --repository "$(REPOSITORY)"
