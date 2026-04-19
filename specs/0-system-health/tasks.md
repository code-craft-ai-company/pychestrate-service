# 0-system-health — Tasks

## Milestones

- **M1 — Skeleton:** Registry + scheduler + endpoints take over from
  `0-web-app-host` stubs. Single `PostgresHealthProbe` ships. Readiness
  returns 503 during startup.
- **M2 — Core Behavior:** Full probe set (bus, object store, timeseries,
  disk space), timeout enforcement, detailed endpoint with RBAC gating,
  `SystemHealthProbeExtension` discovery, overall-status event emission.
- **M3 — Hardening:** Perf validation, property tests, dashboards,
  out-of-tree probe extension example, scheduler supervisor for crashed
  threads.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Create `source/site/automojo/pychestrate/webservice/system_health/` package skeleton per design.md.
- [ ] T1.2 — Implement `system_health/config.py::HealthConfig` (probe_worker_count=4, detailed-permission name).
- [ ] T1.3 — Implement `system_health/registry.py` with `ProbeRecord`, `ProbeKind`, `ProbeResult`, `HealthSnapshot`, and duplicate-name `SemanticError`.
- [ ] T1.4 — Implement `system_health/scheduler.py` with a dedicated `ThreadPoolExecutor(max_workers=4)`, per-probe interval scheduling, and timeout enforcement via `future.result(timeout=...)`.
- [ ] T1.5 — Implement `system_health/endpoints.py` with `/__health/live`, `/__health/ready`, `/__health/detailed` handlers reading from `HealthSnapshot`.
- [ ] T1.6 — Implement `system_health/hooks.py` startup hook priority `50` that unregisters the `0-web-app-host` stubs and registers the real handlers plus the built-in `PostgresHealthProbe`.
- [ ] T1.7 — Implement `PostgresHealthProbe` at `source/site/automojo/extensions/pychestrate/system_health/postgres.py` (liveness, interval 10s, timeout 2s).
- [ ] T1.8 — Wire readiness `503 {"status":"starting"}` while the host's startup hooks have not all completed.

### M2 — Core Behavior

- [ ] T2.1 — Implement `MessageBusHealthProbe` (readiness), `ObjectStoreHealthProbe` (readiness), `TimeseriesHealthProbe` (informational), `DiskSpaceHealthProbe` (readiness with 90% threshold).
- [ ] T2.2 — Implement `SystemHealthProbeExtension` base class and discover subclasses via `E-resource-extensions` (Phase 0.5); Phase 0 loads the five in-tree probes directly.
- [ ] T2.3 — Enforce `pychestrate.system_health.detailed` RBAC permission on `/__health/detailed`; define the permission under `1-rbac` once that ships.
- [ ] T2.4 — Implement `system_health/aggregator.py` computing overall status (`ok | degraded | failing`) and publishing `system_health.overall.changed` on transition.
- [ ] T2.5 — Implement per-probe failure/recovery events `system_health.probe.failed` / `system_health.probe.recovered`.
- [ ] T2.6 — Implement scheduler backlog drop with `pychestrate.system_health.scheduler.backlog` log (1/min rate limit).
- [ ] T2.7 — Wire Prometheus metrics from design.md Observability.
- [ ] T2.8 — Implement shutdown hook: stop scheduler, join with 5s budget.

### M3 — Hardening

- [ ] T3.1 — Benchmark NFR-1: `/__health/live` p99 < 5 ms, `/__health/ready` p99 < 20 ms, `/__health/detailed` p99 < 100 ms. Fail CI on regression.
- [ ] T3.2 — Implement scheduler supervisor that restarts crashed worker threads and emits `system_health.scheduler.crashed`.
- [ ] T3.3 — Truncate `last_error` to 512 chars at probe-result construction time.
- [ ] T3.4 — Document probe authoring and the `SystemHealthProbeExtension` contract under `usersguide/system_health/`.
- [ ] T3.5 — Add trace span `pychestrate.system_health.probe.run` with `probe`, `kind`, `status`, `duration_ms` attributes.
- [ ] T3.6 — Verify multiline error messages use `os.linesep.join([...])`.
- [ ] T3.7 — Add CI lint forbidding probe implementations from importing `secrets_vault` clients unless the probe declares `secrets_vault` in its extension manifest (prevents accidental secret leakage in `details`).

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement in requirements.md (Requirements 1–4).
- [ ] TT-2 — Property-based tests implementing Property 1 (readiness = AND of probes) and Property 2 (no concurrent probe runs), 1000 cases each.
- [ ] TT-3 — Integration test: start the service with Postgres reachable but object store driver unreachable; assert `/__health/ready` is `503` listing the object-store probe, `/__health/live` is `200`, and on object-store recovery readiness flips to `200`.
- [ ] TT-4 — Extension-point test: a sample `pychestrate-ext-example-probe` package ships a `SystemHealthProbeExtension` subclass that probes a fake external endpoint; assert it appears in `/__health/detailed` with correct scheduling cadence.
- [ ] TT-5 — Chaos test: make a probe sleep 60s with timeout 2s; assert the probe records `status="fail"`, `last_error="probe timeout"`, and does NOT block other probes.
- [ ] TT-6 — Auth test: unauthenticated request to `/__health/detailed` returns 401/403; authenticated without `pychestrate.system_health.detailed` returns 403; with permission returns 200.

## Definition of Done

- [ ] All EARS requirements have passing acceptance tests
- [ ] Property-based tests pass across 1000+ generated cases each
- [ ] Extension surface (if any) has at least one in-tree reference
      implementation and one test-only override using a different `PRECEDENCE`
      (Resource extensions have no PRECEDENCE — the test uses a different
      `name` instead, per `automojo-extension` resource semantics.)
- [ ] Metrics / logs / traces emitted per requirements.md NFR-3
- [ ] Sphinx docs generated for public and internal APIs
- [ ] Code conforms to AGENTS.md coding standards (no mutable defaults,
      explicit returns, named parameter passing, type hints on every param,
      no behavior-modifying decorators)
- [ ] No TODO / FIXME left in shipped code
- [ ] Feature listed in the Definition of Done for its owning phase in
      specs/implementation-plan.md
