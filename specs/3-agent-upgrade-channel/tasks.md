# 3-agent-upgrade-channel — Tasks

## Milestones

- **M1 — Skeleton:** Draft + sign + single-stage rollout to a
  fixed-set policy; client outcome collection; signed manifest.
- **M2 — Core Behavior:** Multi-stage rollouts, promote/halt/resume,
  percent + ring + canary policies, object-store + GitHub release
  sources, pin API.
- **M3 — Hardening:** Auto-halt threshold, in-use deferral, metrics,
  durable resume, extension-point coverage, docs.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Migration pack: `agent_rollout`, `agent_rollout_stage`,
  `agent_upgrade_offer`, `agent_pod_pin` tables.
- [ ] T1.2 — Enums and DTOs.
- [ ] T1.3 — Declare `UpgradeArtifactSourceProtocol` and
  `RolloutPolicyProtocol` as `FactoryProtocolBase` subclasses with
  `protocol_schema_version = 1`.
- [ ] T1.4 — Implement `ObjectStoreArtifactSource` reference factory.
- [ ] T1.5 — Implement a trivial `FixedSetRolloutPolicy` reference
  factory for M1 (`params={"client_ids": [UUID]}`).
- [ ] T1.6 — `signer.py` — vault-backed release-key signing with
  fingerprint check at startup.
- [ ] T1.7 — `service.start_rollout` (single stage) + REST
  `POST /agent-rollouts:start`.
- [ ] T1.8 — Transport-side `UpgradeOfferFrame` emission per offer
  row; outcome subscriber path on `UpgradeOutcomeFrame`.

### M2 — Core Behavior

- [ ] T2.1 — `orchestrator.py` full multi-stage state machine
  (`promote_rollout`, `halt_rollout`, `resume_rollout`).
- [ ] T2.2 — Implement `PercentRolloutPolicy`, `RingRolloutPolicy`,
  `CanaryFleetRolloutPolicy` reference factories.
- [ ] T2.3 — Implement `GithubReleasesArtifactSource` reference
  factory.
- [ ] T2.4 — `pins.py` with `set_pod_pin`, `delete_pod_pin`,
  `get_pin_map`; REST endpoints for both.
- [ ] T2.5 — `compute_offer_set` honors pin-map strictly (pin mismatch
  silently excludes).
- [ ] T2.6 — Outcome counters + stage-complete auto-transition.
- [ ] T2.7 — Durable resume: on service restart, load ACTIVE stages
  and resume offer emission for un-outcome'd rows.

### M3 — Hardening

- [ ] T3.1 — Auto-halt threshold evaluator + `entity.rollout.halted`.
- [ ] T3.2 — In-use deferral collaborating with `3-pod-lifecycle`
  (subscriber re-evaluates deferred offers on `state=ready`).
- [ ] T3.3 — Emit all metrics listed in design.md Observability.
- [ ] T3.4 — Trace spans `agent_upgrade.announce`,
  `agent_upgrade.collect_outcome`, `agent_upgrade.auto_halt_check`.
- [ ] T3.5 — Audit-log writes for drafted / started / promoted /
  halted / resumed / pin-set / pin-clear.
- [ ] T3.6 — Sphinx docs for REST, factories, signer contract.

## Test Tasks

- [ ] TT-1 — Unit tests for each EARS clause in Requirements 1-3.
- [ ] TT-2 — Hypothesis tests for Property 1 (pin absoluteness),
  Property 2 (failure-threshold halt monotonic), Property 3 (in-use
  deferral preserves run integrity).
- [ ] TT-3 — Integration test: draft rollout -> stage 0 10% ->
  manual promote -> stage 1 100% -> all outcomes SUCCEEDED -> rollout
  COMPLETED; pinned pods untouched throughout.
- [ ] TT-4 — Extension-point test: out-of-tree
  `InternalArtifactRegistrySource` at `PRECEDENCE=80` overrides the
  default and is used.
- [ ] TT-5 — Auto-halt test: inject 30% failures in a 20-client
  stage with threshold 0.2 -> rollout halts; resume requires explicit
  REST action.
- [ ] TT-6 — Integrity test: bad `sha256` from a factory returns
  `sha256_mismatch`; rollout halts with
  `entity.upgrade.integrity_failed`.

## Definition of Done

- [ ] All EARS requirements have passing acceptance tests.
- [ ] Property-based tests pass across 1000+ generated cases each.
- [ ] Both factory protocols have at least two in-tree references at
  distinct `PRECEDENCE` plus a test-only override.
- [ ] Metrics / logs / traces emitted per requirements.md NFR-3.
- [ ] Sphinx docs generated.
- [ ] Code conforms to AGENTS.md coding standards.
- [ ] No TODO / FIXME left in shipped code.
- [ ] Feature listed in the Definition of Done for Phase 10 in
  specs/implementation-plan.md.
