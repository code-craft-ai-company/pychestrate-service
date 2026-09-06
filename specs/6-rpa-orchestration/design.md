# 6-rpa-orchestration — Design

## Architecture

RPA orchestration is a fourth Layer 6 domain shaped exactly like
`6-build-orchestration`: a per-project specification, a run record, a
trigger entry point that mints a `JobEnvelope` and hands it to
`5-job-dispatch`, a progress parser and a completion branch in Layer 5
ingest, and a client executor. What is new is the **job type registry**
(job types and versions are deployment-wide, not per project) and the **work
packet** (a JSON document delivered to the executing process).

```
 admin ── registers ──▶ RpaJobType ── publishes ──▶ RpaJobTypeVersion
                                                          ▲
 developer ── creates ──▶ RpaSpec (project) ── selects ───┘
                              │
 operator/watch/pipeline ── trigger(work_packet) ──▶ RpaJob ──▶ JobEnvelope(job_kind=rpa)
                                                                     │
                                                          5-job-dispatch ──▶ pod client
                                                                     │
                                                    rpa_executor (process | tasker subprocess)
                                                                     │
                                       progress (rpa.process.v1) ◀───┴───▶ result tree + exit code
```

Both execution modes end in a subprocess on the client. The tasker mode is a
specialisation of the process mode: the client renders a taskplus workflow
file and runs the `taskplus` console script. This keeps `ccai.taskplus` (and
its `eval`-based expression engine) out of the agent process and lets one
progress and result path serve both modes.

## Data Model

New tables (alembic migration `0xx_rpa_orchestration`):

```
rpa_job_type
  type_id            TEXT PK (slug)
  display_name       TEXT NOT NULL
  description        TEXT NOT NULL DEFAULT ''
  execution_mode     TEXT NOT NULL CHECK (execution_mode IN ('process', 'tasker'))
  capability_requirements JSON NOT NULL DEFAULT '[]'
  packet_schema      JSON NULL          -- JSON Schema draft 2020-12
  secret_fields      JSON NOT NULL DEFAULT '[]'   -- JSON pointer paths
  state              TEXT NOT NULL DEFAULT 'active'  -- active | retired
  created_by_id      TEXT NOT NULL
  created_at / updated_at TIMESTAMP

rpa_job_type_version
  id                 INTEGER PK
  type_id            TEXT FK rpa_job_type
  version            TEXT NOT NULL              -- semver preferred; any label allowed
  source_kind        TEXT NOT NULL CHECK (source_kind IN ('git', 'package'))
  source_ref         TEXT NOT NULL              -- repo URL + ref, or package==version
  entrypoint         JSON NOT NULL              -- see Interfaces
  environment        JSON NOT NULL DEFAULT '{}'
  timeout_minutes    INTEGER NOT NULL DEFAULT 60
  state              TEXT NOT NULL DEFAULT 'active'  -- active | deprecated | retired
  published_by_id    TEXT NOT NULL
  published_at       TIMESTAMP
  UNIQUE (type_id, version)

rpa_spec
  spec_id            INTEGER PK
  project_id         INTEGER FK project
  name               TEXT NOT NULL
  type_id            TEXT FK rpa_job_type
  version_selector   TEXT NOT NULL DEFAULT 'latest-active'
  default_packet     JSON NOT NULL DEFAULT '{}'
  target_pod_id      TEXT NULL
  required_capabilities JSON NOT NULL DEFAULT '[]'
  timeout_minutes    INTEGER NULL
  description        TEXT NOT NULL DEFAULT ''
  revision           INTEGER NOT NULL DEFAULT 1
  created_at / updated_at TIMESTAMP
  UNIQUE (project_id, name)

rpa_spec_revision
  id, spec_id, revision, snapshot JSON, created_at

rpa_job
  job_id             INTEGER PK
  project_id         INTEGER FK project
  spec_id            INTEGER FK rpa_spec
  spec_revision      INTEGER NOT NULL
  type_id            TEXT NOT NULL
  resolved_version   TEXT NOT NULL
  execution_mode     TEXT NOT NULL
  work_packet        JSON NOT NULL             -- redacted copy
  packet_digest      TEXT NOT NULL             -- sha256 of canonical merged packet
  run_id             TEXT NULL                 -- 5-run-state-machine run
  status             TEXT NOT NULL             -- pending | dispatching | running | succeeded | failed | timeout | cancelled
  exit_code          INTEGER NULL
  triggered_by_id    TEXT NOT NULL
  trigger_cause      JSON NOT NULL
  idempotency_key    TEXT NOT NULL
  result_root_key    TEXT NULL
  created_at / started_at / completed_at TIMESTAMP
  INDEX (project_id, created_at DESC), INDEX (idempotency_key)
```

