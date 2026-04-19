# 3-dynamic-pods — Tasks

## Milestones

- **M1 — Skeleton:** Template CRUD, render, plan, and a hand-wired
  libvirt provisioner for a toy spec produce a `ready` pod end-to-end in
  a dev environment.
- **M2 — Core Behavior:** Full state machine with checkpointing,
  teardown / rollback, restart-safe resumer, terraform provisioner,
  REST + bus events.
- **M3 — Hardening:** Sandbox enforcement, sandbox capability gating,
  orphan alerting, metrics, perf validation, extension-point coverage.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Migration pack: `pod_template`, `dynamic_pod_materialization`
  tables.
- [ ] T1.2 — DTOs and `MaterializationState` enum.
- [ ] T1.3 — Declare `PodProvisionerProtocol(FactoryProtocolBase)` with
  `required_capabilities=("dispatch:jobs","net:outbound")`.
- [ ] T1.4 — Declare `PodTemplateExtension(ResourceExtension)`.
- [ ] T1.5 — Implement `render.py` with a sandboxed Jinja2 environment.
- [ ] T1.6 — Implement `plan_provisioning` enforcing client-last ordering.
- [ ] T1.7 — Implement `LibvirtProvisioner` reference factory.
- [ ] T1.8 — `start_materialization` + minimal `worker.py` driving
  PENDING -> RENDERING -> RESERVING -> PROVISIONING -> AWAITING_CLIENT ->
  READY for a toy template.
- [ ] T1.9 — REST: template CRUD + `:materialize` + handle `GET`.

### M2 — Core Behavior

- [ ] T2.1 — Integrate `4-checkout-checkin` reservations into RESERVING
  state; record `reservation_ids` on the row.
- [ ] T2.2 — Implement teardown / rollback path with reverse-order
  execution and `teardown_max_attempts`.
- [ ] T2.3 — Implement `resume.py` that re-enqueues non-terminal
  materializations on service restart.
- [ ] T2.4 — Implement `TerraformProvisioner` reference factory
  (`PRECEDENCE=110`).
- [ ] T2.5 — Wait for `entity.client.enrolled` + `entity.pod.registered`
  in AWAITING_CLIENT via `0-message-bus` correlation.
- [ ] T2.6 — REST `:release` endpoint transitioning to DRAINING.
- [ ] T2.7 — Publish all `entity.pod.*` bus events listed in design.md.
- [ ] T2.8 — Audit log writes for start / release / orphan.

### M3 — Hardening

- [ ] T3.1 — `E-extension-sandbox` integration: registry refuses to call
  a provisioner missing `dispatch:jobs` or `net:outbound`.
- [ ] T3.2 — Secret-scrubbing on parameter audit entries via
  `3-pod-scoped-config` integration.
- [ ] T3.3 — Orphaned-pod alerting through `2-notification-hub` with
  runbook link.
- [ ] T3.4 — Emit all metrics in design.md Observability.
- [ ] T3.5 — Trace spans `dynamic_pod.materialize`,
  `dynamic_pod.provision_step.<name>`,
  `dynamic_pod.teardown_step.<name>`, `dynamic_pod.resume`.
- [ ] T3.6 — Perf run: render p99 <= 250 ms on 64 KiB templates;
  Pychestrate-side overhead p99 <= 1 s per member transition on a test
  provisioner.
- [ ] T3.7 — Sphinx docs for templates, provisioners, REST.

## Test Tasks

- [ ] TT-1 — Unit tests for each EARS clause in Requirements 1-3.
- [ ] TT-2 — Hypothesis tests for Property 1 (reverse-order teardown),
  Property 2 (referentially-transparent render), Property 3 (client-last
  ordering).
- [ ] TT-3 — Integration test: submit template -> materialize -> client
  enrolls -> static pod registers -> pod is `ready` -> release -> all
  reservations released.
- [ ] TT-4 — Extension-point test: out-of-tree `DockerComposeProvisioner`
  loads at `PRECEDENCE=95`, overrides libvirt for a `docker_service`
  member kind, and is used.
- [ ] TT-5 — Failure-injection test: mid-provision failure rolls back in
  reverse order without touching post-failure steps.
- [ ] TT-6 — Restart test: kill the worker mid-provision; bring it back;
  resumer resumes at the last checkpointed step; end state is correct.

## Definition of Done

- [ ] All EARS requirements have passing acceptance tests.
- [ ] Property-based tests pass across 1000+ generated cases each.
- [ ] `pod_provisioner` and `PodTemplateExtension` each have at least
  two in-tree references plus a test-only override.
- [ ] Metrics / logs / traces emitted per requirements.md NFR-3.
- [ ] Sphinx docs generated.
- [ ] Code conforms to AGENTS.md coding standards.
- [ ] No TODO / FIXME left in shipped code.
- [ ] Feature listed in the Definition of Done for Phase 8 in
  specs/implementation-plan.md.
