# 0-web-app-host — Requirements

## Introduction

The `0-web-app-host` feature is the Pychestrate service's process entrypoint,
WebWorks application bootstrap, and native WSGI server runner. It lives at the
bottom of Layer 0 (Platform Foundation) — every other feature mounts routes,
middleware, request filters, and lifecycle hooks through the application
persona established here. The feature ships in **Phase 0** and is the
prerequisite for `0-persistence`, `0-message-bus`, `0-object-store`,
`0-system-health`, `10-observability`, and the Phase 0.5 `E-extension-host`.
An initial scaffold already exists at `source/site/app_pychestrate_main.py`;
this specification formalizes that scaffold into a deterministic, testable,
operationally-instrumented host.

## Requirements

### Requirement 1: Deterministic Startup Sequence

**User Story:** As a service operator, I want the web app to follow a single,
documented startup order, so that dependent subsystems (persistence, bus,
extension host) can register against it without race conditions.

**Acceptance Criteria (EARS):**

1. WHEN `pychestrate_website_main` is invoked THEN the system SHALL execute
   phases `configure_logging` → `load_service_config` → `establish_webapp_persona`
   → `register_core_middleware` → `invoke_startup_hooks` → `create_wsgi_application`
   → `run_server` in that exact order.
2. IF any startup phase raises `ConfigurationError` THEN the system SHALL log
   event `pychestrate.webapp.startup.failed` with the phase name and exit with
   process exit code `78` (EX_CONFIG).
3. WHILE startup hooks are executing the system SHALL refuse to bind the
   listening socket until every hook returns.
4. WHERE the environment variable `PYCHESTRATE_DEV_MODE=1` is set the system
   SHALL enable request tracebacks in HTTP error bodies.

### Requirement 2: Graceful Shutdown and Drain

**User Story:** As a deploy pipeline, I want the service to drain in-flight
requests on `SIGTERM`, so that rolling deploys do not sever active sessions.

**Acceptance Criteria (EARS):**

1. WHEN the host receives `SIGTERM` THEN the system SHALL stop accepting new
   connections within 100 ms and continue serving in-flight requests up to
   `shutdown_grace_seconds` (default 30).
2. IF in-flight requests exceed `shutdown_grace_seconds` THEN the system SHALL
   cancel them, log event `pychestrate.webapp.shutdown.forced_cancel` with the
   count, and exit with process exit code `0`.
3. WHILE draining the system SHALL respond `503` with header
   `Retry-After: 5` to new connections that race the socket close.
4. WHEN shutdown completes the system SHALL publish `webapp.shutdown.completed`
   on the in-process lifecycle channel so `0-message-bus`, `0-persistence`,
   and `E-extension-host` can flush before exit.

### Requirement 3: Route, Middleware, and Lifecycle Registration API

**User Story:** As a feature author, I want a single, typed API for adding
routes, middleware, and startup/shutdown hooks, so that feature modules do not
reach into server internals.

**Acceptance Criteria (EARS):**

1. WHEN a feature module calls `register_route(app, path, methods, handler)`
   BEFORE `invoke_startup_hooks` THEN the system SHALL accept the registration.
2. IF `register_route` is called AFTER `invoke_startup_hooks` completes THEN
   the system SHALL raise `SemanticError` (never caught).
3. WHEN `register_startup_hook(app, name, callable, priority)` is called THEN
   the system SHALL execute hooks in ascending `priority` order and fail-fast
   on any exception.
4. WHERE two startup hooks register the same `name` the system SHALL raise
   `SemanticError` at registration time to prevent silent override.

### Requirement 4: Request Correlation and Access Log

**User Story:** As an operator debugging a failure, I want every request to
carry a correlation id that flows through logs, metrics, and traces.

**Acceptance Criteria (EARS):**

1. WHEN a request arrives without header `X-Request-Id` THEN the system SHALL
   generate a ULID and bind it to the request context.
2. IF `X-Request-Id` is present AND matches regex `^[0-9A-HJKMNP-TV-Z]{26}$`
   (ULID Crockford base32) THEN the system SHALL reuse it.