Response dataclasses (in `core/managers/rpa_manager.py`) mirror the tables:
`RpaJobTypeResponse`, `RpaJobTypeVersionResponse`, `RpaSpecResponse`,
`RpaJobResponse`, with `*ListResponse` carrying `total / offset / limit`. The
phase-13 render-smoke suite derives its fixtures from these dataclasses, so
every template attribute must exist on them.

## Interfaces

### Public API

All routes under `/api/v1`, cookie-session or API-key authenticated, RBAC per
`1-rbac`.

#### Job type registry (system scope)

- `GET /api/v1/rpa/job-types` — list; `?state=active|retired`.
- `POST /api/v1/rpa/job-types` — create (`rpa.job_type.manage`).
- `GET /api/v1/rpa/job-types/{type_id}` — detail with versions.
- `PATCH /api/v1/rpa/job-types/{type_id}` — edit display fields, schema,
  secret fields, capabilities.
- `POST /api/v1/rpa/job-types/{type_id}/retire`.
- `POST /api/v1/rpa/job-types/{type_id}/versions` — publish a version.
- `POST /api/v1/rpa/job-types/{type_id}/versions/{version}/deprecate|retire`.

#### Specifications and jobs (project scope)

- `GET|POST /api/v1/projects/{project_id}/rpa/specs`
- `GET|PATCH|DELETE /api/v1/projects/{project_id}/rpa/specs/{spec_id}`
- `POST /api/v1/projects/{project_id}/rpa/specs/{spec_id}/trigger` — body
  `{ work_packet: object, idempotency_key?: str }`; 202 with `RpaJobResponse`.
- `GET /api/v1/projects/{project_id}/rpa/jobs` — `?spec_id&status&page&per_page`.
- `GET /api/v1/projects/{project_id}/rpa/jobs/{job_id}`
- `GET /api/v1/projects/{project_id}/rpa/jobs/{job_id}/logs` — text, `?tail=`.
- `POST /api/v1/projects/{project_id}/rpa/jobs/{job_id}/cancel`

Problem documents follow the RFC 7807 contract; `PacketValidationError`
returns 422 with `errors: [{ path, message }]`.

### Internal API

`webservice/orchestration/rpa/`:

- `registry.py::RpaJobTypeRegistry` — CRUD over job types and versions,
  `resolve_version(type_id, selector) -> RpaJobTypeVersion`
  (semver ordering via `packaging.version`, labels sort after semver).
- `orchestrator.py::RpaOrchestrator.trigger_job(*, project_id, spec_id,
  work_packet, actor_id, trigger_cause, idempotency_key=None) -> RpaJob` —
  merge, validate (`jsonschema`), redact, capability filter, envelope mint,
  `dispatcher.dispatch`, bus events.
- `orchestrator.py::RpaOrchestrator.cancel_job(job_id, actor_id)`.
- `packet.py` — `merge_packet(default, packet)`, `redact_packet(packet,
  secret_fields)`, `packet_digest(packet)`, `validate_packet(packet, schema)`.
- `envelope.py` — `build_rpa_envelope(job, version, packet) -> JobEnvelope`
  with `job_kind = JOB_KIND_RPA`.

Envelope payload (`JobEnvelope.payload`):

```json
{
  "type_id": "invoice-import",
  "version": "1.4.0",
  "execution_mode": "process",
  "source": {"kind": "git", "ref": "https://…/rpa-jobs.git#v1.4.0"},
  "entrypoint": {"command": ["python", "-m", "jobs.invoice_import"], "packet_delivery": "file"},
  "environment": {"LOG_LEVEL": "info"},
  "work_packet": {"customer_id": 42, "period": "2026-08"},
  "timeout_minutes": 30
}
```

