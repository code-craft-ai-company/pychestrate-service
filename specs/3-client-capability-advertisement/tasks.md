# 3-client-capability-advertisement — Tasks

## Milestones

- **M1 — Skeleton:** Full-replace advertisement path; three reference
  kinds; REST read; matcher with boolean predicates.
- **M2 — Core Behavior:** Delta advertisements, all five reference kinds,
  sensitive-value handling via vault, dispatch matcher used by
  `5-job-dispatch`.
- **M3 — Hardening:** Metrics, audit, perf target, extension-point
  coverage, docs.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Migration pack: `client_capability`,
  `client_capability_revision` tables with indices.
- [ ] T1.2 — Declare `CapabilityKindExtension(ResourceExtension)`.
- [ ] T1.3 — Implement `ToolchainCapability`,
  `PodMemberOwnershipCapability`, `ConcurrencyCapability` reference
  kinds.
- [ ] T1.4 — `load_capability_kinds` cached map; fail-fast on duplicate
  names.
- [ ] T1.5 — `service.apply_advertisement` full-replace path with
  per-value validation and transactional write.
- [ ] T1.6 — Transport handler for `CapabilityAdvertisementFrame`.
- [ ] T1.7 — REST read: `GET .../capabilities` (non-sensitive).
- [ ] T1.8 — `matcher.find_clients_matching` supporting `has(kind)` and
  `kind.path = value` predicates with SQL compilation.

### M2 — Core Behavior

- [ ] T2.1 — Extend advertisement frame + `apply_advertisement` to
  handle `delta.add|modify|remove`.
- [ ] T2.2 — Implement `AcceleratorCapability` and
  `AgentFeatureFlagCapability` (sensitive=true).
- [ ] T2.3 — Sensitive-value storage via `1-secrets-vault`: write
  `sensitive_ref`, never materialize in `value_json`.
- [ ] T2.4 — Admin REST path `GET .../capabilities/sensitive` with
  audit log.
- [ ] T2.5 — `client.revoked` subscriber deletes capability rows.
- [ ] T2.6 — `extension.host_rescan` subscriber refreshes the kind map.
- [ ] T2.7 — Expand matcher predicates: `range` on numeric fields,
  `in` on string arrays.

### M3 — Hardening

- [ ] T3.1 — Emit all metrics listed in design.md Observability.
- [ ] T3.2 — Trace spans `client_capability.apply`,
  `client_capability.match`.
- [ ] T3.3 — Perf validation: match p99 <= 15 ms on 10k-client fleet
  with 50 caps avg; apply p99 <= 25 ms for 200 caps.
- [ ] T3.4 — Advertisement body cap (1 MiB) + per-value
  `max_value_bytes` enforced at frame handler.
- [ ] T3.5 — Audit-log write on every admin sensitive-value read.
- [ ] T3.6 — Sphinx docs for kind extensions, predicate grammar,
  internal API.

## Test Tasks

- [ ] TT-1 — Unit tests for each EARS clause in Requirements 1-3.
- [ ] TT-2 — Hypothesis tests for Property 1 (delta equivalence),
  Property 2 (dispatch eligibility monotonic under liveness),
  Property 3 (unknown-kind rejection totality).
- [ ] TT-3 — Integration test: two clients advertise different
  capabilities, dispatcher's matcher picks the right one against a
  predicate; client goes lost and is excluded.
- [ ] TT-4 — Extension-point test: out-of-tree
  `GpuMemoryBudgetCapability` at `capability_kind_name=
  "gpu_memory_budget"` participates in apply + match without special
  casing.
- [ ] TT-5 — Sensitive-value test: non-admin read returns rows for a
  sensitive kind but omits the value; admin read returns the value
  and writes an audit entry.

## Definition of Done

- [ ] All EARS requirements have passing acceptance tests.
- [ ] Property-based tests pass across 1000+ generated cases each.
- [ ] `CapabilityKindExtension` has five in-tree references plus one
  test-only override.
- [ ] Metrics / logs / traces emitted per requirements.md NFR-3.
- [ ] Sphinx docs generated.
- [ ] Code conforms to AGENTS.md coding standards.
- [ ] No TODO / FIXME left in shipped code.
- [ ] Feature listed in the Definition of Done for Phase 2 in
  specs/implementation-plan.md.
