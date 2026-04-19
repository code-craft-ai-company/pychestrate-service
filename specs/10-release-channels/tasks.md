# 10-release-channels — Tasks

## Milestones

- **M1 — Skeleton:** `releases`, `channel_state`, `release_stage_events`,
  `consumer_outcomes`, `trusted_issuer_keys` tables; `ReleaseAspects`;
  `release_channel_policy` factory protocol; `HashRingChannelPolicy`;
  manifest signer subprocess; `publish_release` end-to-end on
  `canary`; REST + CLI publish.
- **M2 — Core Behavior:** `promote_release` with monotonic fraction,
  bake windows, `rollback_channel` with previous-release restoration,
  cascading agent rollback, consumer outcome ingestion, auto-demote on
  stage failure threshold, manifest verification surface exposed to
  `3-agent-upgrade-channel` and the service self-update path.
- **M3 — Hardening:** Metrics / logs / traces, rate limiting on the
  outcome endpoint, signer process isolation review, Sphinx docs for
  the `release_channel_policy` contract, out-of-tree policy
  extension exercised end-to-end.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Land `releases`, `channel_state`, `release_stage_events`,
      `consumer_outcomes`, `trusted_issuer_keys` tables via an
      `EntityMigrationExtension` pack.
- [ ] T1.2 — Implement `ReleaseAspects` dataclass and
      `build_default_release_aspects()` (no mutable defaults).
- [ ] T1.3 — Declare `ReleaseChannelPolicyProtocol`
      `FactoryProtocolBase` with `protocol_schema_version = 1`.
- [ ] T1.4 — Ship `HashRingChannelPolicy` at `PRECEDENCE = 1000`
      claiming every channel (default fallback).
- [ ] T1.5 — Implement `manifest_signer_worker` dedicated signer
      subprocess; load the private key from
      `1-secrets-vault` at boot; expose a line-oriented IPC.
- [ ] T1.6 — Implement `manifest_signer.sign_manifest` + redacted
      stderr wrapper.
- [ ] T1.7 — Implement `manifest_verifier.verify_manifest` against
      `trusted_issuer_keys` with rotation lineage support.
- [ ] T1.8 — Implement `release_service.publish_release` end-to-end
      for `canary` with initial fraction 0.05; emit
      `entity.release.published` + `entity.release.canary_started`.
- [ ] T1.9 — Wire REST `POST /api/v1/ops/release/releases`, `GET
      /api/v1/ops/release/releases[/{id}]`, `GET
      /api/v1/ops/release/manifests/{component}/{channel}/current`.
- [ ] T1.10 — Wire `pychestrate release publish|list` CLI commands.

### M2 — Core Behavior

- [ ] T2.1 — Implement `promote_release` with monotonic fraction
      enforcement (raise `SemanticError` on regression) and bake
      windows (canary -> beta 3600s, beta -> stable 86400s), with
      `system:release.bypass_bake` override.
- [ ] T2.2 — Implement `stage_machine` transitions and append every
      transition to `release_stage_events`.
- [ ] T2.3 — Implement `rollback_channel` as first-class: demote
      current to 0.0, swap `channel_state.previous_release_id` back
      to `current_release_id`, emit `entity.release.rolled_back`.
- [ ] T2.4 — Implement cascading agent rollback path when
      `ReleaseAspects.include_cascading_agent_rollback = True` and
      `component = SERVICE`.
- [ ] T2.5 — Implement `record_consumer_outcome` endpoint
      (`POST /api/v1/ops/release/consumers/{consumer_id}/outcomes`)
      with mTLS-based consumer auth.
- [ ] T2.6 — Implement `auto_demote` watcher: rolling failure rate
      across eligible consumers exceeding `stage_failure_threshold`
      triggers internal `rollback_channel` with
      `reason="auto_failure_threshold"` and fires the
      `pychestrate.release.rolled_back` alert.
- [ ] T2.7 — Implement `policy_router.resolve_policy` with precedence
      tie-break error at startup and runtime fallback to
      `HashRingChannelPolicy` on policy errors (emit
      `entity.release.policy_fallback`).
- [ ] T2.8 — Subscribe to `entity.client.heartbeat`; for agent-component
      releases, update `consumer_outcomes` from the agent version
      reported in the heartbeat.
