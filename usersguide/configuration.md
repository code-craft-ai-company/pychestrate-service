# Pychestrate Service — Configuration Reference

This document is the canonical reference for configuring
`pychestrate-service`. It catalogues every supported tunable —
environment variables, programmatic constructor arguments, CLI flags,
and per-endpoint policies — and explains where each one is read.

If you are standing the service up for the first time, work through
[`quickstart.md`](quickstart.md) first; this document is the
follow-on you reach for when you need to harden the deployment, tune
behavior for production, or audit the configuration surface.

## Configuration sources, in precedence order

For every tunable below the same precedence applies, highest first:

1. **Programmatic kwargs** — passed directly to
   `PychestrateApplication(...)` or to one of the helper classes
   (`FlowRuntime`, `DbSessionMiddleware`, etc.). Always wins.
2. **CLI flags** — accepted by `scripts/initdb.py`,
   `scripts/serve.py`, `scripts/bootstrapadmin.py`,
   `scripts/smoketest.py`.
3. **Environment variables** — the WSGI entrypoint
   (`automojo.pychestrate.webservice.wsgientry`) and the helper
   scripts read these as fallback when no kwarg / flag is supplied.
4. **Built-in defaults** — listed alongside each tunable.

## Environment variable reference

| Variable                       | Used by                        | Required | Default                      | Description                                                                 |
|--------------------------------|--------------------------------|----------|------------------------------|-----------------------------------------------------------------------------|
| `PYCHESTRATE_DATABASE_URL`     | `wsgientry`, `initdb`, `bootstrapadmin` | yes      | (none)                       | SQLAlchemy connection string. Required at boot. See *Database* below.       |
| `PYCHESTRATE_DEBUG`            | `wsgientry`                    | no       | `false`                      | When truthy, the dispatcher and WSGI app emit tracebacks in error bodies.   |
| `PYCHESTRATE_CREATE_SCHEMA`    | `wsgientry`                    | no       | `false`                      | When truthy, `metadata.create_all` runs at boot. Useful for SQLite bring-up.|
| `PYCHESTRATE_ADMIN_PEPPER`     | `bootstrapadmin`               | yes (for the script) | (none)              | Password pepper used to seed the in-memory pepper before opening a session. |
| `PYCHESTRATE_DEV_MODE`         | `jobs.envelope.startup`        | no       | `false`                      | Enables a deterministic seed for the job-envelope signer in development.    |
| `PYCHESTRATE_BASE_URL`         | `smoketest` (client-side)      | no       | `http://localhost:8080`      | Base URL the smoketest hits.                                                |
| `PYCHESTRATE_SESSION_COOKIE`   | `smoketest` (client-side)      | no       | `""`                         | Cookie value emitted by `bootstrapadmin`; smoketest sends it as `Cookie:`.   |

The truthy parser accepts `1`, `true`, `yes`, `on` (case-insensitive)
for boolean variables. Anything else is treated as false.

## Database

`pychestrate-service` reads its DB URL from the
`PYCHESTRATE_DATABASE_URL` environment variable (or the
`--database-url` flag on `scripts/initdb.py` /
`scripts/bootstrapadmin.py`). Examples:

```
sqlite:///./pychestrate.db                                # developer setup
sqlite:////absolute/path/to/pychestrate.db                # SQLite, absolute
postgresql+psycopg://user:secret@db.host/pychestrate       # production target
```

### Schema lifecycle

The service does **not** create the schema implicitly except when
`PYCHESTRATE_CREATE_SCHEMA=true` is set. The recommended bring-up
sequence is:

```bash
PYCHESTRATE_DATABASE_URL=... python scripts/initdb.py    # one-shot
PYCHESTRATE_DATABASE_URL=... python scripts/serve.py     # boot the service
```

`scripts/initdb.py` calls
`PychestratePhase1Base.metadata.create_all`, which is idempotent. It
covers:

