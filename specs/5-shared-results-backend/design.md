# 5-shared-results-backend — Design

## Architecture

This feature is a thin service that mints and lifecycle-manages
per-run prefixes on the object store. It owns one table and one
small API; it delegates every byte-level operation to
`0-object-store`. It lives at
`source/site/ccai/pychestrate/webservice/jobs/results/`. There
are no factory or resource extension points declared here — the only
pluggable aspect, the object-store driver, is owned by
`0-object-store` and reused unmodified. This feature lands in
**Phase 3** alongside the rest of Layer 5's minimum-viable run
surface and is the thin seam that prevents `5-job-envelope` from
having to know about storage layout.

## Data Model

Owned row:

- `shared_results_allocation`:
  - `allocation_id: UUID` (PK, UUIDv7)
  - `run_id: UUID` (FK → `run.run_id`, unique)
  - `project_id: UUID` (FK, indexed)
  - `backend_driver: str`
  - `backend_key_prefix: str`
  - `allocated_at: timestamptz`
  - `landed_at: timestamptz | None`
  - `released_at: timestamptz | None`
  - `hard_deadline_at: timestamptz`
  - `status: AllocationStatus`
  - Indices: `(run_id)` (unique), `(status,
    hard_deadline_at)` for sweep, `(project_id, status)` for
    admin listings.

In-memory state:

- `_timer_wheel: TimerWheel` — fires `prefix_timed_out` for
  pending allocations past deadline.

Enums:

- `AllocationStatus`: `pending | landed | timed_out | released`.

Value types:

- `Allocation`:
  - `run_id: UUID`
  - `backend_driver: str`
  - `backend_key_prefix: str`
  - `hard_deadline_at: datetime`
  - `status: AllocationStatus`
- `PresignedPutGrant`:
  - `url: str`
  - `expires_at: datetime`

## Interfaces

### Public API

N/A at the HTTP surface. The client receives
`backend_key_prefix` and `backend_driver` inside the signed
envelope; it uses its own object-store credentials to write.

### Internal API

```python
class SharedResultsBackend:
    def __init__(
        self,
        repository: AllocationRepository,
        object_store: ObjectStore,
        project_lookup: ProjectLookup,
        maintenance_gate: MaintenanceGate,
        timer_wheel: TimerWheel,
        bus: MessageBus,
        clock: Clock,
        config: SharedResultsConfig
    ) -> None:
        self._repository = repository
        self._object_store = object_store
        self._project_lookup = project_lookup
        self._maintenance_gate = maintenance_gate
        self._timer_wheel = timer_wheel
        self._bus = bus
        self._clock = clock
        self._config = config
        return

    def allocate(
        self,
        run_id: UUID,
        project_id: UUID,
        job_type: str,
        hard_deadline_at: datetime | None = None
    ) -> Allocation:
        """
            Allocate a prefix for a run, idempotent on run_id.

            :param run_id: Service run id.
            :param project_id: Project id (for slug resolution).
            :param job_type: Declared job type.
            :param hard_deadline_at: Optional deadline; defaults
                                     to now + 24 h.

            :returns: The persisted allocation.
            :raises: MaintenanceModeError, SemanticError
        """
        ...

    def mark_landed(
        self,
        run_id: UUID
    ) -> Allocation:
        """
            Mark the allocation landed and cancel its deadline
            timer. Called from the entity.result_tree.landed
            subscription.

            :param run_id: Service run id.

            :returns: Updated allocation.
            :raises: AllocationNotFoundError
        """
        ...

    def release(
        self,
        run_id: UUID
    ) -> Allocation:
        """
            Mark the allocation released; retention purges on its
            schedule.

            :param run_id: Service run id.

            :returns: Updated allocation.
            :raises: AllocationNotFoundError
        """
        ...

    def presign_put(
        self,
        run_id: UUID,
        relative_path: str,
        aspects: PresignAspects | None = None
    ) -> PresignedPutGrant:
        """
            Build a presigned put URL scoped to
            <backend_key_prefix>/<relative_path>.

            :param run_id: Service run id.
            :param relative_path: Sub-path under the allocation.
            :param aspects: Behavior parameters (ttl, metadata).

            :returns: PresignedPutGrant.
            :raises: UnsupportedOperationError,
                     AllocationNotFoundError, SemanticError
        """
        ...

    def resolve(
        self,
        run_id: UUID
    ) -> Allocation:
        """
            Fetch an allocation by run id.

            :param run_id: Service run id.

            :returns: Allocation.
            :raises: AllocationNotFoundError
        """
        ...
```

### Extension Surface

None. This feature reuses `object_store_driver` (from
`0-object-store`) and `retention_action` (from
`2-retention-policies`).

### Events Emitted

On `0-message-bus`:

- `pychestrate.shared_results.allocated` — `{run_id, project_id,
  driver, backend_key_prefix, allocated_at}`
- `pychestrate.shared_results.landed` — `{run_id, project_id,
  landed_at}`
- `pychestrate.shared_results.prefix_timed_out` — `{run_id,
  project_id, hard_deadline_at}`
- `pychestrate.shared_results.released` — `{run_id, project_id,
  released_at}`

### Events Consumed

- `entity.result_tree.landed` (from `5-result-ingest-watcher`) →
  `mark_landed`.
