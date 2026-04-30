# Continuing the pychestrate-service Flask → automojo-webworks migration

## Context

I'm in the middle of migrating `pychestrate-service` (a Python web service
at `/Users/myron/repos/pychestrate-service`) from Flask + flask-restx to
`automojo-webworks` (cloned at `/Users/myron/repos/automojo/automojo-webworks`).

## What's already done

**Five upstream PRs against `automojo-webworks` — ALL MERGED** (audit fixes
discovered while integrating webworks):
- PR #4: digest auth `hmac.compare_digest` (timing-attack fix)
- PR #5: bearer auth constructor validation
- PR #6: apikey blank-key normalization
- PR #7: roles/scopes claim-shape validation
- PR #8: digest empty-required-field rejection

**Two upstream PRs against `pychestrate-core` — PR #7 MERGED, PR #8 OPEN**:
- PR #7: widen `sqlalchemy-utils` constraint to `>=0.41.2,<0.43.0` (was `^0.41.2`)
- PR #8: drop empty `automojo/pychestrate/__init__.py` so it's a namespace
  package (single-byte change, file was 0 bytes; without it, downstream
  `automojo.pychestrate.webservice.*` imports fail). Workaround applied
  locally: `rm /Users/myron/repos/pychestrate-service/.venv/lib/python3.12/
  site-packages/automojo/pychestrate/__init__.py`. Once PR #8 merges, the
  workaround becomes durable.

**Working branch in pychestrate-service**:
- `claude/p24a-flask-to-webworks-foundation-m3` (created off
  `claude/p23c-wire-session-and-mfa-instrumentation-m3`)
- One commit so far: `cf82d04` — "chore(deps): refresh poetry.lock after
  webworks audit fixes + namespace fix" — the lockfile delta from
  `poetry update`. No source migration yet.

## Current state of pychestrate-service

`poetry update automojo-webworks pychestrate-core` removed Flask, flask-restx,
flask-authorize, werkzeug, AND the legacy `automojo-webservice-flask` package
from the venv. They're no longer pulled in by any direct dep.

**The breakage**: 58 source files in `source/site/` and 4 test files in
`source/testroots/` import Flask. They all `ImportError` at runtime. Pure
service-layer tests (e.g. `automojo.tests.singlehost.pychestrate.core` and
`automojo.tests.singlehost.pychestrate.webservice.phase11`) still pass —
36/36 and 59/59 respectively — because they don't touch controllers.

The 58+4 files were inventoried previously. Categories:
- ~40 REST controllers using `flask_restx.Namespace, Resource, fields`
- ~6 web blueprints using `flask.Blueprint`
- 47 files using `flask.g`, `flask.request`, `flask.session`
- `auth_controller.py`, `webworks_bridge.py`, phase-1 middleware (mine)
- 4 test files using `Flask` + `flask_restx.Api` + `app.test_client()`

## What the next session should do

**P24a — establish the migration pattern with one worked example.** Don't
attempt all 58 files. The deliverable for the session is:

1. **Read webworks idioms first** — start at:
   - `/Users/myron/repos/automojo/automojo-webworks/source/testsites/blueprintdemo/endpoints/handlers.py`
     (RestBlueprint usage)
   - `/Users/myron/repos/automojo/automojo-webworks/source/packages/automojo/webworks/routing/middleware/cors.py`
     (middleware shape — sync `__call__(self, request, call_next) -> Response`)
   - `/Users/myron/repos/automojo/automojo-webworks/source/packages/automojo/webworks/devexp/testing/testclient.py`
     (test-client equivalent of Flask `app.test_client()`)
   - `/Users/myron/repos/automojo/automojo-webworks/source/packages/automojo/webworks/routing/request.py`
     (Request shape — `request.method`, `request.path`, `request.query_params`,
     `request.headers`, `request.body`, `request.cookies`, `request.path_params`,
     `request.middleware_context`)

