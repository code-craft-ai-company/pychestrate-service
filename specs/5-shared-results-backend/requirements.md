# 5-shared-results-backend — Requirements

## Introduction

The `5-shared-results-backend` feature allocates per-run prefixes on
the shared object store (`0-object-store`) and embeds the allocation
result into the job envelope's `results` block so the pod client
knows exactly where to push its testbase result tree. It is the
bridge between the abstract object-store facade and Layer 5's Ryun
semantics — every run owns a deterministic, non-overlapping prefix
whose lifetime tracks the run plus retention. It ships in **Phase 3**,
reuses the `object_store_driver` factory registry rather than
introducing its own, and is the source of the
`backend_key_prefix` / `backend_driver` pair every result watcher and
artifact reader consults.

## Requirements

### Requirement 1: Deterministic Per-Run Prefix Allocation

**User Story:** As a dispatcher, I want the shared results prefix
for a run computed deterministically from the run's ids, so that a
reissued envelope (e.g., after a restart during dispatch) points at
the same location and never aliases another run's tree.

**Acceptance Criteria (EARS):**

1. WHEN `shared_backend.allocate(run_id, project_id, job_type)` is
   called THEN the system SHALL return an `Allocation` whose
   `backend_key_prefix` equals
   `"<project_slug>/results/<yyyy>/<mm>/<dd>/<job_type>/<run_id>"`
   using the *service* clock at allocation time, AND whose
   `backend_driver` equals the active object-store driver's
   registered name.
2. IF `allocate` is called a second time for the same `run_id` THEN
   the system SHALL return the existing `Allocation` unchanged —
   allocation is idempotent on `run_id`.
3. WHEN an allocation is created THEN the system SHALL persist a
   `shared_results_allocation` row with `(run_id, project_id,
   backend_driver, backend_key_prefix, allocated_at,
   hard_deadline_at)`.
4. WHERE the project is in read-only maintenance mode (per
   `0-maintenance-mode`) THEN the system SHALL refuse new
   allocations with `MaintenanceModeError` BUT SHALL continue to
   resolve existing allocations.

### Requirement 2: Lifecycle-Aware Prefix Reservation

**User Story:** As a retention policy, I want the prefix reserved
with an explicit deadline and a documented release event, so that
retention can purge prefixes safely without racing a live watcher.

**Acceptance Criteria (EARS):**

1. WHEN `allocate` is invoked THEN the system SHALL record
   `hard_deadline_at = now + envelope.hard_deadline_at_delta`
   (default: run's `hard_deadline_at` field from the envelope,
   otherwise 24 h).
2. WHEN `5-result-ingest-watcher` emits `entity.result_tree.landed`
   for a run THEN the system SHALL mark the allocation `landed`
   AND stop the deadline timer.
3. IF `hard_deadline_at` expires without a tree landing THEN the
   system SHALL emit
   `pychestrate.shared_results.prefix_timed_out` AND transition the
   allocation to `timed_out`; retention sweeps the prefix per
   `2-retention-policies`.
4. WHEN `shared_backend.release(run_id)` is called THEN the system
   SHALL mark the allocation `released` AND, when retention decides
   to purge, the object store receives a prefix-scoped delete
   issued via `0-object-store.delete_prefix` (added for this feature
   — see Out of Scope below).

### Requirement 3: Envelope Integration and Client Pre-Flight

**User Story:** As a pod client, I want the envelope's `results`
block to contain everything I need — prefix, driver name, optional
presigned put credentials — so that I can start writing result
files immediately without a second call to Pychestrate.

**Acceptance Criteria (EARS):**

1. WHEN `5-job-envelope.codec.build(dispatch_request)` is called
   THEN the system SHALL set `envelope.results.backend_key_prefix`
   and `envelope.results.backend_driver` from the allocation for
   `run_id`.
2. WHERE the active driver advertises capability
   `presign_put: True` AND the envelope requests it THEN the
   system SHALL include a capped-TTL `presigned_put_url` in the
   envelope.