- `maintenance.mode.changed` (from `0-maintenance-mode`) →
  updates `_maintenance_gate`.

## Component Breakdown

All paths rooted at `source/site/ccai/pychestrate/webservice/`:

- `jobs/results/__init__.py`
- `jobs/results/backend.py` — `SharedResultsBackend` facade.
- `jobs/results/repository.py` — `AllocationRepository` CRUD.
- `jobs/results/path_builder.py` — deterministic prefix
  construction with sanitization.
- `jobs/results/errors.py` — `AllocationNotFoundError`.
- `jobs/results/schema.py` — `Allocation`, `PresignedPutGrant`,
  `SharedResultsConfig`.
- `jobs/results/hooks.py` — startup hook that subscribes to
  `entity.result_tree.landed` and arms pending timers from DB.

## Key Flows

### Flow 1 — Allocation at Dispatch Time

1. `5-job-dispatch` calls
   `shared_backend.allocate(run_id, project_id, job_type,
   hard_deadline_at)`.
2. Backend resolves `project_slug` via `project_lookup`.
3. `path_builder.build(project_slug, job_type, run_id,
   allocated_at)` produces
   `"<project_slug>/results/<yyyy>/<mm>/<dd>/<job_type>/<run_id>"`.
4. `repository.upsert(run_id, ..., ON CONFLICT DO NOTHING
   RETURNING *)` persists or returns the existing row.
5. Timer wheel is armed for `hard_deadline_at`.
6. `pychestrate.shared_results.allocated` published.
7. `5-job-envelope` reads the allocation and injects into
   `envelope.results`.

### Flow 2 — Landing Cancels Timer

1. `5-result-ingest-watcher` emits
   `entity.result_tree.landed` after a scan completes.
2. Subscription handler calls `mark_landed(run_id)`.
3. Repository UPDATE sets `status='landed'`, `landed_at=now`.
4. Timer wheel cancels the deadline for the allocation.
5. `pychestrate.shared_results.landed` published.

### Flow 3 — Timeout

1. Timer fires for an allocation that never landed.
2. Repository UPDATE sets `status='timed_out'`.
3. `pychestrate.shared_results.prefix_timed_out` published.
4. `5-run-state-machine` subscribes; transitions the run to
   `failed` if not already terminal (via `failure_observed`
   event) with reason `"result_tree_missing"`.
5. `2-retention-policies` sweeps the prefix on its schedule using
   the driver's (to-be-added) `delete_prefix` API.

## Error Handling

- `MaintenanceModeError`: domain error; dispatcher surfaces as
  `dispatch_failed` with reason `"maintenance_mode"`.
- `SemanticError` (invalid slug/job_type characters; `project_id`
  does not resolve to a slug): never caught.
- `AllocationNotFoundError`: bubbles to caller (typically
  watcher hooks).
- `UnsupportedOperationError` from `presign_put` when driver lacks
  the capability: bubbles.
- DB conflict on duplicate `run_id`: handled by the ON CONFLICT
  clause — returns the existing row, never surfaces as an error.

Example multiline error:

```python
err_msg_lines = ["Shared results allocation rejected."]
err_msg_lines.append("RUN_ID: {}".format(run_id))
err_msg_lines.append("PROJECT_ID: {}".format(project_id))
err_msg_lines.append("REASON: {}".format(reason))
err_msg_lines.append("PROJECT_MAINTENANCE_MODE: {}".format(mode))

err_msg = os.linesep.join(err_msg_lines)
raise MaintenanceModeError(err_msg) from None
```

## Security Considerations

- Prefix components are regex-validated before concatenation to
  block path injection.
- Presigned put URLs are scoped to the allocation's prefix, not
  the broader project bucket.
- The driver's credentials are the service's — clients never
  write with service credentials; they use either their own
  credentials (preferred) or the short-lived presigned URL.
- `1-audit-log` subscribes to `pychestrate.shared_results.allocated`
  and `.released` for operator visibility.

## Observability

Metrics:

- `pychestrate_ingest_shared_results_allocations_total{project,driver}`
  — counter
- `pychestrate_ingest_shared_results_landed_total{project}` — counter
- `pychestrate_ingest_shared_results_timed_out_total{project}` —
  counter
- `pychestrate_ingest_shared_results_pending{project}` — gauge
- `pychestrate_ingest_shared_results_release_latency_seconds` —
  histogram
- `pychestrate_ingest_shared_results_presign_grants_total{project,driver}`
  — counter

Log events listed in requirements.md NFR-3. Trace span
`pychestrate.shared_results.allocate` with `project`, `run_id`,
`driver`.

Dashboards: pending-prefix gauge + timeout-rate on
`7-orchestration-metrics`; alert on timeout-rate > 5% over 1 h.

## Open Questions

- Should the date directory use the service clock or the client's
  clock? Current draft: service clock (avoids skew surprises).
  Timebox: Phase 3 exit.
- Do we index prefixes in a dedicated table or rely on
  `run.run_id`? Current draft: dedicated table so retention and
  admin tooling can query without joining the full run row.
  Timebox: Phase 3 exit.
- `delete_prefix` API on `0-object-store` — S3/Azure/GCS support
  bulk delete; NFS/SMB require walking. Confirm the driver
  capability gating before the sweeper lands. Timebox: Phase 3
  exit (coordinated with `0-object-store` roadmap).
