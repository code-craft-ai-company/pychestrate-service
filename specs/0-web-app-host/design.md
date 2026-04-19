# 0-web-app-host — Design

## Architecture

The web app host is the outermost process shell. It owns a single
`WebApplication` persona (provided by `automojo-webworks`), a single WSGI
dispatcher, and the native WebWorks WSGI server. All feature modules (Layer 0
siblings, Layer E, Layer 1+) register against it during startup via a typed
registration API. The host is authoritative for the following state:
(1) the registered route table, (2) the ordered startup/shutdown hook list,
(3) the active request-id for each in-flight request. Everything else
(sessions, auth, DB connection, bus, extension registry) is owned by other
features and merely *attached* to the host during its `invoke_startup_hooks`
phase. The host lives in Phase 0 per implementation-plan.md and intentionally
knows nothing about business entities.

## Data Model

The host has no persistent state. It holds the following in-process
structures for the life of the process:

- `startup_hooks: list[StartupHookRecord]`
  - `name: str` — unique per process
  - `priority: int` — lower runs earlier
  - `callable: Callable[[WebApplication], None]`
  - `registered_at: datetime`
- `shutdown_hooks: list[ShutdownHookRecord]` — same shape as above, runs in
  reverse priority order.
- `request_context: ContextVar[RequestContext]` where
  `RequestContext` has `request_id: str`, `method: str`, `path: str`,
  `started_at: float`, `remote_addr: str`.
- `service_config: ServiceConfig` — immutable dataclass loaded from env +
  optional `pychestrate.yaml`; fields include `listen_host: str`,
  `listen_port: int`, `workers: int`, `threads: int`,
  `shutdown_grace_seconds: int`, `dev_mode: bool`, `log_dir: Path`.

No DB tables, no indices. State lives in memory only.

## Interfaces

### Public API

HTTP surface:

- `GET /__health/live` — 200 while server is serving; delegates to
  `0-system-health` once that feature lands.
- `GET /__health/startup` — 200 once `invoke_startup_hooks` completes,
  503 otherwise.

No other routes are owned by this feature — they are registered by siblings.

### Internal API

```python
def establish_pychestrate_app(
    config: ServiceConfig
) -> WebApplication:
    """
        Build the WebWorks WebApplication persona used by all features.

        :param config: The immutable service configuration loaded at startup.

        :returns: A fully-constructed but *not started* WebApplication.
        :raises: ConfigurationError
    """
    ...


def register_route(
    app: WebApplication,
    path: str,
    methods: list[str],
    handler: Callable[[Request], Response]
) -> None:
    """
        Register a route on the application. Must be called before
        invoke_startup_hooks.

        :param app: The WebApplication returned by establish_pychestrate_app.
        :param path: The URL path pattern.
        :param methods: Allowed HTTP methods.
        :param handler: The request handler callable.

        :returns: None
        :raises: SemanticError
    """
    ...


def register_startup_hook(
    app: WebApplication,
    name: str,
    hook: Callable[[WebApplication], None],
    priority: int
) -> None:
    """
        Register a startup hook. Hooks run in ascending priority.

        :param app: The target application.
        :param name: Unique hook name.
        :param hook: The callable invoked during startup.
        :param priority: Ordering key.

        :returns: None
        :raises: SemanticError
    """
    ...


def register_shutdown_hook(
    app: WebApplication,
    name: str,
    hook: Callable[[WebApplication], None],
    priority: int
) -> None:
    """
        Register a shutdown hook. Hooks run in descending priority.

        :param app: The target application.
        :param name: Unique hook name.
        :param hook: The callable invoked during shutdown.
        :param priority: Ordering key.

        :returns: None
        :raises: SemanticError
    """
    ...


def run_pychestrate_server(
    app: WebApplication,
    config: ServiceConfig
) -> int:
    """
        Invoke startup hooks, create the WSGI application, and run the
        WebWorks server until signaled to stop.

        :param app: The configured WebApplication.
        :param config: The service configuration.

        :returns: Process exit code.
        :raises: ConfigurationError
    """
    ...
```

### Extension Surface

None. The host intentionally exposes no factory protocols or
`ResourceExtension` bases. Every extension point in Pychestrate is owned by
the feature it belongs to; the host only provides the hook primitives
(`register_startup_hook`, `register_shutdown_hook`, `register_route`) that
`E-extension-host` uses to mount itself.

### Events Emitted

Process-local lifecycle channel only (the general-purpose bus in
`0-message-bus` is not yet available when the host starts):

- `webapp.startup.begin` — `{config: ServiceConfig}`
- `webapp.startup.phase_completed` — `{phase: str, duration_ms: float}`
- `webapp.startup.completed` — `{duration_ms: float, hooks_run: int}`
- `webapp.shutdown.started` — `{signal: str}`
- `webapp.shutdown.completed` — `{duration_ms: float, inflight_cancelled: int}`

### Events Consumed

None.

## Component Breakdown

All paths are rooted at `source/site/automojo/pychestrate/webservice/`.

- `host/app_pychestrate_main.py` — process entrypoint (replaces current
  scaffold at `source/site/app_pychestrate_main.py` by moving into the
  package; the current file becomes a thin re-export shim).
- `host/persona.py` — `establish_pychestrate_app`, wraps
  `automojo.webworks.webapplication.establish_webapp_persona`.
- `host/config.py` — `ServiceConfig`, env + yaml loader.
- `host/registration.py` — `register_route`, `register_startup_hook`,
  `register_shutdown_hook`.
- `host/lifecycle.py` — `invoke_startup_hooks`, `invoke_shutdown_hooks`,
  SIGTERM handler, drain logic.
- `host/middleware/request_context.py` — request-id injection, context var
  binding, access log emission.
