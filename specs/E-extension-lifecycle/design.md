# E-extension-lifecycle — Design

## Architecture

E-extension-lifecycle is a coordinator owned by `E-extension-host` that
sits between the host's registry and the service's broader lifecycle
signals (startup, project load, drain, shutdown). The coordinator is
invoked by the app bootstrap for each phase; it walks the host's sorted
factory chain and all resource collections, collecting every class that
declares a hook, then invokes them in order with per-hook timeouts
enforced via `concurrent.futures.ThreadPoolExecutor` futures. Hook calls
are wrapped to reclassify any raised exception as an
`ExtensionHookError`. The lifecycle layer is the source of truth for
each extension's current `health_state` (loaded, ready, quarantined,
draining, unloaded).

## Data Model

In-memory (no SQL):

- `ExtensionLifecycleRecord` — dataclass:
  - `extension_qualname: str`
  - `phase: Literal["on_load","on_service_ready","on_project_loaded",
    "on_service_draining","on_unload"]`
  - `started_at: datetime`
  - `completed_at: Optional[datetime]`
  - `duration_seconds: Optional[float]`
  - `status: Literal["ok","timeout","error","skipped"]`
  - `error_type: Optional[str]`
  - `error_message: Optional[str]`
- `ExtensionHealthState` — dataclass:
  - `extension_qualname: str`
  - `state: Literal["loaded","ready","quarantined","draining","unloaded"]`
  - `last_event_at: datetime`
  - `last_error: Optional[str]`
  - `consecutive_failures: int`

## Interfaces

### Public API

Admin REST (Phase 10 via `E-extension-registry-ui`):

- `GET /admin/extensions/{name}/lifecycle` — permission
  `extensions.read` — returns the most recent records per phase plus
  health.
- `POST /admin/extensions/{name}/quarantine` — permission
  `extensions.quarantine` — marks the extension quarantined.
- `POST /admin/extensions/{name}/unquarantine` — permission
  `extensions.quarantine`.

### Internal API

Code under
`source/site/ccai/pychestrate/webservice/extension/lifecycle/`.

```python
# coordinator.py
class LifecycleCoordinator:
    """
        Drives lifecycle phase execution across loaded extensions.
    """

    def __init__(self, *, host: "ExtensionHost",
                 phase_timeouts: Mapping[str, float],
                 strict: bool) -> None:
        ...

    def run_on_load(self) -> List[ExtensionLifecycleRecord]:
        ...

    def run_on_service_ready(self) -> List[ExtensionLifecycleRecord]:
        ...

    def run_on_project_loaded(self, *, project: "Project") -> List[ExtensionLifecycleRecord]:
        ...

    def run_on_service_draining(self) -> List[ExtensionLifecycleRecord]:
        ...

    def run_on_unload(self) -> List[ExtensionLifecycleRecord]:
        ...

    def invoke_hook(self, *, extension_cls: Type, phase: str,
                    kwargs: Optional[Dict[str, Any]] = None,
                    timeout_seconds: float) -> ExtensionLifecycleRecord:
        ...


def get_lifecycle_coordinator() -> LifecycleCoordinator:
    ...


# health.py
class ExtensionHealthTable:
    """
        Tracks per-extension health across lifecycle events.
    """

    def __init__(self) -> None:
        ...

    def mark(self, *, qualname: str,
             state: str, error: Optional[str] = None) -> None:
        ...

    def get(self, *, qualname: str) -> Optional[ExtensionHealthState]:
        ...

    def list_all(self) -> List[ExtensionHealthState]:
        ...


def get_extension_health_table() -> ExtensionHealthTable:
    ...
```

### Hook signatures

```python
class MyDriverFactory(FactoryExtension):
    PRECEDENCE = 100
    factory_protocol_name = "object_store_driver"

    @classmethod
    def on_load(cls) -> None:
        ...

    @classmethod
    def on_service_ready(cls) -> None:
        ...

    @classmethod
    def on_project_loaded(cls, *, project: "Project") -> None:
        ...

    @classmethod
    def on_service_draining(cls) -> None:
        ...

    @classmethod
    def on_unload(cls) -> None:
        ...
```

