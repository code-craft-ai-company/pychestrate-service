# 6-drift-detection — Design

## Architecture

`6-drift-detection` maintains per-environment drift schedules, fires
cron ticks that build read-only Layer 5 envelopes for the configured
`drift_checker`, and persists the ingested reports. It never performs
remediation directly — drift → notification → operator-gated apply
through `6-infra-orchestration`. Ships in Phase 7. Authoritative source
of truth for the *declared* state is the infra tool's backend; this
feature owns the drift diff + schedule + run history.

## Data Model

Tables in `0-persistence`:

- `drift_schedule`:
  - `(project_id, environment_id) PK`
  - `checker_name: str`
  - `cron_expression: str`
  - `enabled: bool`
  - `updated_by: UUID`
  - `updated_at: datetime`
- `drift_run`:
  - `run_id: UUID` PK
  - `project_id: UUID`
  - `environment_id: UUID`
  - `checker_name: str`
  - `layer5_run_id: UUID`
  - `state: DriftRunState` — `{pending, running, completed, failed, ingest_failed, skipped}`
  - `trigger_kind: str` — `schedule | manual`
  - `scheduled_for: datetime`
  - `ran_at: datetime | None`
  - `drift_count: int | None`
  - `added, changed, destroyed: int | None`
  - `diff_digest_sha256: bytes(32) | None`
  - `report_blob_key: str | None`
- `drift_tick_ledger`:
  - `(project_id, environment_id, scheduled_for) PK` — ensures exactly-once dispatch per tick.

Indices: `(environment_id, scheduled_for DESC)`, `(state)`.

## Interfaces

### Public API

REST under `8-rest-api-v1`:

- `PUT /api/v1/projects/{project_id}/environments/{env_id}/drift-schedule` body `{checker_name, cron_expression, enabled}`.
- `POST /api/v1/projects/{project_id}/environments/{env_id}/drift-runs:run-now` body `{reason}`.
- `GET /api/v1/projects/{project_id}/environments/{env_id}/drift-runs?limit=&cursor=`.
- `GET /api/v1/projects/{project_id}/drift-runs/{run_id}` → full report blob stream.

### Internal API

```python
class DriftDetection:
    def __init__(
        self,
        repo: DriftRepository,
        env_registry: EnvironmentRegistry,
        dispatcher: JobDispatcher,
        envelope_builder: JobEnvelopeBuilder,
        shared_results: SharedResultsBackend,
        checker_registry: DriftCheckerRegistry,
        rbac: RbacService,
        audit: AuditLog,
        bus: MessageBus,
        clock: Clock,
        config: DriftConfig
    ) -> None:
        self._repo = repo
        self._env_registry = env_registry
        self._dispatcher = dispatcher
        self._envelope_builder = envelope_builder
        self._shared_results = shared_results
        self._checker_registry = checker_registry
        self._rbac = rbac
        self._audit = audit
        self._bus = bus
        self._clock = clock
        self._config = config
        return

    def set_schedule(
        self,
        actor_id: UUID,
        project_id: UUID,
        environment_id: UUID,
        checker_name: str,
        cron_expression: str,
        enabled: bool
    ) -> None:
        """
            :raises: AuthorizationError, SemanticError, ConfigurationError
        """
        ...

    def run_now(
        self,
        actor_id: UUID,
        project_id: UUID,
        environment_id: UUID,
        reason: str
    ) -> DriftRunView:
        """
            :raises: AuthorizationError, ConfigurationError, CapabilityMismatchError
        """
        ...

    def tick(
        self,
        environment_id: UUID,
        scheduled_for: datetime
    ) -> DriftRunView | None:
        """
            Called by the scheduler for a single cron tick.

            :returns: DriftRunView, or None if skipped.
            :raises: None (internal)
        """
        ...

    def apply_layer5_state_event(
        self,
        layer5_run_id: UUID,
        event: RunStateEvent
    ) -> None:
        """
            Mirror Layer 5 state onto DriftRun; on terminal ingest the report.
        """
        ...
```

### Extension Surface

Factory protocol declared here:

```python
class DriftCheckerProtocol(FactoryProtocolBase):
    factory_protocol_name: str = "drift_checker"

    @classmethod
    def checker_name(cls) -> str: ...

    @classmethod
    def build_job_envelope(
        cls,
        run_id: UUID,
        project_id: UUID,
        environment_id: UUID,
        env_attrs: dict[str, object],
        result_root_key: str
    ) -> JobEnvelope: ...

    @classmethod
    def parse_report(cls, report_bytes: bytes) -> DriftReport: ...

    @classmethod
    def compute_diff_digest(cls, report: DriftReport) -> bytes: ...

    @classmethod
    def capability_requirements(cls) -> list[str]: ...

    @classmethod
    def report_format_tag(cls) -> str: ...
```

Reference implementations under
`source/site/ccai/factories/pychestrate/drift_checker/`:

