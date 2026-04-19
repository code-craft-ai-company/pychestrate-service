# 4-resource-health — Design

## Architecture

Resource health runs a per-kind scheduler loop that dispatches probe jobs
against candidates, aggregates outcomes, and drives state transitions on
the inventory. The authoritative state lives in two places:
`core.resources.state` (owned by `4-resource-inventory`) and
`core.resource_health` (owned by this feature — per-resource probe
counters, last error, last-good, backoff). Probe *selection* is an
`E-factory-protocols` lookup keyed by `kind_name`; probe *execution*
runs on a bounded worker pool (16 workers default) with per-probe soft
timeouts. State transitions go through the inventory's
`transition_resource_state` API so emissions and audit hooks stay
centralized. Probes never themselves emit `entity.resource.*` events;
the health service does. When a probed resource is currently under an
active reservation, quarantine is *deferred* — recorded in
`core.resource_health.deferred_quarantine` and applied on release.
Ships in Phase 4.

## Data Model

Schema `core`:

- `core.resource_health`
  - `resource_id: UUID` — PK, FK → `core.resources`
  - `probe_name: str` — bound probe, from kind default or override
  - `consecutive_failures: int` — reset on pass
  - `consecutive_successes: int` — used for heal threshold
  - `last_good_at: datetime | None`
  - `last_probe_at: datetime | None`
  - `last_error: str | None` — truncated 1 KB
  - `deferred_quarantine: bool`
  - `next_probe_at: datetime` — backoff-aware scheduling clock
  - `version: int`

Indices:

- PK on `resource_id`.
- INDEX `(next_probe_at, probe_name)` — scheduler tick query.
- Partial INDEX `(deferred_quarantine) WHERE deferred_quarantine = TRUE`
  for on-release drains.

## Interfaces

### Public API

REST under `/api/v1/resources/{resource_id}/health`:

- `GET /api/v1/resources/{resource_id}/health` — returns probe name,
  `last_good_at`, `consecutive_failures`, `last_error`, `next_probe_at`.
- `POST /api/v1/resources/{resource_id}/health:probe-now` — force an
  out-of-cadence probe; requires `resource.health.probe_now`.

### Internal API

```python
def schedule_probe_tick(
    tick_ts: datetime,
    batch_size: int
) -> int:
    """
        Find resources whose next_probe_at <= tick_ts, dispatch probes,
        and record outcomes.

        :param tick_ts: The current wall-clock tick.
        :param batch_size: Max probes per tick.

        :returns: Number of probes dispatched.
    """
    ...


def record_probe_outcome(
    resource_id: UUID,
    probe_name: str,
    outcome: ProbeOutcome,
    probe_completed_at: datetime,
    duration_ms: float,
    error: str | None
) -> None:
    """
        Persist the outcome and drive the quarantine/heal state machine.

        :param resource_id: The probed resource id.
        :param probe_name: The probe that ran.
        :param outcome: pass | fail | timeout.
        :param probe_completed_at: Completion wall clock.
        :param duration_ms: Probe duration.
        :param error: Truncated error string on fail/timeout; None on pass.
    """
    ...


def on_reservation_released(
    resource_id: UUID
) -> None:
    """
        Bus subscriber: drain deferred_quarantine for a just-released
        resource.

        :param resource_id: The resource whose reservation just released.
    """
    ...


def force_probe_now(
    resource_id: UUID,
    actor: UUID
) -> ProbeOutcome:
    """
        Dispatch a probe inline and return its outcome.

        :param resource_id: The resource id.
        :param actor: The caller; must hold resource.health.probe_now.

        :returns: The probe outcome.
    """
    ...
```

### Extension Surface

Factory protocol:

```python
class ResourceHealthProbeProtocol(FactoryProtocolBase):
    """
        factory_protocol_name = "resource_health_probe"
        Keyed per kind: the registry index uses (protocol_name, kind_name).
    """
    kind_name: str
    probe_name: str
    probe_period_seconds: int
    probe_timeout_seconds: int

    @classmethod
    def run(
        cls,
        resource: Resource,
        aspects: ProbeAspects
    ) -> ProbeResult:
        """
            Execute the probe once.

            :param resource: The resource being probed.
            :param aspects: Behaviour bundle (credentials handle, bandwidth
                            budget, cancellation token).

            :returns: ProbeResult.pass_() | .fail(error=..) | .timeout().
        """
        ...
```

