# 5-job-envelope — Tasks

## Milestones

- **M1 — Skeleton:** `JobEnvelope` schema, canonical JSON, Ed25519
  signer/verifier, persistence, startup hook that loads a dev
  signing key. Builds a signed envelope end-to-end without
  extensions.
- **M2 — Core Behavior:** `EnvelopeFieldExtension` resource extension
  registry, in-tree `TestBaseBuildInfoField` and `TestBasePipelineField`,
  JWKS rotation, scoped-secret minting via `1-secrets-vault`,
  `entity.run.dispatched` emission, repository + audit-log
  subscriber.
- **M3 — Hardening:** Constant-time verify, property tests,
  perf validation against NFR-1, schema-version error path,
  reconciliation re-verify flow, dashboards and alerts.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Create `jobs/envelope/` package skeleton per design.md Component Breakdown.
- [ ] T1.2 — Implement `jobs/envelope/schema.py::JobEnvelope` Pydantic model with `additionalProperties: false`; cover all required fields in Requirement 1 AC #1.
- [ ] T1.3 — Implement `jobs/envelope/canonical.py` RFC8785 JCS serializer + matching parser.
- [ ] T1.4 — Implement `jobs/envelope/signer.py` Ed25519 sign/verify helpers (PyNaCl or cryptography library).
- [ ] T1.5 — Implement `jobs/envelope/codec.py::EnvelopeCodec` `build`, `sign`, `serialize_canonical`, `parse`.
- [ ] T1.6 — Implement `jobs/envelope/repository.py::JobEnvelopeRepository` writing the `job_envelope` Postgres table.
- [ ] T1.7 — Register `envelope_startup_hook` at web-app startup priority `40` — loads the signing key from `1-secrets-vault` (env fallback under `PYCHESTRATE_DEV_MODE`).
- [ ] T1.8 — Implement `jobs/envelope/errors.py` with the full error hierarchy.

### M2 — Core Behavior

- [ ] T2.1 — Implement `jobs/envelope/field_registry.py::EnvelopeFieldRegistry` collecting `EnvelopeFieldExtension` subclasses via `E-resource-extensions`.
- [ ] T2.2 — Declare `EnvelopeFieldExtension` base at `jobs/envelope/extensions/envelope_field.py`; enforce unique `field_name` at load time.
- [ ] T2.3 — Implement `TestBaseBuildInfoField` reference extension under `source/site/automojo/extensions/pychestrate/envelope_fields/test_base_build_info.py`.
- [ ] T2.4 — Implement `TestBasePipelineField` reference extension at the same path.
- [ ] T2.5 — Add scoped-secret minting through `1-secrets-vault`'s short-lived-cred interface; clamp TTL to `hard_deadline_at + 300 s`.
- [ ] T2.6 — Publish `entity.run.dispatched` on `0-message-bus` after successful sign + persist.
- [ ] T2.7 — Implement `jobs/envelope/verifier.py` constant-time verify (no early-return on payload mismatch).
- [ ] T2.8 — Implement JWKS resolver (local-first, network-cached) and honor `signing_key.rotated` events.

### M3 — Hardening

- [ ] T3.1 — Wire `max_envelope_age` and `max_extension_claims_bytes` enforcement; reject over-limit envelopes with `SemanticError`.
- [ ] T3.2 — Emit Prometheus metrics and OTel trace spans per design.md Observability section.
- [ ] T3.3 — Benchmark NFR-1: `build` p99 < 4 ms, `sign` p99 < 2 ms, `verify` p99 < 2 ms at 64 KiB payload; fail CI on regression.
- [ ] T3.4 — Implement reconciliation re-verify entry point consumed by `5-cancel-reconcile`.
- [ ] T3.5 — Wire `1-audit-log` subscriber for `pychestrate.job_envelope.signed` and `pychestrate.job_envelope.verify.failed`.
- [ ] T3.6 — Enforce rate-limit `max_signatures_per_second_per_client` with a token-bucket; reject overflow with a 429-equivalent internal error.
- [ ] T3.7 — Document envelope schema under `usersguide/jobs/envelope/schema.rst` with every field, each extension claim, and the canonicalization rules.
- [ ] T3.8 — Verify multiline errors use `os.linesep.join([...])`.

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement (Requirements 1–3).
- [ ] TT-2 — Property-based tests implementing Property 1 (tamper detection + constant-time) and Property 2 (canonical round-trip preserves equality), 1000 cases each.
- [ ] TT-3 — Integration test: full build → sign → transmit → client verify → parse round-trip through `3-client-agent-protocol` mock, asserts `entity.run.dispatched` published once.
- [ ] TT-4 — Extension-point test: in-tree `TestBaseBuildInfoField` plus a test-only `XInfraScopeField` registered at test setup; assert both claims appear under `extension_claims` and both are covered by the signature.
- [ ] TT-5 — Negative test: two `EnvelopeFieldExtension` subclasses with the same `field_name` cause `ConfigurationError` at host load time.
- [ ] TT-6 — Rotation test: rotate signing key mid-dispatch; assert in-flight envelopes continue to sign with the loaded key while new envelopes switch to the new `key_id` after `signing_key.rotated` arrives.

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
