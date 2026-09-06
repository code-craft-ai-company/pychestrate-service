# 6-rpa-orchestration — Requirements

## Introduction

The `6-rpa-orchestration` feature adds Robotic Process Automation jobs to
Pychestrate as a fourth orchestration domain beside builds, infrastructure,
and tests. It lives in **Layer 6** of the architecture (see
`specs/implementation-plan.md`) and ships in **Phase 11**. An RPA job is
identified by a **job type** and a **version**, receives a **work packet**
(the data the job processes), performs the work on a pod client agent, and
reports progress and a result tree through the existing `5-job-*` plane.

Two execution modes are supported, both on the internal framework:

- **Simple process job** — the client hands the work packet to a process
  (a command or script declared by the job type). The job reads the packet,
  performs the work, and exits; the exit code and the files it writes are
  the result.
- **Tasker-based job** — the client runs a `codecraftai-taskplus` workflow
  (`module@Class` tasks) with the work packet injected as the workflow's
  parameters. The workflow engine runs behind a process boundary so the
  service and the client never import it in-process.

No external RPA platform is involved. Like `6-build-orchestration` and
`6-test-orchestration`, this feature reuses `5-job-dispatch`, the run state
machine, progress ingest, and result ingest unchanged; it owns the
RPA-specific specification, job type registry, run records, trigger
semantics, and the `rpa_job_type` factory protocol.

## Requirements

### Requirement 1: RPA Job Types Are Registered With Versions

**User Story:** As an automation engineer, I want to register a job type
once (what it runs, how it receives its packet, what it needs from a pod)
and publish versions of it, so that projects can run a named, versioned
automation without redefining it per project.

**Acceptance Criteria (EARS):**

1. WHEN an administrator registers an RPA job type THEN the system SHALL persist `RpaJobType { type_id: str (slug), display_name, description, execution_mode: process | tasker, capability_requirements: list[str], packet_schema: Optional[JSON Schema] }` and SHALL reject a `type_id` that is not a lowercase slug of 3 to 64 characters.
2. WHEN a version is published for a job type THEN the system SHALL persist `RpaJobTypeVersion { type_id, version: str (semver or pinned label), source: { kind: git | package, ref }, entrypoint, environment: dict[str, str], timeout_minutes, state: active | deprecated | retired }` AND SHALL reject a duplicate `(type_id, version)` pair with `DuplicateVersionError`.
3. WHERE `execution_mode == process` the system SHALL require `entrypoint.command: list[str]` (argv) AND SHALL accept an optional `entrypoint.packet_delivery: file | stdin | env` defaulting to `file`.
4. WHERE `execution_mode == tasker` the system SHALL require `entrypoint.workflow: str` (a path to a taskplus YAML workflow inside the resolved source) OR `entrypoint.tasking: str` (a `module@Class` task identity) AND SHALL reject an entrypoint that names neither.
5. WHEN a job type or version is retired THEN the system SHALL refuse new runs against it with `SemanticError` naming the retired identity, AND SHALL leave existing run records readable.

### Requirement 2: RPA Specifications Bind A Job Type To A Project

**User Story:** As a project developer, I want an RPA specification that says
which job type and version my project runs, with default packet fields and a
pod selector, so that triggering the job is one action.

**Acceptance Criteria (EARS):**

