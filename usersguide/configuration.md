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
| `PYCHESTRATE_COOKIE_SECURE`    | login endpoint                 | no       | `true`                       | Whether the `Secure` flag is emitted on the session cookie.                 |
| `PYCHESTRATE_COOKIE_SAMESITE`  | login endpoint                 | no       | `Lax`                        | `Lax` / `Strict` / `None` for the session cookie `SameSite` attribute.       |
| `PYCHESTRATE_COOKIE_DOMAIN`    | login endpoint                 | no       | (omitted)                    | `Domain` attribute. Empty / unset → no Domain attribute is emitted.         |
| `PYCHESTRATE_COOKIE_PATH`      | login endpoint                 | no       | `/`                          | `Path` attribute on the session cookie.                                     |
| `PYCHESTRATE_COOKIE_MAX_AGE_SECONDS` | login endpoint           | no       | `28800` (8h)                 | `Max-Age` attribute. Also used as the session row's idle/lifetime ceiling.  |
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

The service uses **Alembic** for schema management. The migration
trail lives in `alembic/versions/` and the active revision pointer
is recorded in the `alembic_version` row of the target database.

Recommended bring-up:

```bash
PYCHESTRATE_DATABASE_URL=... python scripts/initdb.py    # one-shot upgrade
PYCHESTRATE_DATABASE_URL=... python scripts/serve.py     # boot the service
```

`scripts/initdb.py` runs `alembic upgrade head` against the
configured DB. To bypass Alembic and use
`PychestratePhase1Base.metadata.create_all` directly (faster for
ephemeral SQLite tests), pass `--use-metadata-create-all`.

#### Authoring a new migration

```bash
PYCHESTRATE_DATABASE_URL=sqlite:///./pychestrate.db \
    .venv/bin/python -m alembic revision \
        --autogenerate -m "<short description>"
```

Alembic compares the SQLAlchemy metadata (loaded by
`alembic/env.py` via the
`automojo.pychestrate.webservice.pychestrateapplication` import)
against the live database and emits a new file under
`alembic/versions/`. Review the generated `upgrade()` and
`downgrade()` bodies — autogenerate is good but not infallible —
and patch in any `import sqlalchemy_utils` /
`from sqlalchemy.dialects import postgresql` /
`from sqlalchemy import Text` lines required by the column types.

#### Applying migrations

```bash
PYCHESTRATE_DATABASE_URL=... .venv/bin/python -m alembic upgrade head
PYCHESTRATE_DATABASE_URL=... .venv/bin/python -m alembic downgrade -1
PYCHESTRATE_DATABASE_URL=... .venv/bin/python -m alembic current
PYCHESTRATE_DATABASE_URL=... .venv/bin/python -m alembic history
```

The bring-up bootstrap (`PYCHESTRATE_CREATE_SCHEMA=true` env var on
`scripts/serve.py` / `wsgientry.application`) also runs
`alembic upgrade head` so a fresh deployment can self-bootstrap. In
production you typically run the upgrade as a separate step in your
deployment pipeline so the schema migration completes before any
worker starts serving traffic.

#### Tables in the baseline

The baseline migration (`fc197732dce1_phase1_baseline_schema`)
creates 62 tables covering:

* Identity & auth: `identity_users`, `auth_sessions`,
  `auth_local_credentials`, MFA enrollments + challenges,
  `auth_provider_directory`.
* RBAC: `rbac_roles`, `rbac_role_bindings`,
  `rbac_role_permissions`.
* Audit: `audit_records`, `audit_event_catalog`, sinks.
* Secrets: `phase1_secrets`, `phase1_secret_versions`,
  `secret_acls`.
* Retention: `retention_policies`, `retention_runs`,
  `retention_action_results`.
* Projects: `projects_*`, member bindings.
* Pods (Layer-3): definitions / versions / state / registrations /
  templates / lifecycle log / dynamic materializations.