3. WHEN the response is sent THEN the system SHALL emit log event
   `pychestrate.webapp.access` with fields `request_id`, `method`, `path`,
   `status`, `duration_ms`, `remote_addr`.
4. WHERE `10-observability` has installed a trace exporter the system SHALL
   set the `request_id` as the span attribute `pychestrate.request_id`.

## Property-Based Test Requirements

### Property 1: Startup Hook Ordering is Stable Under Shuffled Registration

- **Invariant:** For any set of startup hooks registered in any order, the
  execution order is fully determined by `(priority, name)` — registration
  order cannot leak into behavior.
- **Generator:** `hypothesis.strategies.lists(tuples(integers(min_value=0,
  max_value=999), text(min_size=1, max_size=32, alphabet=ascii_letters)),
  min_size=1, max_size=50, unique_by=lambda x: x[1])`, then shuffle before
  registration.
- **Assertion:** The observed execution sequence equals the input sequence
  sorted by `(priority, name)`.
- **Sample size:** 1000 generated cases

### Property 2: Request-Id Round-Trips Preserve Correlation Across Layers

- **Invariant:** For any request, the `X-Request-Id` observed in the access
  log, the metric label, and the response header are byte-identical.
- **Generator:** `hypothesis.strategies.one_of(none(),
  text(alphabet="0123456789ABCDEFGHJKMNPQRSTVWXYZ", min_size=26, max_size=26))`
  fed as the inbound `X-Request-Id` header.
- **Assertion:** `response.headers["X-Request-Id"] ==
  access_log.request_id == metric_label.request_id`, and when the input is
  `None`, the emitted id matches the ULID regex.
- **Sample size:** 1000 generated cases

## Non-Functional Requirements

- **NFR-1 (Performance):** Cold-start (process launch to socket listening) must
  complete in under 2.0 seconds on a 4 vCPU host with an empty extension set.
  p99 overhead added by the host per request (excluding handler work) is
  under 1.5 ms.
- **NFR-2 (Security):** `PYCHESTRATE_DEV_MODE` MUST default to `0`. Error
  responses MUST NOT leak stack frames, file paths, or env values in
  production mode. All inbound header names MUST be lowercased and validated
  against `^[a-z0-9-]{1,128}$` before context binding.
- **NFR-3 (Observability):** Emit metrics `pychestrate_webapp_startup_duration_seconds`
  (histogram, labels `phase`), `pychestrate_webapp_requests_total`
  (counter, labels `method,path,status`), `pychestrate_webapp_request_duration_seconds`
  (histogram, labels `method,path`), `pychestrate_webapp_inflight_requests`
  (gauge). Emit log events `pychestrate.webapp.startup.phase_completed`,
  `pychestrate.webapp.access`, `pychestrate.webapp.shutdown.started`,
  `pychestrate.webapp.shutdown.completed`. Trace span `pychestrate.webapp.request`
  wraps every request.
- **NFR-4 (Reliability):** Availability target 99.95% per calendar month
  excluding planned maintenance declared via `0-maintenance-mode`. A single
  slow handler MUST NOT block health probes: probe requests route through a
  dedicated thread budget so the server can always respond to liveness.

## Out of Scope

- Authentication and session handling (see `1-authentication`).
- RBAC enforcement (see `1-rbac`).
- Extension discovery and lifecycle (see Layer E — Phase 0.5).
- TLS termination — assumed handled by a fronting reverse proxy; the host
  listens HTTP only.
- Clustering or multi-process worker management beyond what WebWorks' WSGI
  server already provides.

## Dependencies

- **Depends on:** `codecraftai-webworks` (external package providing
  `establish_webapp_persona`, `create_wsgi_application`, `run_server`).
- **Depended on by:** `0-persistence`, `0-message-bus`, `0-object-store`,
  `0-system-health`, `0-maintenance-mode`, `10-observability`,
  `E-extension-host`, and every feature in Layer 1 and beyond.
- **Extension points exposed:** None directly. All extensibility is delegated
  to `E-extension-host` which mounts onto the hooks defined by this feature.
