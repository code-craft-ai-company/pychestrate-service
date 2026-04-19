# 3-static-pods — Tasks

## Milestones

- **M1 — Skeleton:** Register + deregister paths work end-to-end against a
  single pod definition; bus events fire; history REST read.
- **M2 — Core Behavior:** Liveness cascade, reconcile-on-recover, full
  rejection taxonomy, audit log, ownership check.
- **M3 — Hardening:** Concurrency handling, metrics, perf target,
  extension hook test, operator runbook.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Migration pack: `pod_registration` table with unique partial
  index `(pod_id) where deregistered_at is null`.
- [ ] T1.2 — DTOs `MemberReport`, `StaticPodRegistrationResult`,
  `StaticPodDeregistrationResult`, `ReconcileOnRecoverResult`.
- [ ] T1.3 — `PodRegistrationRepository` with `get_active`,
  `insert_registration`, `deregister`, `transition_state`.
- [ ] T1.4 — `service.register_static_pod`: fetch pinned definition,
  verify member-set, compute `report_hash`, write row, publish
  `entity.pod.registered`.
- [ ] T1.5 — `service.deregister_static_pod`: write deregistration,
  publish `entity.pod.deregistered`.
- [ ] T1.6 — Transport frame handlers `handlers.on_register_frame`,
  `handlers.on_deregister_frame`.
- [ ] T1.7 — Read-only REST router: current registration + history.

### M2 — Core Behavior

- [ ] T2.1 — Ownership check: resolve `client_id` via
  `3-client-registry`, compare against
  `pod_definition.client_binding.pod_name`; fail with
  `PodNotOwnedByClient`.
- [ ] T2.2 — Bus subscriber for `entity.client.liveness_changed` that
  cascades `to=lost` to `state=client_lost` for all owned active
  registrations.
- [ ] T2.3 — Reconcile-on-recover flow: compare `report_hash` with stored
  one; transition back to `registered` on match, stay `client_lost` on
  mismatch.
- [ ] T2.4 — Bus subscriber for `entity.client.revoked` that
  force-deregisters with reason `client_revoked`.
- [ ] T2.5 — Bus subscriber for `entity.pod.definition_deleted` that
  soft-deregisters with reason `definition_deleted`.
- [ ] T2.6 — Idempotent register path: matching hash updates only
  `last_report_at`, no new bus event.
- [ ] T2.7 — Audit-log writes for register / deregister / rejection with
  `actor=client:<id>`.

### M3 — Hardening

- [ ] T3.1 — Concurrency: detect `ConcurrentRegistrationConflict` on
  parallel inserts, retry once with refreshed read.
- [ ] T3.2 — Emit all metrics in design.md Observability.
- [ ] T3.3 — Trace spans `static_pod.register`, `.deregister`,
  `.reconcile_on_recover`.
- [ ] T3.4 — Perf validation: register 500 pods with 32 members each;
  p99 <= 250 ms.
- [ ] T3.5 — Report size cap (128 KiB) at frame handler boundary.
- [ ] T3.6 — Sphinx docs for the frame handlers, service API, and REST
  read routes.

## Test Tasks

- [ ] TT-1 — Unit tests for each EARS clause in Requirements 1-3.
- [ ] TT-2 — Hypothesis tests for Property 1 (idempotent duplicate
  delivery), Property 2 (reconcile preserves run identity), Property 3
  (validation symmetric-difference totality).
- [ ] TT-3 — Integration test: client enrolls -> registers pod -> loses
  connectivity for 60 s -> reconnects -> same report -> pod returns to
  `registered` with unchanged runs.
- [ ] TT-4 — Extension-hook test: an out-of-tree subscriber to
  `entity.pod.registered` runs on every registration event via
  `E-extension-hooks`.
- [ ] TT-5 — Negative ownership test: a client attempts to register a pod
  bound to a different client; registration is rejected with
  `PodNotOwnedByClient`.

## Definition of Done

- [ ] All EARS requirements have passing acceptance tests.
- [ ] Property-based tests pass across 1000+ generated cases each.
- [ ] `entity.pod.registered` and `entity.pod.deregistered` are exercised
  by at least one in-tree subscriber and one out-of-tree subscriber in
  tests.
- [ ] Metrics / logs / traces emitted per requirements.md NFR-3.
- [ ] Sphinx docs generated.
- [ ] Code conforms to AGENTS.md coding standards.
- [ ] No TODO / FIXME left in shipped code.
- [ ] Feature listed in the Definition of Done for Phase 2 in
  specs/implementation-plan.md.