* Clients: registry / inventory / capabilities / revocations.
* Notifications: channels, dispatch attempts, dead letters.
* Tagging: assignments, taxonomies.
* Variables: bindings, scope cascades.
* Agents: rollouts, stages, offers, frame audit, sessions.
* Orchestration: `flow_submission` (taskplus state).

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
* **Attributes** — `HttpOnly` is hard-coded to `True`. The remaining
  attributes (`Secure`, `SameSite`, `Domain`, `Path`, `Max-Age`) are
  sourced by the login endpoint from the `PYCHESTRATE_COOKIE_*`
  environment variables via
  `automojo.pychestrate.webservice.security.auth.cookiepolicy.load_cookie_policy_from_env`.
  Defaults are production-friendly (`Secure=true`, `SameSite=Lax`,
  no Domain, `Path=/`, `Max-Age=28800` = 8 hours). `Secure=true`
  means a non-TLS deployment must explicitly set
  `PYCHESTRATE_COOKIE_SECURE=false` for browsers to retain the
  cookie.

### Login endpoint

`POST /api/v1/auth/login` accepts a JSON body. The flow is one or
two stages depending on whether the user has any verified MFA
enrollment.

**Stage one** — credentials only:

```json
{"login_name": "alice", "password": "secret"}
```

* **200** with the session payload + `Set-Cookie` when no MFA is
  enrolled.
* **200** with `{"mfa_required": true, "user_id": "...",
  "challenge_id": "...", "method_name": "totp", "expires_at":
  "..."}` when MFA is required. **No** `Set-Cookie` is emitted in
  this stage.
* **401** on invalid credentials.
* **400** on missing / non-object body.

**Stage two** — credentials + MFA proof:

```json
{
  "login_name": "alice",
  "password": "secret",
  "challenge_id": "<from stage one>",
  "mfa_code": "<TOTP digits / push-ack token / etc.>"
}
```

* **200** with the session payload (`session_id`, `user_id`,
  `expires_in_seconds`, `cookie_name`) + `Set-Cookie:
  pychestrate_session=<id>; HttpOnly; Secure; SameSite=Lax; Path=/;
  Max-Age=28800` (attributes vary with the env-var policy). The
  opened session row records the MFA method via
  `auth_session.mfa_method_name`.
* **401** with `challenge_unknown` / `challenge_expired` /
  `challenge_rejected` when MFA verification fails.

Single-stage shortcut: the caller may submit creds + challenge_id +
mfa_code in one POST when it already has a fresh challenge_id
(e.g., from a prior `/auth/mfa/challenge` call); the endpoint
treats that as the second stage directly.

Backoff: the local-credential verifier applies an exponential
backoff keyed on `(login_name, source_ip)`. The login endpoint
sources `source_ip` from the first entry of the `X-Forwarded-For`
header when present, falling back to `"unknown"`. Place the service
behind a reverse proxy that sets `X-Forwarded-For` so the backoff
keys per-client correctly.

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

Every write endpoint on the migrated controllers is gated by
`AccessPolicy`. The exact role set varies:

* **`system-admin` only** — platform-level operations such as
  creating new projects, issuing enrollment tokens, identity-user
  creation, RBAC binding writes, agent rollouts, retention
  policies, notifications, audit / log resources.
* **`system-admin` or `project-owner`** — project lifecycle
  operations on an existing project: `archive`, `unarchive`,
  `delete`, member adds/removes.
* **`system-admin`, `project-owner`, or `project-editor`**
  (`_PROJECT_WRITE`) — content-edits inside a project: `PATCH
  /projects/{slug}`, every `pod-definitions` / `pod-templates` /
  scoped-run-variable write, every `/tags/...` and `/variables/...`
  write.

Reads (GET) and the authentication endpoints stay public.

> **Cross-project leakage caveat.** The role resolver currently
> emits role NAMES without scope context. A user with `project-owner`
> at one project's PROJECT scope therefore clears the policy for
> every other project's URL too. Per-project scope enforcement —
> resolving the URL's `project_id` path parameter against the
> binding's `scope_id` — is the next refinement.

Gated:

