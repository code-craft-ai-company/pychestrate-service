# 4-resource-inventory — Tasks

## Milestones

- **M1 — Skeleton:** Package scaffold, `Resource` model, one hard-coded
  `device` kind, registration endpoint, round-trip REST smoke.
- **M2 — Core Behavior:** `ResourceKindExtension` discovery wired through
  `E-resource-extensions`, four in-tree kinds, state transitions, event
  emission, sensitive-attr routing through `1-secrets-vault`, filtered
  query with per-kind indices.
- **M3 — Hardening:** Perf targets, Hypothesis properties on 1000 cases,
  metrics/log/trace plumbing, `9-admin-ui` tile, audit-log coverage, sample
  out-of-tree kind pack.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Scaffold `source/site/automojo/pychestrate/webservice/resources/inventory/` per design.md Component Breakdown.
- [ ] T1.2 — Add Alembic migration `0010_resources_core` creating `core.resources` with PK, unique partial index `(kind, identity_hash) WHERE state != 'retired'`, index `(kind, state)`, GIN on `tags`.
- [ ] T1.3 — Implement `models.py::Resource` dataclass and `ResourceState` enum.
- [ ] T1.4 — Implement `repository.py::ResourceRepository` with `load`, `load_many`, `save`, `transition`, `query` (no per-kind indices yet).
- [ ] T1.5 — Hard-code a single `DeviceResourceKind` in `kind_registry.py` (extension discovery deferred to T2.1).
- [ ] T1.6 — Implement `service.py::register_resource` with validator + normalizer calls and `ResourceIdentityConflictError` on unique-constraint violation.
- [ ] T1.7 — Add Flask-RestX namespace `api.py` exposing `POST /api/v1/resources` and `GET /api/v1/resources/{id}`; wire permission `resource.inventory.write` / `read`.
- [ ] T1.8 — Emit `entity.resource.registered` through `0-message-bus`.

### M2 — Core Behavior

- [ ] T2.1 — Replace the hard-coded kind with discovery via `E-resource-extensions`; rebuild the registry on `extension.reloaded`.
- [ ] T2.2 — Ship the four reference kinds: `DeviceResourceKind`, `IPAddressResourceKind`, `IPSubnetResourceKind`, `LicenseResourceKind` under `source/site/automojo/extensions/pychestrate/resources/kinds/`.
- [ ] T2.3 — Add `render_public` redaction for sensitive attrs and route sensitive fields through `1-secrets-vault` at registration time.
- [ ] T2.4 — Implement `PATCH /api/v1/resources/{id}` with kind-validated attrs update and version-checked optimistic concurrency.
- [ ] T2.5 — Implement state-transition endpoints `:quarantine`, `:heal`, `:retire` with `ResourceStateTransitionError` on illegal moves; forbid any transition out of `retired`.
- [ ] T2.6 — Emit `entity.resource.quarantined`, `healed`, `retired`, `attributes_updated`.
- [ ] T2.7 — Implement filtered `GET /api/v1/resources?kind=&state=&tags=&<attr>=` with tag-AND semantics and pagination.
- [ ] T2.8 — For each kind, declare `indexed_attrs` and materialize expression indices (`0011_resources_kind_indices`); the query builder uses them.
- [ ] T2.9 — Hook `1-audit-log` into all registration, transition, and attribute-update calls; recorded payload MUST NOT include sensitive cleartext.

### M3 — Hardening

- [ ] T3.1 — Add all metrics from design.md Observability (Prometheus counters / gauges / histograms).
- [ ] T3.2 — Benchmark filtered query p99 < 50 ms on a synthetic 50k inventory; fail CI on regression (NFR-1).
- [ ] T3.3 — Benchmark `POST /api/v1/resources` p99 < 80 ms end to end; fail CI on regression.
- [ ] T3.4 — Add trace spans `pychestrate.resource.register|query|transition`.
- [ ] T3.5 — Ship a sample out-of-tree pack `pychestrate-ext-packetcapture` declaring a `PacketCaptureResourceKind`; integration test it loads and is queryable.
- [ ] T3.6 — Add Inventory tile to `9-admin-ui` showing per-kind counts and recent transitions.
- [ ] T3.7 — Sphinx docs for public + internal APIs under `usersguide/resources/inventory/`.
- [ ] T3.8 — Verify all multiline errors use `os.linesep.join([...])` and no `@retry`-style decorators were introduced.

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement in requirements.md (Requirements 1–4).
- [ ] TT-2 — Hypothesis property-based tests implementing Property 1 (registration round-trip per kind) and Property 2 (identity uniqueness under concurrency), 1000 cases each, against a real Postgres in CI.
- [ ] TT-3 — Integration test: register → quarantine → heal → retire a device, assert the event stream matches `registered, quarantined, healed, retired` and the audit log has the same four entries with the actor.
- [ ] TT-4 — Extension-point test: `TestDeviceResourceKind` (test-only) with lower `PRECEDENCE` overrides the reference kind and is exercised end to end.
- [ ] TT-5 — Concurrent registration stress: 32 threads POST the same `(kind, identity_attrs)`; assert exactly one `201` and thirty-one `409`.

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
