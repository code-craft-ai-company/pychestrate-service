# 0-system-health — Design

## Architecture

System health lives as a `HealthRegistry` + `HealthScheduler` pair attached
to the web app host. The registry holds probe records; the scheduler
runs them on a dedicated thread pool at their declared cadence and caches
the latest `ProbeResult`. The three endpoints (`/__health/live`,
`/__health/ready`, `/__health/detailed`) serve from the cache — they
never invoke a probe synchronously, which is what keeps p99 latency flat
regardless of probe slowness. The registry is authoritative for the
current set of registered probes; the scheduler is authoritative for the
latest `ProbeResult` per probe. Other features (persistence, bus, object
store, timeseries) register themselves as probes during their startup
hooks; extensions register via the `SystemHealthProbeExtension` resource
surface which is discovered by `E-resource-extensions` at Phase 0.5 and
beyond.

## Data Model

No persistent state. In-memory:

- `probes: dict[str, ProbeRecord]`
- `ProbeRecord`:
  - `name: str`
  - `kind: ProbeKind` (`liveness` | `readiness` | `informational`)
  - `probe: Callable[[], ProbeResult]`
  - `interval_seconds: float`
  - `timeout_seconds: float`
  - `last_result: ProbeResult | None`
  - `last_started_at: datetime | None`
  - `in_flight: bool`
- `ProbeResult`:
  - `status: Literal["ok", "fail", "unknown"]`
  - `duration_ms: float`
  - `observed_at: datetime`
  - `last_error: str | None` (truncated at 512 chars)
  - `details: dict[str, Any]` (probe-provided, informational only)
- `overall_status: Literal["ok", "degraded", "failing"]` — recomputed
  after every probe result; published on change.

## Interfaces

### Public API

HTTP:

- `GET /__health/live` — unauthenticated, 200 when process is running.
  Body: `{"status": "live", "service_version": "<semver>"}`.
- `GET /__health/ready` — unauthenticated, 200 if all `readiness` probes
  are `ok`, else 503. Body when 503:
  `{"status": "not_ready", "failing": ["probe_name", ...]}`.
- `GET /__health/detailed` — auth-gated by
  `pychestrate.system_health.detailed`. Body: overall + per-probe.

### Internal API

```python
class HealthRegistry:
    def __init__(self) -> None:
        self._probes: dict[str, ProbeRecord] = {}
        return

    def register_probe(
        self,
        name: str,
        kind: ProbeKind,
        probe: Callable[[], ProbeResult],
        interval_seconds: float,
        timeout_seconds: float
    ) -> None:
        """
            Register a probe.

            :param name: Unique probe name.
            :param kind: liveness | readiness | informational.
            :param probe: Zero-arg callable returning ProbeResult.
            :param interval_seconds: Run cadence.
            :param timeout_seconds: Per-run timeout.

            :returns: None
            :raises: SemanticError on duplicate name.
        """
        ...

    def unregister_probe(
        self,
        name: str
    ) -> None:
        """
            Remove a probe. Idempotent.

            :param name: Probe name.

            :returns: None
            :raises: None
        """
        ...

    def snapshot(self) -> HealthSnapshot:
        """
            Build an immutable snapshot for endpoint serialization.

            :returns: HealthSnapshot with overall + per-probe details.
            :raises: None
        """
        ...


class HealthScheduler:
    def __init__(
        self,
        registry: HealthRegistry,
        config: HealthConfig
    ) -> None:
        self._registry = registry
        self._config = config
        self._running: bool = False
        return

    def start(self) -> None:
        """
            Start the scheduler threads.

            :returns: None
            :raises: SemanticError if already running.
        """
        ...

    def stop(
        self,
        timeout_seconds: float
    ) -> None:
        """
            Stop the scheduler and wait for in-flight probes.

            :param timeout_seconds: Wait budget.

            :returns: None
            :raises: None
        """
        ...


def initialize_system_health(
    app: WebApplication,
    config: HealthConfig
) -> SystemHealth:
    """
        Wire the health registry, scheduler, and endpoints.

        :param app: The web application.
        :param config: Health config.

        :returns: A SystemHealth handle owning registry + scheduler.
        :raises: ConfigurationError
    """
    ...
```

### Extension Surface

Resource extension:

```python
class SystemHealthProbeExtension(ResourceExtension):
    """
        Base class for probe contributions shipped by extensions.

        Subclasses declare:
          - name: class attribute (unique)
          - kind: class attribute (ProbeKind)
          - interval_seconds: class attribute (float)
          - timeout_seconds: class attribute (float)

        Subclasses override `run_probe()` to return a ProbeResult.
    """
    name: str
    kind: ProbeKind
    interval_seconds: float
    timeout_seconds: float

    @classmethod
    def run_probe(cls) -> ProbeResult:
        """
            Execute one probe run.

            :returns: ProbeResult capturing status + details.
            :raises: Any exception (captured by scheduler).
        """
        ...
```

Reference implementations shipped in-tree (under
`source/site/ccai/extensions/pychestrate/system_health/`):

- `PostgresHealthProbe` — liveness `ok` if `SELECT 1` succeeds within
  `timeout_seconds`.
- `MessageBusHealthProbe` — readiness `ok` if the bus accepts a
  round-trip publish/subscribe for a canary topic.
- `ObjectStoreHealthProbe` — readiness `ok` if the active driver's
  `health()` reports `healthy`.
- `TimeseriesHealthProbe` — informational, reports driver health +
  buffer depth.
- `DiskSpaceHealthProbe` — readiness `fail` if log / working directory
  usage > 90%.

### Events Emitted

On `0-message-bus`:

- `system_health.overall.changed` — `{from: str, to: str,
  failing_probes: list[str]}`
- `system_health.probe.failed` — `{probe: str, kind: str, error: str}`
- `system_health.probe.recovered` — `{probe: str, kind: str}`

### Events Consumed

None in Phase 0. In later phases, `extension.reloaded` re-scans
probe extensions.

## Component Breakdown

All paths rooted at `source/site/ccai/pychestrate/webservice/`:

- `system_health/__init__.py`
- `system_health/config.py` — `HealthConfig` (probe worker count,
  detailed-endpoint permission name).
- `system_health/registry.py` — `HealthRegistry`, `ProbeRecord`,
  `ProbeKind`, `ProbeResult`, `HealthSnapshot`.
- `system_health/scheduler.py` — dedicated thread pool, cadence scheduling,
  timeout enforcement.
- `system_health/endpoints.py` — live / ready / detailed HTTP handlers.
- `system_health/aggregator.py` — overall-status recompute, change
  detection, event emit.
- `system_health/extension_base.py` — `SystemHealthProbeExtension`.
- `system_health/hooks.py` — startup/shutdown hooks; takes ownership of
  the endpoints from `0-web-app-host`.

Probe reference implementations under
`source/site/ccai/extensions/pychestrate/system_health/`.

## Key Flows

### Flow 1 — Probe evaluation

1. Scheduler wakes at the next due probe.
2. Marks `in_flight = True`; submits to the thread pool with a
   `timeout_seconds` future.
3. On completion, updates `last_result`, `last_started_at`.
4. On timeout, records `ProbeResult(status="fail", last_error="probe
   timeout")`.
5. On exception, records `ProbeResult(status="fail",
   last_error=truncated(str(exc), 512))`.
6. Aggregator recomputes `overall_status`; on change, publishes
   `system_health.overall.changed`.
7. Scheduler updates metrics (`probe_duration_seconds`, `probe_up`,
   `probe_failures_total`).

### Flow 2 — `/__health/ready` request

1. Middleware routes request to `ReadinessHandler`.
2. Handler consults cached `HealthSnapshot` from registry.
3. If service is `starting` → 503 `{"status": "starting"}`.
4. Else if any `readiness` probe is not `ok` → 503 with list of failing
   probes.
5. Else → 200 `{"status": "ready"}`.

### Flow 3 — Handover from scaffold endpoints

1. `0-web-app-host` registers `/__health/live` and `/__health/startup`
   stubs in Phase 0.
2. `0-system-health` startup hook priority `50` unregisters the stubs
   and registers its own handlers under the same paths plus
   `/__health/ready` and `/__health/detailed`.
3. Behavior of `/__health/live` is preserved byte-for-byte; the
   `/__health/startup` stub is aliased to `/__health/ready`.

## Error Handling

- Probe exceptions: caught ONCE by the scheduler, converted to
  `ProbeResult(status="fail", last_error=...)`. No re-raise — probes do
  not crash the service.
- Scheduler thread crash: the supervisor restarts the scheduler thread
  and emits `system_health.scheduler.crashed`.
- `SemanticError` on duplicate probe name: bubbles.
- `ConfigurationError` on bad `HealthConfig`: bubbles to host (exit 78).

Multiline error example:

```python
err_msg_lines = ["Duplicate health probe registration rejected."]
err_msg_lines.append("PROBE NAME: {}".format(name))
err_msg_lines.append("EXISTING KIND: {}".format(existing.kind))
err_msg_lines.append("NEW KIND: {}".format(kind))

err_msg = os.linesep.join(err_msg_lines)
raise SemanticError(err_msg) from None
```

## Security Considerations

- `/__health/live` and `/__health/ready` bypass auth so orchestrators
  can probe before auth is ready — responses carry no secrets.
- `/__health/detailed` requires permission
  `pychestrate.system_health.detailed`; `last_error` truncated at 512
  chars to bound leakage.
- `details: dict[str, Any]` from a probe is serialized verbatim — probe
  authors are responsible for not including secrets there. A lint rule
  flags probe implementations that reference `secrets_*` modules.
- No rate limiting on `/__health/live` (must be cheap); `/__health/ready`
  and `/__health/detailed` inherit the default request-level rate
  limiter from Layer 0.

## Observability

Metrics:

- `pychestrate_system_health_probe_duration_seconds{probe,kind}` — histogram
- `pychestrate_system_health_probe_failures_total{probe}` — counter
- `pychestrate_system_health_probe_up{probe,kind}` — gauge (0|1)
- `pychestrate_system_health_overall_status` — gauge (0=failing,
  1=degraded, 2=ok)
- `pychestrate_system_health_scheduler_backlog{probe}` — gauge

Log events:

- `pychestrate.system_health.probe.failed`
- `pychestrate.system_health.probe.recovered`
- `pychestrate.system_health.overall.changed`
- `pychestrate.system_health.scheduler.backlog`
- `pychestrate.system_health.scheduler.crashed`

Trace spans:

- `pychestrate.system_health.probe.run` — attributes `probe`, `kind`,
  `status`, `duration_ms`

Dashboards: system health tile under `9-admin-ui`; overall-status
gauge on the NOC board in `7-orchestration-metrics`.

## Open Questions

- Do we expose a `/__health/tap` streaming endpoint for operators
  watching probe transitions live, or keep that to logs? Timebox:
  Phase 10.
- Do we allow an extension to declare a project-scoped probe whose
  failure affects only that project's readiness (not service global)?
  Timebox: `0-maintenance-mode` start.
- Whether to cache responses at the response-header level (ETag + 304)
  for probing orchestrators — depends on real probe volume.
  Timebox: Phase 3 exit.