| Method | Path                                               |
|--------|----------------------------------------------------|
| POST   | `/api/v1/identity/users`                           |
| POST   | `/api/v1/flags`                                    |
| POST   | `/api/v1/rbac/bindings`                            |
| DELETE | `/api/v1/rbac/bindings/{binding_id}`               |
| POST   | `/api/v1/rbac/check`                               |
| POST   | `/api/v1/clients/{client_id}/revoke`               |
| PUT    | `/api/v1/clients/{client_id}/attributes`           |
| POST   | `/api/v1/enrollment-tokens`                        |
| DELETE | `/api/v1/enrollment-tokens/{token_id}`             |
| POST   | `/api/v1/enrollment-tokens/clients/{cid}/revoke`   |
| POST   | `/api/v1/retention/policies`                       |
| POST   | `/api/v1/retention/policies/{id}/publish`          |
| POST   | `/api/v1/notifications/channels`                   |
| POST   | `/api/v1/projects`                                 |
| PATCH  | `/api/v1/projects/{slug}`                          |
| DELETE | `/api/v1/projects/{slug}`                          |
| POST   | `/api/v1/projects/{slug}/archive`                  |
| POST   | `/api/v1/projects/{slug}/unarchive`                |
| POST   | `/api/v1/projects/{slug}/members`                  |
| DELETE | `/api/v1/projects/{slug}/members/{user_id}`        |
| DELETE | `/api/v1/projects/{slug}/members/{user_id}/{role}` |
| POST   | `/api/v1/projects/{pid}/pod-definitions`           |
| POST   | `/api/v1/projects/{pid}/pod-templates`             |
| POST   | `/api/v1/projects/{pid}/pod-templates/{tid}/materialize` |
| PUT    | `/api/v1/projects/{pid}/runs/{rid}/variables/{name}` |
| DELETE | `/api/v1/projects/{pid}/runs/{rid}/variables/{name}` |
| POST   | `/api/v1/agent-rollouts`                           |
| POST   | `/api/v1/agent-rollouts/{rollout_id}/start`        |
| POST   | `/api/v1/tags/{kind}/{id}`                         |
| DELETE | `/api/v1/tags/{kind}/{id}/{tag}`                   |
| PUT    | `/api/v1/variables/{scope}/{scope_id}/{name}`      |
| DELETE | `/api/v1/variables/{scope}/{scope_id}/{name}`      |
| POST   | `/api/v1/flows`                                    |
| POST   | `/api/v1/auth/providers/{kind}/{name}/enable`      |
| POST   | `/api/v1/auth/providers/{kind}/{name}/disable`     |

Intentionally ungated:

| Method | Path                                  | Why                                                              |
|--------|---------------------------------------|------------------------------------------------------------------|
| POST   | `/api/v1/auth/login`                  | The caller has no cookie yet; credentials are the auth factor.   |
| POST   | `/api/v1/auth/logout`                 | Idempotent; tolerates anonymous callers.                         |
| GET    | `/api/v1/auth/providers`              | Needed by the login picker before any session exists.            |
| POST   | `/api/v1/auth/mfa/challenge`          | Scoped to the partial-session principal; the partial-session UX is the gate.|
| POST   | `/api/v1/auth/mfa/verify`             | Same.                                                            |
| POST   | `/api/v1/enrollment-tokens/redeem`    | Agents have no cookie at redemption; the secret is the factor.   |

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
3. **`BearerTokenMiddleware`** — when `request.auth` is still
   `None` after the cookie middleware, reads `Authorization: Bearer
   <token>`, hashes the value via the same HMAC-SHA256 + pepper
   recipe the enrollment redeem flow uses, looks up the matching
   `clients` row, and attaches an `AuthenticationContext` whose
   principal carries `roles={"agent"}` plus the client's
   `client_id` / `pod_name` / `project_id` attributes. Cookie
   callers keep their human seat; bearer-only callers (agents) get
   the agent seat.
4. **`AccessPolicyMiddleware`** — enforces the per-endpoint
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

### Log capture

A single `_ThreadLocalLogHandler` is attached to the root logger when
the runtime is constructed. Each worker thread binds its own
`io.StringIO` buffer to the handler before invoking the engine and
detaches it in the `finally` clause, so concurrent flows write only
to their own `log_text`. The handler is removed from the root logger
when the runtime is shut down.

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

* Per-project scope enforcement — the role resolver should emit
  scoped names (e.g. `project-owner:<project_id>`) and the
  middleware should match those against the URL's `project_id`
  path parameter so a `project-owner` on project A cannot manage
  project B.
* `auth/mfa/challenge` and `auth/mfa/verify` need their own gates
  once the partial-session UX is finalized.