3. IF a client writes outside the allocated prefix THEN the
   result watcher SHALL ignore those writes (they are invisible to
   the watcher's scan scope) — this is an enforcement in
   `5-result-ingest-watcher`, not here, but this feature MUST NEVER
   hand out overlapping prefixes.
4. WHEN a client writes a file under its allocated prefix THEN
   no other run's watcher SHALL observe it.

## Property-Based Test Requirements

### Property 1: Prefix Uniqueness Across All Runs

- **Invariant:** For any generated set of runs across any
  combination of projects, dates, and job types,
  `allocate(r).backend_key_prefix` is unique per `run_id` and
  `(r1, r2)` with `r1.run_id == r2.run_id` yield identical prefixes
  (allocation idempotency).
- **Generator:** `hypothesis.strategies.lists(runs(),
  min_size=1, max_size=1000, unique_by=lambda r: r.run_id)`
  drawing project slugs from a pool of 16 and job types from
  a pool of 8.
- **Assertion:** `len({r.run_id: allocation.backend_key_prefix for
  r in runs}) == len(set(runs))`; each allocation call twice
  returns identical prefix.
- **Sample size:** 1000 generated cases

### Property 2: Prefix Is Strictly Under the Project's Scope

- **Invariant:** For any allocation,
  `allocation.backend_key_prefix.startswith(
  f"{project_slug}/")` is true AND the computed path passes the
  `0-object-store` key regex
  `^[A-Za-z0-9/_.\-]{1,1024}$`.
- **Generator:** Project slugs from a restricted alphabet
  matching the slug rules in `2-projects`; job types from an
  ASCII pool; `run_id` as UUIDv7.
- **Assertion:** prefix invariants hold across all generated
  allocations.
- **Sample size:** 1000 generated cases

## Non-Functional Requirements

- **NFR-1 (Performance):** `allocate` p99 < 25 ms (single INSERT
  with ON CONFLICT). `release` and `mark_landed` p99 < 15 ms.
  Under sustained dispatch load of 1000 allocations/sec the
  shared_results_allocation INSERT SHALL NOT be the bottleneck
  (measured against `5-job-dispatch` throughput NFR).
- **NFR-2 (Security):** Prefixes are sanitized: project slug, date
  components, `job_type` and `run_id` are all validated against
  `^[A-Za-z0-9_.\-]+$` before concatenation.
  `presigned_put_url` TTL is capped at
  `min(envelope.hard_deadline_at + 300 s, max_presign_expires_seconds)`.
  A presigned put URL is scoped to the allocated prefix — never a
  broader project path. Maintenance mode blocks new allocations.
- **NFR-3 (Observability):** Emit metrics
  `pychestrate_ingest_shared_results_allocations_total{project,driver}`
  (counter),
  `pychestrate_ingest_shared_results_landed_total{project}` (counter),
  `pychestrate_ingest_shared_results_timed_out_total{project}` (counter),
  `pychestrate_ingest_shared_results_pending{project}` (gauge),
  `pychestrate_ingest_shared_results_release_latency_seconds`
  (histogram). Log events
  `pychestrate.shared_results.allocated`,
  `pychestrate.shared_results.landed`,
  `pychestrate.shared_results.prefix_timed_out`,
  `pychestrate.shared_results.released`. Trace span
  `pychestrate.shared_results.allocate` with `project`, `run_id`,
  `driver`.
- **NFR-4 (Reliability):** A driver becoming unavailable MUST NOT
  drop pending allocations — the rows remain in `pending` state.
  On driver recovery the watcher continues to scan the already-
  allocated prefixes without reissue.

## Out of Scope

- Object-store driver implementations — owned by `0-object-store`.
- Parsing the result tree itself — owned by
  `5-result-ingest-watcher`.
- Content-addressing and promotion — owned by `5-artifact-store`.
- Actual purge of expired prefixes — owned by
  `2-retention-policies`; this feature publishes events
  (`timed_out`, `released`) that retention consumes.
- A new `delete_prefix` API on `0-object-store` is requested by
  this feature but implemented there.

## Dependencies

- **Depends on:** `0-object-store` (driver facade),
  `0-persistence`, `0-message-bus`, `2-projects` (project slug
  resolution), `0-maintenance-mode`, `5-job-envelope` (envelope
  build-time integration).
- **Depended on by:** `5-job-envelope` (populates
  `envelope.results`), `5-result-ingest-watcher` (scans the
  prefix), `5-artifact-store` (reads blobs from the prefix),
  `2-retention-policies` (purges expired prefixes).
- **Extension points exposed:** None — reuses
  `object_store_driver` from `0-object-store` and
  `retention_action` from `2-retention-policies`.