### Extension Surface

The five hook names are the surface itself. Following the Aspects
pattern, the timeout per phase is a caller parameter, not a decorator on
the hook.

### Events Emitted

- `extension.hook_started` — `{qualname, phase, timeout_seconds}`
- `extension.hook_completed` — `{qualname, phase, duration_seconds}`
- `extension.call_failed` — `{qualname, phase, reason, traceback}`
- `extension.quarantined` — `{qualname, reason}`
- `extension.unquarantined` — `{qualname, actor}`

### Events Consumed

- `entity.project.loaded` (from `2-projects`) → triggers
  `run_on_project_loaded`.
- `system.drain_started` (from `0-maintenance-mode`) → triggers
  `run_on_service_draining`.
- `system.shutdown_requested` → triggers `run_on_unload`.

## Component Breakdown

```
source/site/ccai/pychestrate/webservice/extension/lifecycle/
    __init__.py
    coordinator.py        # LifecycleCoordinator
    health.py             # ExtensionHealthTable
    records.py            # ExtensionLifecycleRecord dataclass
    hook_signatures.py    # Signature validation helpers
    admin_routes.py       # /admin/extensions/{name}/lifecycle +
                          # quarantine routes
    errors.py             # ExtensionHookError exception
```

## Key Flows

### Flow A — Startup

1. Host finishes bootstrap; coordinator's `run_on_load` fires.
2. For every extension with an `on_load` classmethod, coordinator
   submits the call to the executor with its timeout; collects the
   record; emits events.
3. Any failure in strict mode is recorded and (for `on_load`) triggers
   a `ConfigurationError` that aborts the app; in permissive mode, the
   extension is quarantined.
4. App continues and calls `run_on_service_ready`; same flow with
   fail-closed readiness gating in strict mode.
5. `0-system-health` marks the service `ready` when coordinator
   reports no strict-mode failures.

### Flow B — Project load

1. `2-projects` emits `entity.project.loaded`.
2. Coordinator invokes `run_on_project_loaded(project=<p>)`.
3. Per-extension records persist; quarantine decisions update
   `ExtensionHealthTable`.

### Flow C — Drain and shutdown

1. Operator toggles maintenance drain; bus emits
   `system.drain_started`.
2. Coordinator runs `on_service_draining` in ascending PRECEDENCE;
   collects records; best-effort on failures.
3. When shutdown is requested, coordinator runs `on_unload` in
   descending PRECEDENCE; idempotent on repeat calls.

## Error Handling

- `ExtensionHookError` — wraps the original exception with qualname,
  phase, and PRECEDENCE.
- `ConfigurationError` — raised only during startup under strict mode
  for failed `on_load` / `on_service_ready`. Multiline message via
  `os.linesep.join`.
- `SemanticError` from within a hook is never caught; lets the caller
  see API misuse.
- Timeouts are not exceptions; they are record rows with status
  `timeout` and a `hook_timeout` bus event.

## Security Considerations

- Hooks execute in the service process; capability gating (Phase 8)
  routes hook invocation through `E-extension-sandbox`.
- Admin routes gated by `extensions.read` or `extensions.quarantine`.
- Audit log entries on quarantine / unquarantine via `1-audit-log`.

## Observability

- Metrics:
  - `pychestrate_extension_hook_duration_seconds{phase,extension}`
  - `pychestrate_extension_hook_failures_total{phase,reason}`
  - `pychestrate_extension_hook_timeouts_total{phase}`
  - `pychestrate_extension_quarantined_total{reason}`
- Log events: `pychestrate_extension_hook_started`,
  `pychestrate_extension_hook_completed`,
  `pychestrate_extension_hook_failed`,
  `pychestrate_extension_quarantined`,
  `pychestrate_extension_unquarantined`.
- Trace span: `pychestrate_extension.hook.<phase>`.

## Open Questions

- Should we surface per-hook cancellation via an explicit
  `cancel_token` argument? Timebox to Phase 1 when long-running
  `on_project_loaded` patterns first appear.
- Should quarantine be persisted across restarts (DB-backed) or only
  in-process? Timebox to Phase 10.