For `execution_mode = tasker`, `entrypoint` is
`{"workflow": "workflows/invoice.yaml"}` or `{"tasking": "jobs.invoice@InvoiceImport"}`.

Layer 5 changes:

- `jobs/envelope/schema.py`: `JOB_KIND_RPA = "rpa"` added to
  `SUPPORTED_JOB_KINDS`; `canonical.py` accepts it.
- `orchestration/pipelines/execution/orchestrator.py`: `JOB_KIND_RPA` branch
  and an `RpaStepKind` (`factories/rpa_step_kind.py`) so a pipeline stage
  can trigger a specification with a packet.
- `ingest/progress/service.py`: parser for `format_tag = "rpa.process.v1"`
  (`{ "line": str, "stream": "stdout|stderr", "ts": iso }` and
  `{ "progress": { "percent": int, "message": str } }`).
- `ingest/result/completion.py`: `RPA_FORMAT_TAG = "rpa.result.v1"` branch
  that records `exit_code`, `result_root_key`, and the terminal status on
  `rpa_job`.

### Extension Surface

- `factory: rpa_job_type` — `RpaJobTypeProtocol` with classmethods
  `type_id()`, `execution_mode()`, `packet_schema()`, `secret_fields()`,
  `capability_requirements()`, `versions() -> list[RpaJobTypeVersionSpec]`,
  `validate_packet(packet)`. Extensions ship job types as code; the registry
  merges discovered protocol implementations with database-registered types
  (database wins on conflict, logged). In-tree implementations:
  `ProcessJobType` and `TaskplusJobType` base classes that extension authors
  subclass.
- `resource: RpaPacketRendererExtension` — optional UI renderer for a
  packet schema (default is the JSON editor).
- `event: entity.rpa.job_started`, `entity.rpa.job_completed`,
  `entity.rpa.job_type_published`.

Client side (`pychestrate-client`):