In-tree implementations under
`source/site/automojo/factories/pychestrate/resource_health_probe/`:

- `DevicePingProbe` — ICMP echo; `kind_name="device"`, PRECEDENCE 1000.
- `DeviceTCPProbe` — TCP connect check; `kind_name="device"`, PRECEDENCE
  1100.
- `DeviceSSHProbe` — SSH banner check; `kind_name="device"`, PRECEDENCE
  1200.
- `SubnetDhcpProbe` — DHCP test lease; `kind_name="ip_subnet"`,
  PRECEDENCE 1000.
- `IpAddressReachabilityProbe` — ARP + ICMP; `kind_name="ip_address"`,
  PRECEDENCE 1000.
- `LicenseSeatCountProbe` — vendor REST call; `kind_name="license"`,
  PRECEDENCE 1000.

Test-only `AlwaysFailProbe` and `AlwaysPassProbe` shipped under `tests/`
for extension-point coverage.

### Events Emitted

Via `4-resource-inventory.transition_resource_state`:

- `entity.resource.quarantined`
- `entity.resource.healed`

Directly:

- `pychestrate.resource.health.probe_failed`
- `pychestrate.resource.health.probe_timeout`
- `pychestrate.resource.health.quarantine_deferred`
- `pychestrate.resource.health.no_probe_for_kind`
- `pychestrate.resource.health.backoff_applied`

### Events Consumed

- `entity.reservation.released` — triggers drain of
  `deferred_quarantine`.
- `entity.resource.registered` — seeds a `core.resource_health` row.
- `entity.resource.retired` — removes the `core.resource_health` row.
- `extension.reloaded` — rebuild per-kind probe bindings.

## Component Breakdown

Under `source/site/automojo/pychestrate/webservice/resources/health/`:

- `models.py` — `ResourceHealthRow`, `ProbeOutcome`, `ProbeResult`,
  `ProbeAspects`.
- `repository.py` — CRUD on `core.resource_health`; scheduler query.
- `probe_registry.py` — factory lookup keyed by `(protocol_name,
  kind_name)`, PRECEDENCE sort.
- `scheduler.py` — tick loop dispatching on a 16-worker pool.
- `outcome_processor.py` — translates outcomes into state-machine
  transitions.
- `service.py` — `record_probe_outcome`, `force_probe_now`.
- `subscribers.py` — bus subscriptions.
- `api.py` — `/api/v1/resources/{id}/health` REST.
- `errors.py` — `ProbeNotFoundError`, `ProbeTimeoutError`.

Probes at `source/site/automojo/factories/pychestrate/resource_health_probe/`.

## Key Flows

### Flow 1 — Scheduled probe tick

1. Every 1s the scheduler calls `schedule_probe_tick(now,
   batch_size=200)`.
2. Query: `SELECT resource_id, probe_name FROM core.resource_health
   WHERE next_probe_at <= now ORDER BY next_probe_at LIMIT 200 FOR
   UPDATE SKIP LOCKED`.
3. For each row, submit to the worker pool; each worker calls
   `probe.run(resource, aspects)` under a `probe_timeout_seconds` async
   cancellation.
4. On result: call `record_probe_outcome(...)`.

### Flow 2 — Pass outcome

1. `record_probe_outcome` with `ProbeOutcome.pass_()`:
   - `consecutive_failures = 0`; `consecutive_successes += 1`;
     `last_good_at = probe_completed_at`; `last_error = NULL`.
   - `next_probe_at = now + probe_period_seconds`.
2. If the resource was `quarantined` AND
   `consecutive_successes >= heal_threshold_consecutive`: call
   `inventory.transition_resource_state(resource_id,
   ResourceState.AVAILABLE, reason="probe healed: {probe_name}")`.

