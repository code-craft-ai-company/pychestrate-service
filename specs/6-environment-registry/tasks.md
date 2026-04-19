# 6-environment-registry — Tasks

## Milestones

- **M1 — Skeleton:** `environment` schema + declare/list/get + `K8sClusterEnvironmentKind` + REST endpoints.
- **M2 — Core Behavior:** archive/freeze/unfreeze, `record_apply`, `mark_destroyed`, probe/guard assignments, additional built-in kinds.
- **M3 — Hardening:** Observability, property tests, perf, audit, docs.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Create `source/site/automojo/pychestrate/webservice/orchestration/infra/environment/` package per design.md.
- [ ] T1.2 — Add `0-persistence` migration for `environment`, `environment_probe_assignment`, `environment_guard_assignment`, `environment_history`.
- [ ] T1.3 — Implement `kind_protocol.py::EnvironmentKindExtension`.
- [ ] T1.4 — Implement `K8sClusterEnvironmentKind` at `source/site/automojo/extensions/pychestrate/environment_kind/k8s_cluster.py` with declared `attrs_schema`.
- [ ] T1.5 — Implement `registry.py::EnvironmentRegistry.declare`, `list`, `get`.
- [ ] T1.6 — Register REST `POST/GET /api/v1/projects/{id}/environments`, `GET /environments/{id}`.

### M2 — Core Behavior

- [ ] T2.1 — Implement `archive`, `freeze`, `unfreeze` with REST endpoints; emit corresponding events.
- [ ] T2.2 — Implement `record_apply` and `mark_destroyed` with row-level locking and monotonicity.
- [ ] T2.3 — Implement `set_probes`, `set_guards`, and `PATCH /attrs` with schema revalidation.
- [ ] T2.4 — Implement `VmPoolEnvironmentKind`, `CloudAccountEnvironmentKind`, `DatabaseServiceEnvironmentKind` under `source/site/automojo/extensions/pychestrate/environment_kind/`.
- [ ] T2.5 — Implement `kind_registry.py` accessor; subscribe to `extension.reloaded`.
- [ ] T2.6 — Emit `entity.env.declared`, `entity.env.archived`, `entity.env.frozen`, `entity.env.unfrozen`, `entity.env.applied`, `entity.env.destroyed`.
- [ ] T2.7 — Wire audit log for every mutation.
- [ ] T2.8 — Cascade archive on `entity.project.archived`.

### M3 — Hardening

- [ ] T3.1 — Emit Prometheus metrics and OTel spans per design.md Observability.
- [ ] T3.2 — Benchmark NFR-1: declare p99 < 90 ms; get p99 < 40 ms; list p99 < 120 ms at 1 000 envs; record_apply p99 < 80 ms. Fail CI on regression.
- [ ] T3.3 — Enforce attribute-schema secret handling: attrs carry only `_secret_ref` markers, not expanded values.
- [ ] T3.4 — Sphinx docs for REST, internal API, kind authoring.
- [ ] T3.5 — Verify multiline errors use `os.linesep.join([...])`.
- [ ] T3.6 — Implement `is_frozen(environment_id)` fast path consumed by `6-infra-orchestration`.

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement in requirements.md (Requirements 1–3).
- [ ] TT-2 — Property-based tests implementing Property 1 (schema determinism) and Property 2 (record_apply monotonicity) at 1000 cases each.
- [ ] TT-3 — Integration test: declare a k8s env, record an apply, freeze it, attempt an infra apply via `6-infra-orchestration` → rejected with `FrozenEnvironmentError`.
- [ ] TT-4 — Extension-point test: test-only `GpuFarmEnvironmentKind` (`PRECEDENCE = 1`) declared; verify declare accepts matching attrs and rejects mismatching ones.
- [ ] TT-5 — Concurrency test: 50 concurrent `record_apply` calls with random timestamps; the pointer equals the `(applied_at, run_id)` max.
- [ ] TT-6 — Cascade archive test: archiving a project archives all its envs.

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