2. **Resolve the request-scoped state question** (open at end of last
   session): `MiddlewareContext` is sealed (only `endpoint_descriptor`,
   `scope`, `config`, `logger` properties — no extension point). The Flask
   `g.db_session` pattern needs replacement. Two paths to evaluate:
   - Set arbitrary attrs on `Request` directly (`request.db_session = ...`)
     — works if `Request.__init__` doesn't `__slots__`-lock. I started
     verifying this in the prior session but didn't finish; check `class
     Request` body in `routing/request.py:23-` for `__slots__`.
   - Subclass `MiddlewareContext` with extra fields and have the db-session
     middleware swap in the subclass at `request.middleware_context = ...`.

3. **Migrate `auth_controller.py` as the worked example**:
   - File: `source/site/automojo/pychestrate/webservice/security/auth/restapi/v1/auth_controller.py`
   - 5 endpoints: `GET /providers`, `POST /providers/{kind}/{name}/enable`,
     `POST /providers/{kind}/{name}/disable`, `POST /logout`,
     `POST /mfa/challenge`, `POST /mfa/verify`
   - Mapping:
     - `flask_restx.Namespace + Resource` → `RestBlueprint` subclass with
       `base_path = "/api/v1/auth"`
     - `@auth_ns.route(...)` + `class Foo(Resource)` + `def post(self):` →
       `@RestBlueprint.attach_at(path=..., methods=["POST"])` on a method
     - `flask.g.db_session` → `request.db_session` (or `request.middleware_context.db_session` depending on path 2 above)
     - `flask.request.get_json()` → `await request.json()` or
       `json.loads(request.body)` (sync if handler is sync)
     - `auth_ns.abort(404, "msg")` → `return JSONResponse(content={"error": "msg"}, status_code=404)`
     - `return (body, 200)` → `return JSONResponse(content=body, status_code=200)`
     - `auth_ns.expect(model, validate=True)` → consider Pydantic schemas
       per webworks `Doc()` annotations, or skip for now

4. **Build a webworks `DbSessionMiddleware`** in
   `source/site/automojo/pychestrate/webservice/middleware_webworks.py`:
   ```python
   class DbSessionMiddleware:
       name: str = "db_session"
       def __init__(self, session_factory):
           self._session_factory = session_factory
       def __call__(self, request, call_next):
           db_session = self._session_factory()
           request.db_session = db_session  # OR via middleware_context
           try:
               return call_next(request)
           finally:
               db_session.close()
   ```

5. **Write a webworks-native test** at
   `source/testroots/automojo/tests/singlehost/pychestrate/webservice/phase12/test_p24a_auth_controller_webworks_m3.py`
   using `automojo.webworks.devexp.testing.create_test_client()`. Cover the
   admin enable/disable + picker scenarios from the original
   `test_p21c_feature_flag_gates_and_admin_toggle_m2.py`.

6. **Document the migration pattern** at the top of the new
   `auth_controller.py` so subsequent slices have a worked example.

7. **DO NOT migrate the other 57 files this session.** Defer to follow-up
   slices. Note in the PR description that this is one example; the rest
   tracks as P24b–P24j (per the 8-slice plan from the earlier session).

## Conventions / things that bit me last time

- The shell drops back to a `.claude/worktrees/adoring-sammet-4eb165/` cwd
  after every command. Always `cd /Users/myron/repos/pychestrate-service`
  (or the relevant repo) at the start of each Bash call.
- Test invocation:
  ```
  cd /Users/myron/repos/pychestrate-service && \
    PYTHONPATH=source/site:source/testroots:source/packages \
    .venv/bin/testbase testing run \
      --root source/testroots/automojo \
      --includes "automojo.tests.singlehost.pychestrate.webservice.phase12.test_p24a*" \
      -o .output_p24a
  ```
- Coding standards from `/Users/myron/repos/CLAUDE.md`: explicit `return rtnval`
  on every function; no truthy/falsy checks (`if x is not None: ... if len(x) > 0:`);
  multiline error msgs via `os.linesep.join([...])`; named-parameter passing
  always; no `__init__`-side instance vars introduced elsewhere.
- Commit messages match the pychestrate-service convention:
  `feat(p24a): ...` with a `Co-Authored-By: Claude Opus 4.7 (1M context)
  <noreply@anthropic.com>` trailer.
- Each PR is stacked on the prior — `gh pr create --base
  claude/p23c-wire-session-and-mfa-instrumentation-m3 --head
  claude/p24a-flask-to-webworks-foundation-m3 ...`
- The user prefers the autonomous-loop pattern: when they say "continue",
  pick the next concrete deliverable autonomously and ship it.
- They also follow up specific PRs ("PR 7 has been merged, verify") — be
  ready to verify upstream merge state via `gh pr view N --json state,mergedAt`.

## Open / pending items not in scope for this session

- pychestrate-core PR #8 (namespace package fix) needs to merge upstream;
  watch for the user reporting "merged".
- The 4 single-owner sub-namespaces (`automojo/configuration/`, `extension/`,
  `interfaces/`, `xmodules/`) ship empty `__init__.py` files. Latent risk
  but not blocking — only file PRs if asked.
- 58-file Flask migration continues as P24b onwards. The 8-slice plan from
  earlier:
  P24a — Foundation + auth_controller (this session)
  P24b — Retarget `webworks_bridge.py` from Flask middleware to webworks
  P24c — Migrate first batch of REST controllers
  P24d–P24h — Remaining controller groups (clients, identity, security/RBAC,
  retention, secrets, projects, agents, tagging, audit, pods, variables,
  notifications, project_templates)
  P24i — Migrate `webinterface/blueprints` (server-rendered HTML)
  P24j — Drop residual Flask deps from pyproject.toml + lock

## First action when you read this

Look at `/Users/myron/repos/automojo/automojo-webworks/source/packages/
automojo/webworks/routing/request.py` line ~23 and confirm whether `Request`
uses `__slots__`. That decides whether `request.db_session = ...` direct
attachment works or if we need the MiddlewareContext-subclass approach.
Then start the migration as outlined.
