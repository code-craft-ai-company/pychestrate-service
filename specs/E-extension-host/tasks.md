# E-extension-host — Tasks

## Milestones

- **M1 — Skeleton:** `ExtensionHost` class exists, `bootstrap()` scans an empty
  namespace and returns an empty snapshot, `get_extension_host()` is wired into
  the app bootstrap, and the `/admin/extensions/snapshot` route returns 200 OK
  with an empty body shape. Proves the wiring.
- **M2 — Core Behavior:** Scanner walks `sys.path`, loads `FactoryExtension`
  and `ResourceExtension` subclasses, enforces PRECEDENCE ordering and
  duplicate detection, exposes the full `SuperFactory` lookup surface, and
  supports live re-scan. Service bootstraps against a real in-tree sample
  extension pack.
- **M3 — Hardening:** Fail-closed validation, strict/permissive modes,
  structured metrics/logs/traces, admin route RBAC + audit, concurrency-safe
  rescan, and documentation generated for the public host API.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Create the package tree under
  `source/site/automojo/pychestrate/webservice/extension/host/` with empty
  `__init__.py`, `host.py`, `scanner.py`, `registries.py`, `snapshot.py`,
  `failures.py`, `admin_routes.py`.
- [ ] T1.2 — Implement `ExtensionHostSnapshot` dataclass in `snapshot.py` with
  the fields listed in design.md and a `snapshot_digest()` helper (SHA-256
  over sorted qualnames + PRECEDENCE).
- [ ] T1.3 — Implement `ExtensionHost.__init__` and a no-op `bootstrap()` that
  returns an empty snapshot; add `get_extension_host()` module-level function
  that raises `SemanticError` before bootstrap.
- [ ] T1.4 — Wire host construction into the `automojo-webworks` app factory so
  it runs after the message bus comes up.
- [ ] T1.5 — Add the `GET /admin/extensions/snapshot` route under
  `admin_routes.py` returning the empty snapshot shape.

### M2 — Core Behavior

- [ ] T2.1 — Implement `scan_pychestrate_namespaces(scan_paths=...)` in
  `scanner.py` walking `automojo/factories/pychestrate` and
  `automojo/extensions/pychestrate` trees.
- [ ] T2.2 — Implement `load_factory_extension_types` and
  `load_resource_extension_types` with defensive `__module__` checks to avoid
  re-loading imported-from-elsewhere symbols.
- [ ] T2.3 — Implement typed registries in `registries.py`: ordered factory
  chain sorted by `PRECEDENCE` asc and tie-broken by qualname; resource
  collections grouped by declared base type.
- [ ] T2.4 — Implement `create_instance_by_order`, `create_instance_for_each`,
  `get_override_types_by_order`, `iterate_override_types_for_each` mirroring
  the upstream `SuperFactory` signatures with named-parameter passing.
- [ ] T2.5 — Add duplicate-precedence detection at register time; raise
  `ConfigurationError` with the offending class qualnames.
- [ ] T2.6 — Implement `rescan()` with a non-blocking `asyncio.Lock` so
  concurrent admin triggers return 409 rather than colliding.
- [ ] T2.7 — Add `POST /admin/extensions/rescan` route with permission
  `extensions.rescan` gating; emit audit-log entry on success.
- [ ] T2.8 — Ship a minimal in-tree sample module under
  `source/site/automojo/factories/pychestrate/_samples/` wired to prove the
  host loads something.

### M3 — Hardening

- [ ] T3.1 — Implement strict vs permissive modes driven by
  `PYCHESTRATE_EXTENSION_SCAN_MODE` env var, with aggregated multiline
  `ConfigurationError` messages via `os.linesep.join`.
- [ ] T3.2 — Emit Prometheus metrics listed in design.md Observability.
- [ ] T3.3 — Emit structured log events and OpenTelemetry trace spans listed
  in design.md.
- [ ] T3.4 — Implement `ExtensionCallError` reclassification wrapper around
  every outbound extension callable.
- [ ] T3.5 — Generate Sphinx docs for the public `ExtensionHost` API and link
  from the Layer E index in `E-extension-docs`.
- [ ] T3.6 — Add a `snapshot_digest`-diff CLI one-liner to
  `development/dev-harness` so operators can compare snapshots across nodes.
- [ ] T3.7 — Add a failure-injection flag for local debugging so developers
  can force-fail a given module at scan time.
- [ ] T3.8 — Remove all TODO/FIXME markers and run the repo's lint + type
  checks.

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement in requirements.md.
- [ ] TT-2 — Property-based tests implementing Property 1 (deterministic
  precedence), Property 2 (atomic load), Property 3 (rescan idempotence) at
  1000 cases each.
- [ ] TT-3 — Integration test: boot a fresh service with a synthetic two-pack
  extension set, observe the correct chain, trigger `rescan` with a new pack
  on disk, observe addition without restart.
- [ ] TT-4 — Extension-point test: sample out-of-tree package
  `pychestrate-ext-sample-host` registers a `FactoryExtension` and a
  `ResourceExtension`, both appear in the snapshot, and an override pack with
  a different `PRECEDENCE` wins over the sample.

## Definition of Done

- [ ] All EARS requirements have passing acceptance tests.
- [ ] Property-based tests pass across 1000+ generated cases each.
- [ ] Sample in-tree factory and resource extension each have a reference
  implementation and a test-only override with a different `PRECEDENCE`.
- [ ] Metrics / logs / traces emitted per requirements.md NFR-3.
- [ ] Sphinx docs generated for `ExtensionHost` and the scanner helpers.
- [ ] Code conforms to AGENTS.md coding standards (no mutable defaults,
      explicit returns, named parameter passing, type hints on every param,
      no behavior-modifying decorators).
- [ ] No TODO / FIXME left in shipped code.
- [ ] Feature listed in the Phase 0.5 exit criterion in
      specs/implementation-plan.md.