- `rpa_executor.py::execute_rpa_envelope(*, state, envelope, local_run_id,
  aspects, progress_reporter) -> RpaRunOutcome` following
  `build_executor.py`: `resolve_rpa_dirs`, source acquisition (reuse the
  build executor's git checkout), packet materialisation, subprocess run via
  `aspects.run_func`, log tailing to the progress reporter, results upload.
- `RpaExecutorAspects { run_func, taskplus_binary = "taskplus",
  progress_interval_seconds = 1.0, cancel_grace_seconds = 10, max_packet_bytes }`
  wired into `DispatchConsumerAspects`.
- Capability advertisement: `rpa` kind with attributes
  `{ "job_types": ["invoice-import@1.4.0", …], "taskplus": "1.0.2" | null }`
  so `capability_matcher` predicates `has(rpa)` and `rpa.taskplus` work.

### Events Emitted

`entity.rpa.job_started`, `entity.rpa.job_completed`,
`entity.rpa.job_type_published`, `entity.rpa.job_type_retired`.

### Events Consumed

`entity.run.state_changed` (mirror into `rpa_job.status`),
`entity.run.progress` (log viewer), `entity.run.result_ingested`.

## Component Breakdown

- `core/managers/rpa_manager.py` — response dataclasses, `RpaManager`
  (CRUD, listing, version resolution) over the ORM.
- `core/orm/rpa.py` — SQLAlchemy models; alembic migration.
- `webservice/orchestration/rpa/{registry,orchestrator,packet,envelope,errors}.py`.
- `webservice/orchestration/rpa/restapi/v1/rpa_routes.py` — REST surface,
  `register_rpa_routes(*, app, version_prefix)`.
- `webservice/orchestration/rpa/factories/{protocol,process_job_type,taskplus_job_type}.py`.
- `webinterface/blueprints/projects/routes_rpa.py` + templates
  `projects/rpa/{list,detail,logs,spec_list,spec_detail,spec_create,spec_edit,run}.html`
  using `site_shell/_macros.html` and the shared log viewer.
- `webinterface/blueprints/config/routes_rpa_types.py` + templates
  `config/rpa_types/{list,detail,create,version_create}.html`.
- `nav_manifest.py`: `Projects` group gets nothing new (project sub-nav
  carries RPA); `Admin` group gets "RPA Job Types"; a new top-level
  `Automation` entry `/rpa` (bundle view of jobs across projects) is optional
  and tagged with surface `rpa` (see `9-ui-profiles`).
- Client: `rpa_executor.py`, `rpa_progress_reporter.py`, capability
  advertisement, `dispatch_consumer.py` branch.

## Key Flows

### Flow 1 — Trigger a process job from the UI

1. Developer opens the specification, edits the pre-filled packet, submits
   the Run form (CSRF, confirm dialog).
2. Route handler calls `RpaOrchestrator.trigger_job`; packet merged,
   validated, redacted; version resolved; capabilities checked.
3. `RpaJob` row inserted `pending`; envelope minted with `job_kind = rpa`;
   `dispatcher.dispatch` selects a pod; row moves to `dispatching`.
4. Client acquires source, writes `work_packet.json`, runs the command, tails
   output as `rpa.process.v1` progress; the job detail page's log viewer
   refreshes while `running`.
5. Process exits; client uploads results with `exit_code`; completion branch
   sets `succeeded | failed | timeout`; `entity.rpa.job_completed` emitted;
   detail page shows exit code and result tree.

### Flow 2 — Tasker-based job

Same as Flow 1 through dispatch. The client renders
`workflow.rendered.yaml` from the declared workflow (or a one-task workflow
wrapping the declared `module@Class` tasking), sets `parameters` to the work
packet and `environment` to the declared environment, and runs
`taskplus workflow run workflow.rendered.yaml` as the subprocess. Exit code
and logs follow the process path.

### Flow 3 — Publish a new version and roll projects forward

Admin publishes `1.5.0`; specifications with `latest-active` pick it up on
their next trigger and record `resolved_version = 1.5.0`; a specification
pinned to `1.4.0` is unaffected until edited; deprecating `1.5.0` makes
`latest-active` fall back to `1.4.0`.

### Flow 4 — Cancel

Operator cancels from the job detail page; orchestrator forwards the cancel
through Layer 5; client terminates the process group; status `cancelled`.

## Error Handling

- `PacketValidationError` (422) lists every failing JSON pointer.
- `CapabilityMismatchError` (409) lists required and advertised sets.
- `VersionNotActiveError` / `JobTypeRetiredError` (409).
- `PacketTooLargeError` (413) above `max_packet_bytes`.
- Client-side: source acquisition failure and missing `taskplus` binary are
  reported as `failed` with a diagnostic in `stderr.log`, never as a hung run.

## Security Considerations

- Work packets may carry secrets: `secret_fields` are redacted in storage
  and in every UI and API read; the envelope is signed and delivered once.
- The taskplus expression engine evaluates workflow text with `eval`; running
  it only as a subprocess on the pod, from a signed envelope, and never in the
  agent or service process, bounds the blast radius. Job type registration
  is admin-only.
- Process jobs inherit the agent's user; pods that run untrusted job types
  should run agents under a dedicated account (documented, not enforced here).
- New RBAC permissions: `rpa.job_type.manage` (system), `rpa.spec.manage`,
  `rpa.job.trigger`, `rpa.job.read` (project roles: admin, developer, viewer
  respectively as with builds).

## Observability

- Metrics: `rpa_jobs_triggered_total{type_id,mode}`,
  `rpa_job_duration_seconds{type_id}`, `rpa_packet_validation_failures_total`.
- Structured log events: `pychestrate.rpa.trigger`, `.dispatch`,
  `.complete`, `.cancel`, `.packet_rejected`.
- Audit log entries for job type create/publish/retire and every trigger.

## Open Questions

1. Should the `Automation` global view (`/rpa`, cross-project jobs) ship as a
   web-component bundle like `/builds`, or only as project-scoped server
   pages? The remediation left both patterns in place; the recommendation is
   project pages first, bundle later if operators need the cross-project view.
2. Version labels: enforce strict semver or accept arbitrary labels that sort
   after semver? The design accepts labels but warns on publish.
3. Where should job type code live for in-house types: a git repository per
   type (source kind `git`) or a shared `pychestrate-rpa-jobs` package
   (source kind `package`)? Both are supported; a convention is needed.
4. Does the tasker-based mode need the taskplus `flowstate` returned as a
   structured result, or is a results directory written by tasks enough?
