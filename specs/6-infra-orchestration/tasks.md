# 6-infra-orchestration — Tasks

## Milestones

- **M1 — Skeleton:** `infra_run` schema + `TerraformInfraDriver` + plan happy path + Layer 5 state mirror.
- **M2 — Core Behavior:** Apply + destroy with guard + frozen checks, `apply_planned` with plan validity, `PulumiInfraDriver`, `AnsibleInfraDriver`, cancel.
- **M3 — Hardening:** Observability, property tests, perf, docs, audit, rate limiting.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Create `source/site/automojo/pychestrate/webservice/orchestration/infra/` package per design.md.
- [ ] T1.2 — Add `0-persistence` migration for `infra_run`, `infra_guard_decision_cache`.
- [ ] T1.3 — Implement `driver_protocol.py::InfraToolDriverProtocol`.
- [ ] T1.4 — Implement `TerraformInfraDriver` at `source/site/automojo/factories/pychestrate/infra/terraform.py` with `PRECEDENCE = 500`.
- [ ] T1.5 — Implement `orchestrator.py::InfraOrchestrator.trigger_run` happy path for `action="plan"`.
- [ ] T1.6 — Implement `state_mirror.py` subscriber mirroring Layer 5 onto `InfraRun` and persisting `plan_summary_ref` + `plan_artifact_ref` + `plan_diff_digest` on terminal plans.
- [ ] T1.7 — Register `POST /api/v1/projects/{id}/infra-runs` and `GET /.../{run_id}`.

### M2 — Core Behavior

- [ ] T2.1 — Wire `BlastRadiusGuards.allow(...)` check for `apply` / `destroy` before dispatch; raise `GuardDeniedError`.
- [ ] T2.2 — Wire `EnvironmentRegistry.is_frozen(...)` check; raise `FrozenEnvironmentError`.
- [ ] T2.3 — Implement `plan_window.py` with `plan_validity_seconds` check; raise `PlanExpiredError`.
- [ ] T2.4 — Implement `apply_planned` endpoint `POST /.../infra-runs/{plan_run_id}:apply-planned`.
- [ ] T2.5 — Implement `PulumiInfraDriver` and `AnsibleInfraDriver` (Ansible: `supports_plan_replay = False`).
- [ ] T2.6 — Implement `cancel_run` and `POST :cancel`.
- [ ] T2.7 — Emit `entity.infra.run_started`, `entity.infra.run_completed`, `entity.infra.plan.promoted`, `entity.infra.guard.denied`, `entity.infra.frozen.rejected`.
- [ ] T2.8 — On apply success, call `env_registry.record_apply(environment_id, run_id, output_digest_sha256)`.

### M3 — Hardening

- [ ] T3.1 — Emit Prometheus metrics and OTel spans per design.md Observability.
- [ ] T3.2 — Benchmark NFR-1: trigger p99 < 200 ms; guard check p99 < 40 ms; `apply_planned` p99 < 250 ms; plan digest p99 < 100 ms @ 2 MiB. Fail CI on regression.
- [ ] T3.3 — Enforce `max_infra_triggers_per_minute_per_project` (default 30).
- [ ] T3.4 — Sphinx docs for REST, internal API, driver authoring.
- [ ] T3.5 — Verify multiline errors use `os.linesep.join([...])`.
- [ ] T3.6 — Subscribe to `entity.env.frozen|unfrozen` and invalidate the guard decision cache.
- [ ] T3.7 — Encrypt-at-rest plan bytes using object-store capability; deny `infra.plan.read` access otherwise.

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement in requirements.md (Requirements 1–3).
- [ ] TT-2 — Property-based tests implementing Property 1 (plan/apply linkage immutability) and Property 2 (guard determinism) at 1000 cases each.
- [ ] TT-3 — Integration test: Phase 7 scenario — trigger a Terraform plan against env `staging`, review summary, `apply-planned` succeeds, env state updated.
- [ ] TT-4 — Extension-point test: in-tree `TerraformInfraDriver` plus a test-only `FakeInfraDriver` (`PRECEDENCE = 1`); verify the fake wins when configured.
- [ ] TT-5 — Guard-deny test: destroy on `prod` denied for user lacking role; `GuardDeniedError` with rule_id surfaced.
- [ ] TT-6 — Plan-expired test: 1 s validity; wait 2 s; `apply_planned` raises `PlanExpiredError`.
- [ ] TT-7 — Frozen-env test: freeze env; apply/destroy rejected; plan still allowed.

## Definition of Done

- [ ] All EARS requirements have passing acceptance tests
- [ ] Property-based tests pass across 1000+ generated cases each
- [ ] Extension surface (if any) has at least one in-tree reference
      implementation and one test-only override using a different `PRECEDENCE`
- [ ] Metrics / logs / traces emitted per requirements.md NFR-3
- [ ] Sphinx docs generated for public and internal APIs
- [ ] Code conforms to AGENTS.md coding standards (no mutable defaults,
      explicit returns, named parameter passing, type hints on every param,
      no behavior-modifying decorators)
- [ ] No TODO / FIXME left in shipped code
- [ ] Feature listed in the Definition of Done for its owning phase in
      specs/implementation-plan.md
