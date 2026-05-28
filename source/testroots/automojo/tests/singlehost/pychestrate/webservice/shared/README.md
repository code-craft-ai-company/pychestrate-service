# shared / webworks_test_harness

Shared fakes for the pychestrate webworks handler-level tests.

## Why this exists

Every test file under `phase10/` and `phase12/` that exercises a
webworks route registrar used to declare its own `_FakeApp`,
`_FakeRequest`, `_FakeSecurityManager`, `_StubJinjaEnvironment`,
and friends. That added ~50-500 lines of boilerplate per file
and made new feature PRs (e.g. release templates) feel
expensive: copy the harness or ship unit-only tests.

The harness here consolidates the common pieces so handler-level
coverage costs ~10 lines instead of ~500.

## When to use it

Reach for the shared harness when your test needs to:

- assert a route registrar attached the documented
  `(path, methods)` matrix --
  use `make_fake_app()` and `app.route_pairs()`.
- invoke a webworks handler directly with a request that has
  `path` / `path_params` / `query_params` / `cookies` / `body` /
  `json()` / `form()` / `headers` / `db_session` /
  `security_manager` attached --
  use `make_fake_request(...)`.
- drive an auth-guarded handler with a session shaped the way
  `webinterface.foundation.auth_guard` expects --
  use `make_fake_session(...)`.
- assert which template name + context a handler rendered
  without actually rendering HTML --
  use `with capture_renders(templating_module=...) as r:`.

## When NOT to use it

Stay inline when:

- the handler under test touches a request attribute the harness
  does not yet model. Either extend the harness in this PR (with
  the same conventions) or build a one-off fake locally.
- you are testing the harness primitives themselves (cookie
  signing, csrf rotation, flash queue semantics). Those live one
  layer below the harness and should be tested against their
  real modules.

## Dropping in custom mocks

Common extensions:

- **Different security-manager behaviour:** pass
  `permission_predicate=lambda uid, perm: perm != "blocked.perm"`
  to `make_fake_security_manager(...)`, or set
  `mgr.validate_token_response = None` to simulate the
  invalid-session path.
- **A db_session with non-trivial behaviour:** build the
  SQLAlchemy-style object you need locally and pass it via
  `make_fake_request(db_session=my_session)`. The harness does
  not try to mock SQLAlchemy itself.
- **Reading captured render context:** use
  `recorder.last_context()` for single-render handlers,
  `recorder.calls[i].context` for multi-render flows.

## Stability promise

The harness's exported symbols are stable within the
`source/testroots` tree. Internal helpers prefixed with `_`
(e.g. `_StubTemplate`, `_encode_form`) may move without notice
-- import only the names listed in the docstring of
`webworks_test_harness.py`.