- `TerraformDriftChecker` — `PRECEDENCE = 500`; calls `terraform plan -refresh-only -detailed-exitcode`.
- `PulumiDriftChecker` — `PRECEDENCE = 500`; calls `pulumi preview --diff`.
- `AnsibleDriftChecker` — `PRECEDENCE = 500`; check-mode playbook with changed-task detection.

### Events Emitted

- `entity.env.drift.scheduled` — `{environment_id, checker_name, scheduled_for}`
- `entity.env.drift.dispatched` — `{environment_id, drift_run_id, layer5_run_id}`
- `entity.env.drift.completed` — `{environment_id, drift_run_id, drift_count, diff_digest}`
- `entity.env.drift_detected` — `{environment_id, previous_digest, current_digest, drift_count}` (when digest changes)
- `entity.env.drift.manual_triggered` — `{environment_id, actor_id, reason}`

### Events Consumed

- `entity.env.declared|archived|destroyed` — create/stop schedules.
- `entity.run.state_changed|completed|failed|cancelled` — mirror.
- `extension.reloaded` — refresh checker registry.

## Component Breakdown

All paths rooted at `source/site/ccai/pychestrate/webservice/orchestration/infra/drift/`:

- `__init__.py`
- `service.py` — `DriftDetection`.
- `repository.py` — `DriftRepository`.
- `scheduler.py` — cron evaluator + exactly-once tick via `drift_tick_ledger`.
- `ingest.py` — report-blob persistence and digest computation on terminal.
- `checker_protocol.py` — `DriftCheckerProtocol`.
- `checker_registry.py`.
- `aspects.py` — `RunNowAspects`.
- `errors.py` — `CapabilityMismatchError`.
- `rest/v1_routes.py`.

Factories under `source/site/ccai/factories/pychestrate/drift_checker/`.

## Key Flows

### Flow 1 — Scheduled tick

1. `scheduler.py` fires at the cron tick.
2. `tick(env_id, scheduled_for)` attempts an exactly-once insert into `drift_tick_ledger`; duplicate → skip.
3. Env attrs loaded via `EnvironmentRegistry`; checker resolved.
4. Capability check against any available pod with the advertised capability; miss → WARNING + `skipped`.
5. `result_root` allocated; envelope built; dispatched via `JobDispatcher`.
6. `drift_run` row created; `entity.env.drift.dispatched` emitted.

### Flow 2 — Terminal ingest

1. Layer 5 state change mirror updates `drift_run`.
2. On terminal success, `ingest.py` reads the result tree; `parse_report(...)` yields a `DriftReport`.
3. `compute_diff_digest(report)` produces `diff_digest_sha256`.
4. Report blob written to `0-object-store` under `report_blob_key`.
5. If digest changed vs the last report for `(env_id, checker_name)`, emit `entity.env.drift_detected`.
6. Emit `entity.env.drift.completed`.

### Flow 3 — Run now

1. REST `:run-now` → `run_now(...)`.
2. RBAC `drift.run`; audit row; ad-hoc dispatch with `trigger_kind = manual`.

## Error Handling

- `SemanticError`: invalid cron, unknown checker, unknown env → bubble.
- `AuthorizationError`: 403.
- `ConfigurationError`: checker contract breakage → bubble to host.
- `CapabilityMismatchError`: WARNING on scheduled; 409 on manual.
- Ingest failures mark the run `ingest_failed` and retry via bounded backoff; emitted as `pychestrate.infra.drift.ingest_failed` log.
- Multiline errors via `os.linesep.join([...])`.

## Security Considerations

- Checker credentials scoped per-env under `secrets/env/<id>/drift/*`.
- Drift jobs use read-only credentials enforced by the driver; guard against accidental mutation by rejecting checkers whose capability advertises `may_mutate: True`.
- Manual `run_now` rate-limited per env (default 12/hour).

## Observability

Metrics:

- `pychestrate_infra_drift_runs_total{project,env,checker,outcome}` — counter
- `pychestrate_infra_drift_run_duration_seconds{project,checker}` — histogram
- `pychestrate_infra_drift_changes_total{project,env,kind}` — counter
- `pychestrate_infra_drift_skipped_total{project,env,reason}` — counter
- `pychestrate_infra_drift_ingest_failures_total{project,env}` — counter

Log events: `pychestrate.infra.drift.scheduled`, `pychestrate.infra.drift.dispatched`, `pychestrate.infra.drift.completed`, `pychestrate.infra.drift.detected`, `pychestrate.infra.drift.manual_triggered`, `pychestrate.infra.drift.capability_mismatch`, `pychestrate.infra.drift.ingest_failed`.

Trace spans: `pychestrate.infra.drift.schedule_tick`, `pychestrate.infra.drift.dispatch`, `pychestrate.infra.drift.persist_report`.

## Open Questions

- Scheduler horizontal scaling — distributed cron or sticky-singleton? Timebox: Phase 7 midpoint.
- Should drift notifications fan out per-resource (count-delta) or per-run (summary)? Timebox: Phase 7 exit.
- Report compression on object store — gzip vs zstd. Timebox: Phase 7 midpoint.