- `host/middleware/error_boundary.py` — production-vs-dev error rendering.
- `host/runner.py` — `run_pychestrate_server`, wraps
  `automojo.webworks.wsgi.server.run_server`.
- `host/probes.py` — minimal `/__health/live` and `/__health/startup`
  handlers, superseded by `0-system-health` once it lands.

## Key Flows

### Flow 1 — Cold start

1. `__main__` calls `pychestrate_website_main`.
2. `load_service_config` reads env + optional YAML → `ServiceConfig`.
3. `configure_logging` sets log directory, JSON formatter, log level.
4. `establish_pychestrate_app(config)` builds the persona.
5. Feature modules call `register_startup_hook` / `register_route`.
6. `invoke_startup_hooks` runs hooks in ascending priority; emits
   `webapp.startup.phase_completed` per hook with duration.
7. `create_wsgi_application` composes middleware chain:
   `request_context → error_boundary → dispatcher`.
8. `run_server` binds the socket and enters the accept loop; emits
   `webapp.startup.completed`.

### Flow 2 — Graceful shutdown on SIGTERM

1. `_sigterm_handler` sets `shutting_down = True` and stops the accept loop.
2. `webapp.shutdown.started` is emitted with `signal: "SIGTERM"`.
3. In-flight requests continue; new connections receive 503 `Retry-After: 5`.
4. Wait up to `shutdown_grace_seconds`; cancel remainder; emit
   `pychestrate.webapp.shutdown.forced_cancel` if count > 0.
5. `invoke_shutdown_hooks` runs hooks in descending priority.
6. `webapp.shutdown.completed` is emitted; process returns exit code 0.

### Flow 3 — Request correlation

1. Request arrives; `request_context` middleware reads `X-Request-Id`.
2. If absent or malformed, a ULID is generated.
3. The id is bound to `request_context` ContextVar.
4. Handler runs.
5. On response, middleware appends `X-Request-Id` header, emits
   `pychestrate.webapp.access`, records latency histogram.

## Error Handling

- `ConfigurationError` raised during `load_service_config` or
  `establish_pychestrate_app` is logged as
  `pychestrate.webapp.startup.failed` and causes process exit code `78`.
  Multiline messages use `os.linesep.join([...])` per AGENTS.md.
- `SemanticError` raised by `register_*` APIs (duplicate hook name,
  registration after startup) is never caught — it bubbles and crashes the
  process so misuse is loud.
- Any exception raised by a startup hook is wrapped with context
  `("Startup hook {name} failed during phase {phase}", cause)` and re-raised
  as `ConfigurationError` so the operator sees the offending hook name.
- Per-request exceptions are caught exactly once by `error_boundary`
  middleware, logged as `pychestrate.webapp.request.failed`, and translated
  to `500` responses. In dev mode the traceback is included in the body;
  in production only the `request_id` is returned.

Error message construction example:

```python
err_msg_lines = ["Duplicate startup hook registration rejected."]
err_msg_lines.append("HOOK NAME: {}".format(name))
err_msg_lines.append("EXISTING PRIORITY: {}".format(existing.priority))
err_msg_lines.append("NEW PRIORITY: {}".format(priority))

err_msg = os.linesep.join(err_msg_lines)
raise SemanticError(err_msg) from None
```

## Security Considerations

- No authentication enforced at this layer; `1-authentication` mounts as
  middleware during Phase 1.
- Error bodies in production mode contain only `{"request_id": "..."}` —
  never the exception class, message, or traceback.
- Dev mode (`PYCHESTRATE_DEV_MODE=1`) is gated: in containerized deploys the
  env var is stripped by the release channel (see `10-release-channels`).
- Inbound `X-Request-Id` is validated against the ULID regex before binding
  to any logging context to prevent log-injection.
- `/__health/live` and `/__health/startup` are the only endpoints that may
  bypass future auth; they report no entity data.
- The host does not read or write secrets — that is `1-secrets-vault`.

## Observability

Metrics (Prometheus naming):

- `pychestrate_webapp_startup_duration_seconds{phase}` — histogram
- `pychestrate_webapp_requests_total{method,path,status}` — counter
- `pychestrate_webapp_request_duration_seconds{method,path}` — histogram
  with buckets `[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10]`
- `pychestrate_webapp_inflight_requests` — gauge
- `pychestrate_webapp_shutdown_drain_seconds` — histogram

Log events (structured JSON):

- `pychestrate.webapp.startup.begin`
- `pychestrate.webapp.startup.phase_completed`
- `pychestrate.webapp.startup.completed`
- `pychestrate.webapp.startup.failed`
- `pychestrate.webapp.access`
- `pychestrate.webapp.request.failed`
- `pychestrate.webapp.shutdown.started`
- `pychestrate.webapp.shutdown.forced_cancel`
- `pychestrate.webapp.shutdown.completed`

Trace spans:

- `pychestrate.webapp.request` — parent span for every request, carries
  `pychestrate.request_id` attribute.
- `pychestrate.webapp.startup` — parent span for the full startup sequence;
  each hook is a child span `pychestrate.webapp.startup.hook` with attribute
  `hook.name`.

Dashboards consuming these are defined under `9-admin-ui` and
`7-orchestration-metrics`.

## Open Questions

- Should `shutdown_grace_seconds` be configurable per-route (some handlers
  may legitimately run >30s)? Timebox: decide before Phase 3 (test run
  streaming endpoints).
- Do we adopt OpenTelemetry context propagation headers
  (`traceparent`/`tracestate`) in Phase 0, or defer to `10-observability`?
  Timebox: decide before Phase 0 exit.
- Do we retain the `scms` logger name inherited from the initial scaffold or
  rename to `pychestrate`? Timebox: decide before Phase 0 exit to avoid log
  pipeline churn.
