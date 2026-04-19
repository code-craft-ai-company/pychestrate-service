# 3-client-registry — Tasks

## Milestones

- **M1 — Skeleton:** Row creation on enroll, lookup by three keys, admin
  read REST, core attribute extension base.
- **M2 — Core Behavior:** Heartbeat-driven updates, attribute validation via
  extensions, diff events, REST admin writes, bus subscriber wiring.
- **M3 — Hardening:** Concurrency / optimistic-lock handling, metrics, audit
  hooks, perf target, extension-point coverage.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Extend `client` table with `last_seen`, `liveness_state`,
  `last_agent_version`, `transport_name`, `degraded_at`, `revision_token`
  via a migration pack.
- [ ] T1.2 — Add `client_attribute` table with `(client_id, kind)` unique
  constraint.
- [ ] T1.3 — Declare `ClientAttributeExtension(ResourceExtension)` with
  required class vars `attribute_kind_name`, `value_schema`, `display_label`,
  `searchable`.
- [ ] T1.4 — Implement `OsKindAttribute`, `CpuArchAttribute`,
  `ConcurrencyAttribute` as reference in-tree extensions.
- [ ] T1.5 — Implement `ClientRegistryRepository` with `get_by_id`,
  `get_by_scope`, `get_by_cert_serial`, `list_clients`.
- [ ] T1.6 — Implement `ClientRegistry.get_*` API with `ClientNotFound`
  propagation.
- [ ] T1.7 — Admin REST `GET /api/v1/clients` and `GET /api/v1/clients/{id}`.

### M2 — Core Behavior

- [ ] T2.1 — `load_attribute_kinds` walks the extension host and returns a
  typed map; fail-fast on duplicate `attribute_kind_name`.
- [ ] T2.2 — `apply_heartbeat` guarded UPDATE (only if `:received_at >
  last_seen`), updates transport_name + agent_version atomically.
- [ ] T2.3 — Subscribers for `entity.client.enrolled`,
  `entity.client.heartbeat`, `entity.client.liveness_changed`,
  `entity.client.revoked`.
- [ ] T2.4 — `update_attributes` validates every value against extension
  `value_schema` before any write; all-or-nothing per request.
- [ ] T2.5 — Diff emitter: compute `added`, `removed`, `modified` sets on
  attribute change and publish `entity.client.attributes_changed`.
- [ ] T2.6 — Admin REST `PUT /api/v1/clients/{id}/attributes` gated by
  `client.registry.admin`; audit-logged.
- [ ] T2.7 — Publish `entity.client.registered` after initial row insert so
  downstream features (UI, dispatcher cache) can prime.

### M3 — Hardening

- [ ] T3.1 — Optimistic-lock path using `revision_token`: detect collision,
  retry once with refreshed read, then fail to
  `entity.client.registry_write_failed`.
- [ ] T3.2 — Emit all metrics in design.md Observability; wire dashboard
  JSON under `docs/observability/client_registry.json`.
- [ ] T3.3 — Trace spans `client_registry.read`, `client_registry.write`,
  `client_registry.attribute_update`.
- [ ] T3.4 — Perf validation: 10k-client fleet seed, sustain 5000
  heartbeat updates/sec for 10 min with p99 write <= 15 ms.
- [ ] T3.5 — Attribute blob cap (16 KiB) enforced with a clear rejection
  reason.
- [ ] T3.6 — Handling of unloaded attribute kinds: values retained but
  flagged `kind_stale=true`; surface in admin UI response.

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS clause in Requirements 1-4.
- [ ] TT-2 — Hypothesis tests for Property 1 (monotonic `last_seen`),
  Property 2 (all-or-nothing attribute updates), Property 3 (cross-key
  lookup agreement).
- [ ] TT-3 — Integration test: enroll 50 clients, drive 1000 random
  heartbeat + attribute updates concurrently, assert registry end-state
  matches the deterministic reducer.
- [ ] TT-4 — Extension-point test: a test-only `GpuModelAttribute` at
  `attribute_kind_name="gpu_model"` with schema
  `{"vendor": str, "model": str, "memory_gib": int}` is discovered,
  accepted, and usable in filter queries.
- [ ] TT-5 — Schema-violation test: submitting `{"family": "bsd"}` for
  `os` attribute rejects the entire request.

## Definition of Done

- [ ] All EARS requirements have passing acceptance tests.
- [ ] Property-based tests pass across 1000+ generated cases each.
- [ ] `ClientAttributeExtension` has three in-tree reference kinds and one
  test-only override kind.
- [ ] Metrics / logs / traces emitted per requirements.md NFR-3.
- [ ] Sphinx docs for public REST surface and internal service API.
- [ ] Code conforms to AGENTS.md coding standards.
- [ ] No TODO / FIXME left in shipped code.
- [ ] Feature listed in the Definition of Done for Phase 2 in
  specs/implementation-plan.md.
