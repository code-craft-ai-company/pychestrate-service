# 0-web-app-host — Tasks

## Milestones

- **M1 — Skeleton:** The existing `app_pychestrate_main.py` scaffold is
  refactored into the `host/` package with typed registration APIs and
  deterministic startup ordering. The service binds a port, responds to
  `/__health/live`, and exits cleanly on SIGTERM.
- **M2 — Core Behavior:** Middleware chain (request-context, error-boundary,
  access log), shutdown drain, config loading from env + YAML, metric and
  trace emission.
- **M3 — Hardening:** Property-based tests, performance validation against
  NFR-1, docs, dev-mode gating, duplicate-hook detection, and first
  integration with `0-system-health` (handing over `/__health/live`).

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Create `source/site/automojo/pychestrate/webservice/host/` package skeleton with empty modules listed in design.md Component Breakdown.
- [ ] T1.2 — Implement `host/config.py` with `ServiceConfig` dataclass and `load_service_config()` that reads `PYCHESTRATE_*` env vars plus an optional `pychestrate.yaml`.
- [ ] T1.3 — Implement `host/persona.py::establish_pychestrate_app` wrapping `automojo.webworks.webapplication.establish_webapp_persona`.
- [ ] T1.4 — Implement `host/registration.py` with `register_route`, `register_startup_hook`, `register_shutdown_hook`, duplicate-name `SemanticError` enforcement.
- [ ] T1.5 — Implement `host/lifecycle.py::invoke_startup_hooks` and `invoke_shutdown_hooks` with stable `(priority, name)` sort.
- [ ] T1.6 — Implement `host/runner.py::run_pychestrate_server` wrapping `automojo.webworks.wsgi.server.run_server` and installing a SIGTERM handler.
- [ ] T1.7 — Port `app_pychestrate_main.py` to use the new APIs; keep the existing `/` greeting route as a registered route.
- [ ] T1.8 — Wire minimal `host/probes.py` serving `/__health/live` and `/__health/startup` until `0-system-health` ships.

### M2 — Core Behavior

- [ ] T2.1 — Implement `host/middleware/request_context.py` (ULID generation, `X-Request-Id` validation regex, `ContextVar` binding, response header echo).
- [ ] T2.2 — Implement `host/middleware/error_boundary.py` with dev-vs-prod rendering gated on `ServiceConfig.dev_mode`.
- [ ] T2.3 — Emit `pychestrate.webapp.access` log event from the request-context middleware on response.
- [ ] T2.4 — Implement graceful shutdown: stop accepting connections on SIGTERM, drain in-flight up to `shutdown_grace_seconds`, 503 `Retry-After: 5` for racers.
- [ ] T2.5 — Emit lifecycle log events: `startup.begin`, `startup.phase_completed`, `startup.completed`, `shutdown.started`, `shutdown.completed`, `shutdown.forced_cancel`.
- [ ] T2.6 — Register Prometheus metrics listed in design.md Observability and emit them from middleware + lifecycle.
- [ ] T2.7 — Add `pychestrate.webapp.request` and `pychestrate.webapp.startup` trace spans with `request_id` attribute.
- [ ] T2.8 — Publish sphinx docstrings on every public symbol in the host package per AGENTS.md style.

### M3 — Hardening

- [ ] T3.1 — Benchmark cold-start duration on a 4 vCPU reference runner; fail CI if > 2.0s (NFR-1).
- [ ] T3.2 — Benchmark per-request host overhead; fail CI if p99 > 1.5 ms (NFR-1).
- [ ] T3.3 — Confirm dev-mode default is `0`; add CI check that release images strip `PYCHESTRATE_DEV_MODE`.
- [ ] T3.4 — Document the registration API and startup phases in `usersguide/host/` (sphinx).
- [ ] T3.5 — Hand `/__health/live` and `/__health/startup` ownership to `0-system-health` via a priority-sorted registration swap; keep behavior identical.
- [ ] T3.6 — Audit all error messages to ensure they use `os.linesep.join([...])` multiline pattern.

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement in requirements.md (Requirements 1–4).
- [ ] TT-2 — Property-based tests implementing Property 1 (hook ordering stability) and Property 2 (request-id round trip), 1000 cases each.
- [ ] TT-3 — Integration test: start the real server with two registered startup hooks and two routes, hit `/`, SIGTERM, verify drain and exit code 0.
- [ ] TT-4 — Extension-point test: N/A — the host declares no extension points. Instead, add a regression test that `E-extension-host` (once it lands) can register via `register_startup_hook` with priority `10` without duplicate-name conflicts against existing hooks.
- [ ] TT-5 — Chaos test: inject a handler that sleeps longer than `shutdown_grace_seconds` and assert forced cancellation plus log event `shutdown.forced_cancel`.

## Definition of Done

- [ ] All EARS requirements have passing acceptance tests
- [ ] Property-based tests pass across 1000+ generated cases each
- [ ] Extension surface (if any) has at least one in-tree reference
      implementation and one test-only override using a different `PRECEDENCE`
      (N/A for this feature — the host exposes no extension surface)
- [ ] Metrics / logs / traces emitted per requirements.md NFR-3
- [ ] Sphinx docs generated for public and internal APIs
- [ ] Code conforms to AGENTS.md coding standards (no mutable defaults,
      explicit returns, named parameter passing, type hints on every param,
      no behavior-modifying decorators)
- [ ] No TODO / FIXME left in shipped code
- [ ] Feature listed in the Definition of Done for its owning phase in
      specs/implementation-plan.md