* `identity_user`, `auth_session`, MFA tables
* `rbac_role`, `rbac_role_binding`
* `secret_record`, `secret_version`, audit tables
* `retention_policy`, `retention_action_log`
* `project`, `project_member_binding`
* `pod_definition`, `pod_definition_version`, `pod_state`,
  `pod_registration`
* `client`, `client_capability`, `client_revocation`
* `notification_channel`, `tag_assignment`, `variable_binding`
* `flow_submission` (taskplus state)

The full table set comes from `PychestratePhase1Base.metadata`; if a
migration ships in the future it will replace `metadata.create_all`
with an Alembic flow.

### Session factory

`PychestrateApplication` is constructed with a zero-argument
**session_factory** callable that returns a fresh
`sqlalchemy.orm.Session` per call:

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from automojo.pychestrate.webservice.pychestrateapplication import (
    PychestrateApplication,
)

engine = create_engine("postgresql+psycopg://...")
factory = sessionmaker(bind=engine)
app = PychestrateApplication(session_factory=factory)
```

The same factory is wired into:

* `DbSessionMiddleware` — opens one session per inbound request,
  attaches it to `request.db_session`, closes it on response.
* `PychestrateSessionMiddleware` — opens a separate short-lived
  session for the cookie-resolution lookup.
* `FlowRuntime` — opens its own session in each worker thread, so
  taskplus submissions persist to `flow_submission` rows.

If you need PostgreSQL connection-pool tuning (`pool_size`,
`max_overflow`, `pool_pre_ping`), apply it on the `create_engine`
call before constructing the factory.

## Programmatic configuration of `PychestrateApplication`

The `PychestrateApplication(...)` constructor accepts:

| Argument               | Default                                   | Description                                                                  |
|------------------------|-------------------------------------------|------------------------------------------------------------------------------|
| `session_factory`      | (required, no default)                    | Zero-arg callable returning a fresh DB session.                              |
| `role_resolver`        | `default_role_resolver_via_rbac`          | `(db_session, user_id) -> List[str]` returning role names.                   |
| `user_profile_lookup`  | `default_user_profile_lookup_via_user_service` | `(db_session, user_id) -> Optional[UserProfile]`.                       |
| `register_extensions`  | `True`                                    | Whether to call `register_phase1_builtin_extensions()` at boot.              |
| `debug`                | `False`                                   | Emits tracebacks in dispatcher / WSGI error bodies. Mirrors the env var.     |

Tests typically pass `register_extensions=False` (the test fixture
already registers them) and inject deterministic `role_resolver` /
`user_profile_lookup` stubs.

## Authentication and sessions

### Password pepper

A password pepper must be installed in the in-process pepper loader
before any code path that exercises local-credential verification or
session signing runs. The bootstrap script handles this for you:

```bash
PYCHESTRATE_ADMIN_PEPPER=<value> python scripts/bootstrapadmin.py
```

The same pepper value must be supplied to the running service. In
production this typically lives in a secret manager and is read at
service start-up via a custom bootstrap that calls:

```python
from automojo.pychestrate.webservice.secrets.secret_bytes import SecretBytes
from automojo.pychestrate.webservice.security.auth.pepper_loader import (
    set_active_pepper,
)

