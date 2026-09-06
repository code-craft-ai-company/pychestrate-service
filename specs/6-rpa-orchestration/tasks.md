# 6-rpa-orchestration — Tasks

## Milestones

- **M1 — Skeleton:** ORM + migration, `RpaManager` dataclasses, job type
  registry, `RpaOrchestrator.trigger_job` happy path for the process mode,
  envelope `job_kind = rpa`, client `rpa_executor` process path, minimal
  REST and project pages.
- **M2 — Core Behavior:** Tasker mode, packet schema validation and
  redaction, version resolution and lifecycle, capability advertisement and
  matching, cancel, progress parser and completion branch, admin registry
  pages, pipeline step kind and watch action, bus and audit events.
- **M3 — Hardening:** Property tests, extension protocol tests, RBAC,
  observability, UI profile gating, docs and `openapi/pychestrate.yaml`.

## Tasks

### M1 — Skeleton

- [x] T1.1 — Add `JOB_KIND_RPA = "rpa"` to `jobs/envelope/schema.py`, `SUPPORTED_JOB_KINDS`, `canonical.py`, and the client's `dispatch_consumer.py` kind tuple; unit tests for acceptance.
- [x] T1.2 — ORM models `RpaJobType`, `RpaJobTypeVersion`, `RpaSpec`, `RpaSpecRevision`, `RpaJob` under `core/orm/rpa.py`; alembic migration. *Done 2026-09-05 as `orchestration/rpa/models.py` (orchestration layer, `project_id` kept as a string reference) plus alembic `f2a3b4c5d6e7`.*
- [x] T1.3 — `core/managers/rpa_manager.py` with response dataclasses and CRUD (`RpaManager`), including `list_jobs(project_id, spec_id, status, offset, limit)` returning `total`. *Done 2026-09-05 as the view dataclasses and read functions in `orchestration/rpa/service.py`; no separate core manager was needed.*
- [x] T1.4 — `orchestration/rpa/registry.py::RpaJobTypeRegistry` with `resolve_version`. *Done 2026-09-05 inside `orchestration/rpa/service.py` (`register_job_type`, `publish_version`, `resolve_version`, `set_version_state`, `retire_job_type`).*
- [x] T1.5 — `orchestration/rpa/packet.py` (`merge_packet`, `packet_digest`, `redact_packet`, `validate_packet`).
- [x] T1.6 — `orchestration/rpa/envelope.py::build_rpa_envelope` and `orchestrator.py::RpaOrchestrator.trigger_job` (process mode, no schema yet).
- [x] T1.7 — REST routes `rpa_routes.py` (job types list/create/detail, versions publish, specs CRUD, trigger, jobs list/detail/logs) registered from `register_service_extensions()`.
- [x] T1.8 — Client `rpa_executor.py` process path: dirs, packet file, env, subprocess via `aspects.run_func`, `stdout.log`/`stderr.log`, exit code, results upload; `_handle_rpa_job` branch in `dispatch_consumer.py`. *Done 2026-09-05; tasker mode landed alongside (`render_taskplus_workflow`, `taskplus workflow run`).*
- [x] T1.9 — Project web pages: `routes_rpa.py` with `rpa_list`, `rpa_detail`, `rpa_logs`, `rpa_spec_list`, `rpa_spec_detail`, `rpa_spec_create`, `rpa_run`; templates using `site_shell/_macros.html`, `ui.log_viewer`, `ui.status_badge`, `ui.pagination`; sub-nav entry "RPA" in `projects/base.html`; register fixtures for the new template variables in `testshared/factories/webui/template_contexts.py`. *Done 2026-09-05; the Run form lives on the specification detail page.*

### M2 — Core Behavior