- [ ] T2.9 — Expose `verify_manifest` in `8-plugin-api` so
      `3-agent-upgrade-channel` and the service self-updater share the
      same verification entry point.

### M3 — Hardening

- [ ] T3.1 — Emit every metric in requirements.md NFR-3 and add the
      trace spans (`release.publish`, `release.promote`,
      `release.rollback`, `release.policy.evaluate`,
      `release.manifest.sign`, `release.manifest.verify`,
      `release.auto_demote`).
- [ ] T3.2 — Add rate limiting on
      `POST /consumers/{id}/outcomes` per consumer id (default 30
      rpm).
- [ ] T3.3 — Implement `entity.secret.rotated` subscriber that picks
      up a new signing key for the signer subprocess and appends to
      `trusted_issuer_keys` with `replaced_by` lineage.
- [ ] T3.4 — Add multi-line error messages built via
      `os.linesep.join(...)` per design.md Error Handling.
- [ ] T3.5 — Generate Sphinx docs for public and internal APIs and
      the `release_channel_policy` contract.
- [ ] T3.6 — Security review of the signer subprocess (seccomp,
      file-descriptor hygiene, stderr redactor); document in
      usersguide.
- [ ] T3.7 — Ship an out-of-tree `pychestrate-ext-release-policy-ring`
      example package registering a region-ring policy at
      `PRECEDENCE = 500` claiming `canary`; the integration suite
      confirms the override takes effect.
- [ ] T3.8 — Run a full cycle: publish agent 1.42.0 canary, promote
      to beta, promote to stable, verify via
      `3-agent-upgrade-channel` that the right consumers receive the
      right versions at each fraction, then rollback and verify
      pre-canary state is restored.

## Test Tasks

- [ ] TT-1 — Unit tests covering every EARS acceptance criterion in
      Requirements 1–4 (signing / bake / promote / rollback / policy
      fallback).
- [ ] TT-2 — Hypothesis property tests: Property 1 (canary abort
      fully restores pre-canary state), Property 2 (manifest
      signature is required and sufficient — every mutation rejected,
      untouched manifests accepted), Property 3 (promotion is
      monotonic within a stage), 1000 cases each.
- [ ] TT-3 — Integration test against `3-agent-upgrade-channel`:
      publish agent canary, assert only the ring-selected 5% of
      registered clients receive the new manifest and that pinned
      pods are silently excluded. Then rollback via
      `rollback_channel` and assert every non-pinned client converges
      back to the prior version on the next heartbeat.
- [ ] TT-4 — Extension-point test: out-of-tree
      `pychestrate-ext-release-policy-ring` at `PRECEDENCE = 500`
      registers and receives the canary compute call; in-tree default
      handles non-canary channels.
- [ ] TT-5 — Signer isolation test: confirm the signer private key
      does not appear in any REST handler process's memory map, that
      stderr emission containing a base64 blob shaped like the key is
      redacted, and that killing the signer subprocess produces
      `ReleaseSigningKeyUnavailableError` on publish.
- [ ] TT-6 — Cascading rollback test: publish service canary + agent
      canary on the same channel, force an auto-demote on the service
      release with `include_cascading_agent_rollback = True`, assert
      the agent rollback is emitted within the same run and visible
      to `3-agent-upgrade-channel`.

## Definition of Done

- [ ] All EARS requirements have passing acceptance tests
- [ ] Property-based tests pass across 1000+ generated cases each
- [ ] Extension surface has at least one in-tree reference
      implementation (`HashRingChannelPolicy`) and one test-only
      override using a different `PRECEDENCE`
- [ ] Metrics / logs / traces emitted per requirements.md NFR-3
- [ ] Rollout shape honors NFR-1 (canary 5%, beta 25%, stable 100%,
      1h canary bake, 24h beta bake, 10% auto-demote threshold)
- [ ] `3-agent-upgrade-channel` end-to-end test passes against this
      feature's manifest surface
- [ ] Sphinx docs generated for public and internal APIs and the
      `release_channel_policy` contract
- [ ] Code conforms to AGENTS.md coding standards (no mutable defaults,
      explicit returns, named parameter passing, type hints on every
      param, no behavior-modifying decorators, Aspects-style behavior
      parameters — no `@retry`)
- [ ] No TODO / FIXME left in shipped code
- [ ] Feature listed in the Definition of Done for Phase 10 — Public
      Surface & Extensibility Completion in
      specs/implementation-plan.md