set_active_pepper(pepper=SecretBytes(b"<value-from-secret-manager>"))
```

Rotating the pepper invalidates every persisted credential — schedule
rotations carefully.

### Session cookie

* **Name** — `pychestrate_session` (constant
  `SESSION_COOKIE_NAME` in
  `webservice.security.auth.cookies`).
* **Body** — opaque server-generated session id (UUID).
* **Attributes** — `HttpOnly` is hard-coded to `True`. Every other
  flag (`Secure`, `SameSite`, `Domain`, `Path`, `Max-Age`) is
  caller-supplied at the seam where the cookie is built
  (`build_session_cookie`). The login endpoint that emits the cookie
  is part of a follow-up slice; until then `bootstrapadmin` prints
  the raw session id and callers send it via
  `Cookie: pychestrate_session=<value>`.

### Session lifetimes

Two parameters are passed to `session_service.open_session`:

| Parameter               | bootstrap-admin default | Recommendation                          |
|-------------------------|-------------------------|------------------------------------------|
| `idle_timeout_seconds`  | 8 hours                 | 30–60 min for human users, 8 h for CLI. |
| `max_lifetime_seconds`  | 24 hours                | Hard ceiling. 8 h interactive / 24 h CLI.|

Each session row carries both deadlines; `resolve_session` rejects
sessions past either.

## RBAC and AccessPolicy

### Role catalog

The Phase-1 extension bootstrap registers a fixed catalog:

| Role             | Intended subject                                     |
|------------------|------------------------------------------------------|
| `system-admin`   | Operators that need write access to every resource.  |
| `auditor`        | Read-only access to audit + secrets metadata.        |
| `project-owner`  | Full control of one project.                         |
| `project-editor` | Create / patch resources within one project.         |
| `project-viewer` | Read-only access to one project.                     |

`scripts/bootstrapadmin.py --create-schema` syncs this catalog into
`rbac_role` rows on first run and is idempotent on re-run.

### Binding scopes

A binding lives at one of three scopes:

* `SYSTEM` — no `scope_id`; applies platform-wide.
* `ORGANIZATION` — `scope_id` is an organization id.
* `PROJECT` — `scope_id` is a project id.

The bootstrap script issues a `(system-admin, SYSTEM)` binding for
the seeded user. Production deployments typically follow up with
project-scoped bindings via `POST /api/v1/rbac/bindings`.

### Per-endpoint AccessPolicy

Endpoints declare their security constraints inline on the
`@RestBlueprint.attach_at` decorator:

```python
from automojo.webworks.security.accesspolicy import AccessPolicy

_ADMIN_POLICY = AccessPolicy(roles=("system-admin",))

class FlowsBlueprint(RestBlueprint):
    @RestBlueprint.attach_at(
        path="/api/v1/flows",
        methods=["POST"],
        access_policy=_ADMIN_POLICY,
    )
    def submit_flow(request: Request) -> JSONResponse:
        ...