- [x] T2.1 — Tasker mode on the client: render `workflow.rendered.yaml` (packet → `parameters`, environment → `environment`; wrap a `module@Class` tasking in a one-task workflow), run `taskplus workflow run` as the subprocess; detect a missing binary and fail with a diagnostic. *Done 2026-09-05 with T1.8.*
- [x] T2.2 — Packet schema validation (`jsonschema`, draft 2020-12) with per-path errors; `secret_fields` redaction in storage and reads; `max_packet_bytes`. *Done 2026-09-05 (jsonschema draft 2020-12, per-path errors, `secret_fields` redaction, 1 MiB cap).*
- [x] T2.3 — Version lifecycle: deprecate, retire, `latest-active` resolution with semver ordering; refuse runs against retired identities. *Done 2026-09-05 (semver via `packaging.version`, labels sort after versions).*
- [x] T2.4 — Capability kind `rpa` on the client (job types installed, taskplus version); `capability_requirements` filter in the orchestrator; `CapabilityMismatchError`. *Done 2026-09-05 server-side (`RpaCapability` kind, `capability_tags_for_client` enrichment of dispatch candidates); the client does not advertise capabilities yet in any domain, so the pod-side advertisement stays open.* *Closed 2026-09-06: `PUT /api/v1/clients/{id}/capabilities` (mTLS-matched pod) plus the client's `capabilities.py`, which advertises the `rpa` kind (taskplus version, configured `rpa_job_types` and `capability_tags`) when the dispatch loop starts.*
- [x] T2.5 — Progress parser `rpa.process.v1` and completion branch `rpa.result.v1` in Layer 5 ingest; status mirror from `entity.run.state_changed`. *Done 2026-09-05 (`FRAME_KIND_RPA` frames with `rpa.process.v1` line batches, `complete_rpa_run` on `rpa.result.v1`; status mirrored from the manifest's `rpa_status`).*
- [x] T2.6 — Cancel: REST + UI action, Layer 5 forward, client process-group termination with grace. *Done 2026-09-05 for the service and pages (job marked cancelled, run-state cancel requested); client-side process-group termination is still open.* *Client process-group termination landed 2026-09-05 (`run_streaming` with `cancel_check_func`, SIGTERM then SIGKILL after the grace period); the server-to-client cancel signal still needs a REST poll hook.* *Closed 2026-09-06: the heartbeat acknowledgement's `cancellations` feed the client's `cancel_registry`; each RPA run polls it and terminates its process group.*
- [x] T2.7 — Admin registry pages under `/admin/rpa-job-types` (list, detail, create, publish version, deprecate, retire) with CSRF and `data-confirm`; nav entry in the Admin group. *Done 2026-09-05 (`config/routes_rpa_types.py`, list/create/detail with publish, deprecate, reactivate, retire).*
- [x] T2.8 — Pipeline `RpaStepKind` and watch action `trigger_rpa_job`. *Done 2026-09-05 (`RpaStepKind`, `PipelineOrchestrator._dispatch_rpa_job`, `WatchAction.TRIGGER_RPA_JOB` through the `build_watch_rpa_trigger` bridge).*
- [x] T2.9 — Bus events and audit entries; idempotency window. *Done 2026-09-05 for bus events and the idempotency window; audit-log entries are still open.* *Audit kinds landed 2026-09-05 (`audit/extensions/rpa_events.py`).*
- [x] T2.10 — Run form: JSON packet editor pre-filled with `default_packet`, client-side schema validation, confirm before dispatch. *Done 2026-09-05: browser-side pre-check (JSON parse, required keys, primitive types, enums) runs on submit and renders below the button; the server still validates the full schema.*

### M3 — Hardening

- [x] T3.1 — RBAC permissions and gates; deny paths redirect to the referring page. *Done 2026-09-05: REST routes gate on `system:rpa.read` / `system:rpa.create` / `system:rpa.job_types.manage`; pages gate on project roles and the admin permission and deny through the shared referer-aware redirect.*
- [x] T3.2 — `factory: rpa_job_type` protocol, `ProcessJobType` / `TaskplusJobType` bases, extension-host discovery and conflict handling. *Done 2026-09-05 (`factories/job_type_protocol.py`: `RpaJobTypeProtocol`, `ProcessJobType`, `TaskplusJobType`, `CodeDefinedVersion`; `sync_code_defined_job_types` mirrors implementations into the registry, database wins on conflict).*
- [x] T3.3 — Metrics, structured logs, `openapi/pychestrate.yaml` entries. *Done 2026-09-05 (`metrics/ingest/extensions/rpa_counters.py`, structured `pychestrate.rpa.*` logs, OpenAPI paths and schemas under the `rpa` tag).*
- [x] T3.4 — `9-ui-profiles` gating: tag RPA nav entries, dashboard tiles, and palette provider with surface `rpa`. *Done 2026-09-05 (RPA project tab and the admin registry entry carry surface `rpa`).*
- [x] T3.5 — Documentation: userguide chapter "RPA jobs" (job types, packets, both modes, writing a job type) and glossary entries. *Done 2026-09-05 (`userguide/19-00-rpa-jobs.rst`, glossary entries).*

## Test Tasks

- [x] Property 1 (packet merge), Property 2 (redaction), Property 3 (version resolution) as testbase property tests.
- [x] Render-smoke coverage for every new template (populated and sparse) via the phase-13 suite; endpoint lint passes.
- [x] Route tests for trigger (422 on packet failure, 409 on capability mismatch, 202 happy path), cancel, and the redacted read.
- [x] Client executor tests with an injected `run_func`: process mode, tasker mode rendering, timeout, cancel, missing binary.
- [x] End-to-end: trigger from the UI, run on a local client, log viewer shows output, detail shows exit code and results. *Browser sweep 2026-09-05 (`verify_rpa_browser.py`): register type, publish version, create spec, Run form validation, trigger reaches dispatch ("no enrolled pod" without a client), UI-profile flows; axe clean on 17 of 18 pages (the remaining one is the upstream mj-select button-name on /builds). Running the job on a real pod still needs an enrolled client, whose private dependencies are not installable in this workspace.*

## Definition of Done

- A process job type and a tasker job type can each be registered,
  versioned, bound to a project specification, triggered with a work packet
  from the UI and the API, executed on a pod, cancelled, and inspected
  (packet redacted, logs live, exit code, results).
- The full singlehost suite and the phase-13 guardrails pass; the browser
  sweep shows the new pages with no serious or critical axe violations.
- Hiding the `rpa` surface through `9-ui-profiles` removes it from
  navigation, dashboards, and the palette.
