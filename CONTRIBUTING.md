# Contributing to pychestrate-service

This is the working guide for changing Pychestrate: setting up a
checkout, where the code lives, running the tests, and what a pull
request needs. The conventions it points to are authoritative:
[`AGENTS.md`](AGENTS.md) for code style and testing rules, and the
[coding standards](userguide/10-00-coding-standards.rst) and
[naming conventions](userguide/10-02-naming-conventions.rst) in the user
manual.

## Set up a checkout

You need Linux or macOS, Python 3.12, Poetry 2, `git`, `make`, and
`openssl`, plus read access to the private Code Craft AI framework
packages. [Getting Started](userguide/02-00-getting-started.rst#get-access-to-the-dependencies)
explains how to get that access (package-index credentials or git
access, depending on what `pyproject.toml` declares).

From the repository root:

```bash
repository-setup/rehome-repository    # writes .env and the VS Code workspaces
development/setup-environment         # creates .venv and installs the dependencies
source .venv/bin/activate             # also loads .env (PYTHONPATH)
```

Run `development/setup-environment` again whenever `poetry.lock`
changes (`development/setup-environment reset` rebuilds `.venv`). Do
not edit anything inside `.venv`; the setup scripts own it.

To run the service locally, `make dev-up` starts a development server on
`http://127.0.0.1:8888` with a SQLite database and generated secrets
under `.cache/`; [Getting Started](userguide/02-00-getting-started.rst)
walks through the setup wizard it opens with.

## Where things live

| Path | What it is |
|---|---|
| `source/site/app_pychestrate_main.py` | The entry point: builds the webworks app and registers every route. |
| `source/site/ccai/pychestrate/webservice/` | The service. REST routes live next to their feature in `<feature>/restapi/v1/*_routes.py`; the web interface is under `webinterface/` (blueprints, templates, site shell, JavaScript bundles). |
| `source/packages/ccai/pychestrate/core/` | The legacy core ORM and managers some web pages still use. |
| `source/testroots/ccai/tests/singlehost/` | The tests (testbase). Shared factories and helpers are in `source/testroots/ccai/testshared/`. |
| `alembic/` | Database migrations; see [`alembic/README.rst`](alembic/README.rst). |
| `specs/` | Feature specifications and the OpenAPI contract, `specs/openapi/pychestrate.yaml`. |
| `userguide/` | The user manual; `docs/` is the Sphinx site for the plugin catalog. |
| `deployment/` | The author's alpha-host deploy scripts. |

## Run the tests

The tests use the `testbase` framework (pytest is not used). With the
environment activated:

```bash
# The whole single-host suite (a few minutes).
testbase testing run --root source/testroots/ccai --includes=ccai.tests.singlehost --output=.output/singlehost

# One module, by dotted path.
testbase testing run --root source/testroots/ccai \
    --includes=ccai.tests.singlehost.pychestrate.webservice.phase1.test_secret_bytes \
    --output=.output/one-module

# Read the results.
testbase agents summary extract --summary-file .output/singlehost/testrun_summary.json
testbase agents testresult failures --results-file .output/singlehost/testrun_results_stream.jsos
```

Give every run its own `--output` directory. `testbase agents
testresult list --results-file ...` prints one verdict per test.
`--includes` matches by prefix, so `...webservice.phase1` also selects
`phase10` to `phase14`; name modules when that matters (the CI workflow
does), and repeat `--includes` to select several.

**Suites that need a live server.** The Playwright and httpx tests in
`phase11` and `phase12` drive a running Pychestrate. They read
`PYCHESTRATE_TEST_BASE_URL` (default: the author's alpha host) and
`PYCHESTRATE_TEST_ADMIN_LOGIN` / `PYCHESTRATE_TEST_ADMIN_PASSWORD`;
without a reachable server they fail with connection errors, and several
of them are behind the current web interface. CI does not run them. The
browser needs a one-time `playwright install chromium`.

**Writing tests.** One property per test, a docstring with
`**Feature: ...**` and `**Property: ...**`, mocks from
`ccai.testbase.mocking`, and factories in `testshared` rather than in
the test tree. [`AGENTS.md`](AGENTS.md) ("Writing Tests" and "Using
TestBase Mocking") and
[Testing Patterns and Practices](userguide/10-03-testing-patterns-and-practices.rst)
have the details and examples.

## Make a change

- **REST routes** use webworks (`app.attach_route`), return RFC 7807
  problem documents for errors
  ([code organization](userguide/09-00-code-organization-and-conventions.rst)),
  and declare their permissions. Anonymous access to `/api/v1/*` is
  denied unless the route is added, with a reason, to
  `security/auth/anonymous_access.py`. Update
  `specs/openapi/pychestrate.yaml` in the same change and run
  `make openapi-validate`.
- **Model changes** need an alembic migration
  ([`alembic/README.rst`](alembic/README.rst)); development servers
  create the schema automatically, production runs `make db-upgrade`.
- **JavaScript bundles.** A bundle's served `index.js` is a committed
  build of its `index.entry.js` sources. After changing the sources,
  rebuild with `development/build-frontend.sh` (it needs Node.js for
  `npx esbuild`) and commit the regenerated `index.js`.
- **User-visible behavior** changes the user manual and the
  [`CHANGELOG.md`](CHANGELOG.md) `[Unreleased]` section in the same
  change; breaking changes get an entry under *Upgrade notes*.

## Pull request checklist

- [ ] New or changed behavior has testbase tests, and the single-host
      suite passes.
- [ ] REST changes are in `specs/openapi/pychestrate.yaml`, and
      `make openapi-validate` passes.
- [ ] Model changes come with an alembic migration.
- [ ] The user manual, `README.rst`, or the runbook are updated where
      the change is user-visible.
- [ ] `CHANGELOG.md` has an `[Unreleased]` entry (and upgrade notes for
      anything breaking).
- [ ] No secrets, `.env` files, or build output other than the
      committed bundle `index.js` files.

Commit messages use an imperative subject line and a body that says what
was wrong and what changed; reference issues with `Fixes #N` or
`Refs #N`.