```

The policy carries:

* `roles` — tuple of role names; the principal needs **at least one**.
* `scopes` — tuple of permission keys; the principal needs **at least
  one**.
* `require_auth` — defaults to `True`. When `False` plus empty
  `roles`/`scopes`, the policy is effectively informational.
* `constraints` — free-form dict for future engines.

`AccessPolicyMiddleware` reads the matched descriptor's policy and:

* returns **401** when `require_auth` and `request.auth is None`;
* returns **403** when the policy declares roles and the principal's
  role set is disjoint from the requirement;
* returns **403** when the policy declares scopes and the principal's
  permission set is disjoint;
* otherwise calls the next handler.

### Currently gated endpoints

| Method | Path                  | Required role |
|--------|-----------------------|---------------|
| POST   | `/api/v1/projects`    | `system-admin`|
| POST   | `/api/v1/flows`       | `system-admin`|

All other endpoints are public until you gate them. The mechanism is
ready; per-endpoint review and rollout is a follow-up slice.

## Middleware pipeline

The pipeline is assembled by `PychestrateApplication._build_pipeline`
and runs in this order on every request:

1. **`DbSessionMiddleware`** — opens `request.db_session` from the
   shared session factory; closes it on response.
2. **`PychestrateSessionMiddleware`** — reads
   `Cookie: pychestrate_session=<id>`, resolves through
   `session_service.resolve_session`, builds an
   `AuthenticationContext`, attaches it as `request.auth`. Respects
   an existing non-`None` `request.auth` so test scaffolds can
   inject contexts without going through the cookie path.
3. **`AccessPolicyMiddleware`** — enforces the per-endpoint
   `AccessPolicy`. Always last so it sees the populated
   `request.auth`.

Out-of-the-box middleware does **not** include CORS or rate limiting
yet. To add CORS, append
`automojo.webworks.routing.middleware.cors.CORSMiddleware` after the
access policy step (or before, depending on the policy you want for
preflight 204s). The wiring point is
`PychestrateApplication._build_pipeline`.

## FlowRuntime (taskplus orchestration)

`PychestrateApplication` constructs one `FlowRuntime` per app
instance and exposes it as `app.flow_runtime`. The dispatcher
attach-shim sets `request.flow_runtime = app.flow_runtime` on every
request unless a caller (a test) has already injected an override.

Constructor arguments:

| Argument          | Default | Description                                                                 |
|-------------------|---------|-----------------------------------------------------------------------------|
| `max_workers`     | 4       | Maximum concurrent worker threads in the executor.                          |
| `session_factory` | `None`  | When supplied, every state transition writes to a `flow_submission` row.    |

When `session_factory` is `None` the runtime is in-memory only —
submissions disappear on restart. Production deployments should
always pass a factory.

### Persistence model

* Submitting a workflow via `POST /api/v1/flows` writes a row with
  `state=PENDING` and the verbatim YAML.
* The worker thread updates the row to `RUNNING` (with `started_at`),
  runs the engine, captures stdout + log lines into a per-submission
  `StringIO`, and writes the terminal `state` (`SUCCEEDED` /
  `FAILED`) plus `result_code`, `error_text`, `completed_at`, and
  `log_text`.
* On boot, `FlowRuntime` reads every existing row into its in-memory
  cache so historical submissions appear in `GET /api/v1/flows`.

### Log capture caveat

The current implementation attaches a `logging.StreamHandler` to the
**root** logger for the duration of the worker. A second worker
running concurrently against the same engine sees log entries from
the other in its capture buffer. Acceptable for development;
production deployments should switch to a thread-local handler.

## WSGI deployment

### Built-in server

`scripts/serve.py` wraps the `automojo.webworks.wsgi.server`
implementation and is the convenient developer-mode launcher:

```bash
python scripts/serve.py --host 0.0.0.0 --port 8080
```

| Flag        | Default       | Description                  |
|-------------|---------------|------------------------------|
| `--host`    | `127.0.0.1`   | Bind interface.              |
| `--port`    | `8080`        | Bind port.                   |

### gunicorn

For production deployment use a real WSGI server. The
`automojo.pychestrate.webservice.wsgientry` module exposes a
top-level `application` global that gunicorn / uWSGI / waitress can
import directly:

```bash
PYCHESTRATE_DATABASE_URL=postgresql+psycopg://... \
PYCHESTRATE_DEBUG=false \
gunicorn -b 0.0.0.0:8080 --workers 4 \
    'automojo.pychestrate.webservice.wsgientry:application'
```

Worker count tuning notes:

* The `FlowRuntime` thread pool is **per-process**, so each gunicorn
  worker runs its own pool of `max_workers` flow workers.
* Submissions persisted via `flow_submission` rows are visible
  cross-worker via the DB; the in-memory cache is per-worker.
* Authentication state is stateless (cookie + DB lookup), so any
  worker can serve any request.

## Logging

The service emits via the standard Python `logging` module. A
`pychestrate-flow-*` thread-name prefix identifies flow worker
threads. Recommended setup:

```python
import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s [%(threadName)s]: %(message)s",
)
```

For structured logging, install your handler before
`PychestrateApplication(...)` is called.

## Known follow-ups

The configuration surface intentionally stays small while the service
matures. Open work includes:

* Login endpoint that returns a `Set-Cookie` envelope so admins don't
  need to copy-paste the session id from `bootstrapadmin`.
* Per-endpoint `AccessPolicy` rollout to the rest of the gated
  surface (`POST /identity/users`, `POST/DELETE /enrollment-tokens`,
  `POST /clients/{id}/revoke`, etc.).
* Cookie policy (`Secure`, `SameSite`, `Max-Age`, `Domain`) sourced
  from environment variables at the future login seam.
* Thread-local log capture in `FlowRuntime` so concurrent flows don't
  cross-contaminate `log_text`.
* Alembic migrations replacing `metadata.create_all`.