1. WHEN a developer creates an RPA specification THEN the system SHALL persist `RpaSpec { spec_id, project_id, name, type_id, version_selector: exact version | "latest-active", default_packet: dict, target_pod_id: Optional, required_capabilities: list[str], timeout_minutes: Optional, description }` under the project.
2. WHEN `version_selector == "latest-active"` THEN the system SHALL resolve the highest active version by semver ordering at trigger time and SHALL record the resolved version on the run.
3. IF the referenced job type has no active version THEN the system SHALL refuse to create the specification with `SemanticError` naming the job type.
4. WHEN a specification is edited THEN the system SHALL increment `RpaSpec.version` (the specification's own revision) and SHALL record the previous revision so a run can show the specification as it was when triggered.

### Requirement 3: Triggering An RPA Job Delivers A Work Packet

**User Story:** As an operator, I want to trigger an RPA job with a work
packet, from the UI, the REST API, a watch, or a pipeline stage, so that the
same automation serves interactive, scheduled, and event-driven use.

**Acceptance Criteria (EARS):**

1. WHEN a caller invokes `rpa_orchestrator.trigger_job(project_id, spec_id, work_packet, trigger_cause, aspects)` THEN the system SHALL merge `work_packet` over `RpaSpec.default_packet` (packet keys win), validate the merged packet against the job type's `packet_schema` when one is declared, and SHALL raise `PacketValidationError` listing every failing path before any dispatch.
2. WHEN the packet is valid THEN the system SHALL persist `RpaJob { job_id, project_id, spec_id, spec_revision, type_id, resolved_version, work_packet (redacted copy), status: pending, triggered_by, trigger_cause, created_at }` and SHALL mint a `JobEnvelope` with `job_kind = "rpa"` whose payload carries `{ type_id, version, execution_mode, source, entrypoint, environment, work_packet, timeout_minutes }`.
3. IF the packet contains a key listed in the job type's `secret_fields` THEN the system SHALL store only a redaction marker for that key in `RpaJob.work_packet` AND SHALL place the real value in the envelope only.
4. WHERE the specification or job type declares `required_capabilities` the system SHALL dispatch only to a pod client whose advertised capabilities cover `rpa` plus the declared set, AND SHALL raise `CapabilityMismatchError` listing both sides otherwise.
5. WHEN two triggers arrive within `idempotency_window_seconds` with the same `(project_id, spec_id, packet_digest, trigger_cause_kind)` THEN the system SHALL return the original `job_id` without creating a second job.
6. WHEN a job is triggered THEN the system SHALL emit `entity.rpa.job_started` with `{ job_id, project_id, spec_id, type_id, version, execution_mode, trigger_cause }`, AND on a terminal state `entity.rpa.job_completed` with `{ job_id, final_status, started_at, finished_at, result_root_key, exit_code }`.

### Requirement 4: Clients Execute Both Modes Behind A Process Boundary

**User Story:** As a pod operator, I want the client agent to run RPA jobs
with the same isolation and reporting it uses for builds and tests, so that a
misbehaving automation cannot take the agent down and I can follow it live.

**Acceptance Criteria (EARS):**

1. WHEN a client receives an envelope with `job_kind = "rpa"` THEN the client SHALL route it to `rpa_executor.execute_rpa_envelope` and SHALL acquire the declared `source` (git ref checkout or installed package) into a per-run working directory before executing.
2. WHERE `execution_mode == process` the client SHALL write the work packet as `work_packet.json` in the run directory, SHALL export `PYC_WORK_PACKET` (path), `PYC_RUN_ID`, `PYC_JOB_TYPE`, `PYC_JOB_VERSION`, and `PYC_RESULTS_DIR`, SHALL deliver the packet per `packet_delivery`, and SHALL run `entrypoint.command` as a subprocess with the declared environment and timeout.
3. WHERE `execution_mode == tasker` the client SHALL run the taskplus engine as a subprocess (`taskplus workflow run <rendered workflow>`), SHALL render the work packet into the workflow's `parameters` and the declared environment into its `environment`, AND SHALL NOT import `ccai.taskplus` into the agent process.
4. WHEN the process writes lines to stdout or stderr THEN the client SHALL forward them as progress through `5-progress-ingest` with `format_tag = "rpa.process.v1"` at least every `progress_interval_seconds`, AND SHALL forward a structured progress record when a line matches the `PYC-PROGRESS <json>` marker.
5. WHEN the process exits THEN the client SHALL upload `PYC_RESULTS_DIR` (plus captured `stdout.log` and `stderr.log`) as the result tree, SHALL report `exit_code`, and SHALL map exit code `0` to `succeeded`, a timeout to `timeout`, and any other code to `failed`.
6. WHEN the server sends a cancel for the run THEN the client SHALL terminate the process group, wait up to `cancel_grace_seconds`, then kill it, and SHALL report `cancelled`.

### Requirement 5: RPA Surfaces In The Web UI

**User Story:** As a project member, I want RPA job types, specifications,
and jobs to appear in the project UI with the same conventions as builds and
tests, so that I do not learn a second interface.

**Acceptance Criteria (EARS):**

1. WHEN a project member opens `/projects/{id}/rpa` THEN the system SHALL render the RPA jobs list (job, specification, type and version, status badge, triggered by, duration, started) with the shared filters, pager, and empty state, and links to `/projects/{id}/rpa/specs`, job detail, and job logs.
2. WHEN a developer opens a specification THEN the system SHALL render a "Run" form that pre-fills `default_packet` as an editable JSON packet, validates it client-side against `packet_schema` when present, and confirms before dispatch.
3. WHEN an administrator opens `/admin/rpa-job-types` THEN the system SHALL render the registry (types, active versions, execution mode, capability requirements) with create, publish-version, deprecate, and retire actions, each CSRF-gated and confirmed.
4. WHEN a job detail page renders THEN the system SHALL show the work packet with secret fields redacted, the resolved version, the log viewer (live while running), the exit code, and the result tree.
5. WHEN the `rpa` surface is disabled by `9-ui-profiles` THEN the RPA navigation entries, dashboard tiles, and palette results SHALL be hidden while the routes remain reachable by URL.

## Property-Based Test Requirements

### Property 1: Packet Merge Is Deterministic And Packet-Wins

For any `default_packet` and `work_packet` dicts, merging yields a dict whose
keys are the union and whose value for a shared key equals the `work_packet`
value; merging twice yields the same digest.

### Property 2: Redaction Never Leaks

For any job type with `secret_fields` and any packet, the persisted
`RpaJob.work_packet` contains the redaction marker at every secret path and
the JSON serialisation of the stored packet contains none of the secret
values.

### Property 3: Version Resolution Is Monotonic

For any set of active versions, `latest-active` resolves to the maximum under
semver ordering, and deprecating that version makes the next-highest active
version resolve.

## Non-Functional Requirements

- Trigger latency: packet validation plus envelope mint under 200 ms at p95
  for packets up to 256 KiB.
- Work packet size limit: 1 MiB; larger inputs must be passed by reference
  (an artifact key), which the process receives in the packet.
- Log forwarding: at most one progress record per second per run in steady
  state; bursts are coalesced.
- The agent must not import `ccai.taskplus` or `ccai.interop.protocols.tasker`
  into its own process; both run only behind subprocess boundaries.

## Out of Scope

- Distributed fan-out of one job across many nodes via the tasker
  controller (`codecraftai-interop-ext-tasker`). The `6-rpa-orchestration`
  job runs on one pod; multi-node fan-out is a later feature that can reuse
  `TaskerController` and `TaskingResultPromise`.
- A visual flow designer for taskplus workflows.
- Browser or desktop UI automation primitives on the client; those arrive as
  job types shipped by extensions, not as agent features.
- External RPA platforms (UiPath, Power Automate, Robocorp).

## Dependencies

- `5-job-envelope` (new `job_kind = "rpa"`), `5-job-dispatch`,
  `5-run-state-machine`, `5-progress-ingest` (new `rpa.process.v1` parser),
  `5-result-ingest-watcher` (new `rpa` completion branch), `5-artifact-store`.
- `3-client-capability-advertisement` (new `rpa` capability kind with
  `job_types` and `taskplus` attributes).
- `2-projects` (project membership and roles), `1-rbac` (new permissions
  `rpa.job_type.manage`, `rpa.spec.manage`, `rpa.job.trigger`,
  `rpa.job.read`), `1-audit-log`.
- `6-pipeline-definition` (an `rpa` step kind), `2-projects` watches (an
  `trigger_rpa_job` watch action).
- `9-ui-profiles` for surface gating; `9-site-shell` for navigation.
- `codecraftai-taskplus` installed on pods that run tasker-based jobs; the
  client only needs its `taskplus` console script on `PATH`.