### Flow 3 — Fail outcome with active reservation

1. `record_probe_outcome` with `.fail(error=...)`:
   - `consecutive_failures += 1`; `consecutive_successes = 0`;
     `last_error = truncate(error, 1024)`.
   - `next_probe_at = now + probe_period_seconds *
     min(2^consecutive_failures, 16)` — exponential backoff.
2. If `consecutive_failures >= quarantine_threshold_consecutive`:
   - If the resource has NO active granted reservation: call
     `inventory.transition_resource_state(resource_id,
     ResourceState.QUARANTINED, ...)`.
   - If the resource IS under an active reservation: set
     `deferred_quarantine = TRUE`; emit
     `pychestrate.resource.health.quarantine_deferred`.

### Flow 4 — Deferred quarantine drain on release

1. `entity.reservation.released` fires with `resource_id=R`.
2. `on_reservation_released(R)` loads the `core.resource_health` row.
3. If `deferred_quarantine == TRUE`: call
   `inventory.transition_resource_state(R, ResourceState.QUARANTINED,
   ...)`, clear the flag, emit `entity.resource.quarantined`.

## Error Handling

- Probe exceptions caught inside the worker and translated to
  `ProbeResult.fail(error=str(exc))`; never propagate.
- `ProbeTimeoutError` translates to `ProbeResult.timeout()` and is
  counted separately in metrics.
- `SemanticError` (e.g. record_probe_outcome for a retired resource)
  bubbles.
- `ConfigurationError` raised at startup if two probe implementations
  share `(kind_name, probe_name)` and one is not an override of the
  other — blocks service start.
- Multiline errors via `os.linesep.join([...])`.

## Security Considerations

- Probes run under their granted `E-extension-sandbox` capabilities
  (Phase 8). In-tree device probes require `net:outbound`; license
  probes require `net:outbound` + `read:secrets`.
- Probe credentials (SSH keys, vendor tokens) come from
  `1-secrets-vault` via the kind's declared sensitive attrs — no
  cleartext in probe code.
- REST `probe-now` gated by `resource.health.probe_now`; audited.
- Backoff prevents storms: even if a third-party extension probes
  aggressively, consecutive failures back off to at most
  `probe_period_seconds * 16`.

## Observability

Metrics:

- `pychestrate_resource_probe_runs_total{kind,probe,outcome}` — counter
- `pychestrate_resource_probe_duration_seconds{kind,probe}` — histogram
- `pychestrate_resource_probe_timeout_total{kind,probe}` — counter
- `pychestrate_resource_quarantine_duration_seconds{kind}` — histogram (on heal)
- `pychestrate_resource_consecutive_failures{kind}` — gauge (sampled)
- `pychestrate_resource_health_last_good_age_seconds{kind}` — gauge
- `pychestrate_resource_health_deferred_quarantine_count` — gauge

Log events:

- `pychestrate.resource.health.probe_failed`
- `pychestrate.resource.health.probe_timeout`
- `pychestrate.resource.health.quarantine_deferred`
- `pychestrate.resource.health.no_probe_for_kind`
- `pychestrate.resource.health.backoff_applied`

Trace spans:

- `pychestrate.resource.health.probe` — `kind`, `probe`, `resource_id`,
  `outcome`, `duration_ms`.
- `pychestrate.resource.health.tick` — `dispatched`, `queued`.

Dashboards: "Resource Health" panel on `7-resource-metrics` — per-kind
pass rate, median duration, quarantine age, deferred count.

## Open Questions

- Should the probe registry allow *multiple* probes bound to one kind
  and gate healing on *all* passing? Current plan: single probe per
  `(kind_name, probe_name)`; composite is a policy problem for Phase 5.
- Backoff ceiling of 16× feels right for 60 s probes (up to 16 min) but
  tight for 900 s licenses (up to 4 h). Make ceiling per-kind. Timebox:
  Phase 4 hardening.
- Do we probe quarantined resources at the same cadence, or at a
  reduced cadence? Current plan: same cadence (so heal-watch is quick)
  with backoff applied on continued failures.
