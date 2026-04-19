# 3-pod-definitions — Tasks

## Milestones

- **M1 — Skeleton:** CRUD for a pod definition version 1 with the three
  in-tree validators and three member kinds; REST surface with RBAC.
- **M2 — Core Behavior:** Versioning, soft-delete with in-use check, full
  member-kind extension discovery, validator factory precedence, audit
  log, bus events.
- **M3 — Hardening:** Serializable tx retry, metrics, perf target, extra
  member kinds, extension-point coverage tests.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Migration pack: `pod_definition`, `pod_definition_version`
  tables with indices described in design.md.
- [ ] T1.2 — Ship `pod_spec.schema.json` describing the canonical spec
  shape.
- [ ] T1.3 — Define DTOs `PodSpec`, `PodDefinition`, `PodDefinitionVersion`,
  `ValidationReport`, `ValidationError`, `ValidationWarning` as dataclasses.
- [ ] T1.4 — Declare `PodSpecValidatorProtocol(FactoryProtocolBase)`.
- [ ] T1.5 — Declare `PodMemberKindExtension(ResourceExtension)` with
  required class vars.
- [ ] T1.6 — Implement `IntegrityValidator` at `PRECEDENCE=10`.
- [ ] T1.7 — Implement `LinuxHost`, `NetworkSwitch`, `SyntheticRole`
  reference member kinds.
- [ ] T1.8 — REST router: `POST`/`GET` (single + list). RBAC gated.

### M2 — Core Behavior

- [ ] T2.1 — Implement `MemberKindValidator` and `LinkGraphValidator`
  (precedence 20 and 30).
- [ ] T2.2 — Implement `load_member_kinds` consuming extension host output
  and caching with invalidation on `entity.extension.host_rescan`.
- [ ] T2.3 — Implement `create_pod_definition_version` in a `SERIALIZABLE`
  isolation tx.
- [ ] T2.4 — Soft-delete flow: query `5-run-state-machine` for in-flight
  runs; fail with 409 if any exist.
- [ ] T2.5 — REST: `PUT` (new version), `DELETE` (soft), `GET` by version.
- [ ] T2.6 — Bus publishers `entity.pod.definition_created|updated|deleted`.
- [ ] T2.7 — Audit-log writes with compact `diff_summary`.
- [ ] T2.8 — Ship remaining reference member kinds: `WindowsHost`,
  `SerialConsole`, `PowerDistributionUnit`.

### M3 — Hardening

- [ ] T3.1 — Serializable retry path on `ConcurrentVersionCollision`; at
  most one retry.
- [ ] T3.2 — Emit all metrics in design.md Observability.
- [ ] T3.3 — Trace span `pod_definition.validate`, `.write`, `.read`.
- [ ] T3.4 — Perf validation: create 500 pods with 32 members / 64 links
  each; p99 validation <= 75 ms.
- [ ] T3.5 — Enforce JSON size cap (256 KiB) and per-member attribute cap
  (32 KiB) at the REST boundary with precise rejection reason.
- [ ] T3.6 — Sphinx docs generated for REST, validators, member kinds.

## Test Tasks

- [ ] TT-1 — Unit tests for each EARS clause in Requirements 1-3.
- [ ] TT-2 — Hypothesis tests for Property 1 (validator purity),
  Property 2 (version retention), Property 3 (parent-cycle detection).
- [ ] TT-3 — Integration test: create pod -> bump version -> attempt delete
  while a run references v2 -> delete fails -> run completes -> delete
  succeeds.
- [ ] TT-4 — Extension-point test: a test-only `GpuHostMemberKind` and a
  test-only `QuotaValidator` (`PRECEDENCE=25`) both load, are applied, and
  the `QuotaValidator` rejects a spec exceeding a configured member cap.
- [ ] TT-5 — Negative test: spec referencing unknown member kind returns
  `UnknownMemberKind` with the missing kind name.

## Definition of Done

- [ ] All EARS requirements have passing acceptance tests.
- [ ] Property-based tests pass across 1000+ generated cases each.
- [ ] `pod_spec_validator` factory has at least three in-tree
  implementations at distinct `PRECEDENCE` values plus one test-only
  override.
- [ ] `PodMemberKindExtension` has six in-tree reference kinds plus one
  test-only kind.
- [ ] Metrics / logs / traces emitted per requirements.md NFR-3.
- [ ] Sphinx docs generated for public REST and internal API.
- [ ] Code conforms to AGENTS.md coding standards.
- [ ] No TODO / FIXME left in shipped code.
- [ ] Feature listed in the Definition of Done for Phase 2 in
  specs/implementation-plan.md.
