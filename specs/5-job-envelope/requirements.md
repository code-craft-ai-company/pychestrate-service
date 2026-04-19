# 5-job-envelope — Requirements

## Introduction

The `5-job-envelope` feature defines the signed dispatch payload that
Pychestrate hands to a pod client when it asks the client to start a job.
The envelope is the single self-contained object that carries every
identity, reference, scoped secret, results location, and deadline the
client needs to run the job without ever calling back for missing
context. It is the bedrock of Layer 5 because every feature downstream —
`5-job-dispatch`, `5-dispatch-receipt`, `5-run-state-machine`,
`5-progress-ingest`, `5-result-ingest-watcher` — pivots on fields it
defines. It ships in **Phase 3** alongside the other minimum-viable run
features and exposes the `EnvelopeFieldExtension` resource extension so
extensions (e.g., infra-scope tokens, SBOM-required claims) can splice
signed, typed fields into envelopes their jobs need. Pychestrate never
spawns job processes; the envelope is handed off, then the client agent
owns every process below it.

## Requirements

### Requirement 1: Canonical Envelope Schema

**User Story:** As a pod client agent author, I want one strict,
versioned envelope schema, so that my client can parse every dispatch
deterministically and reject malformed envelopes before running
anything.

**Acceptance Criteria (EARS):**

1. WHEN `envelope_codec.build(dispatch_request)` is called THEN the
   system SHALL produce a `JobEnvelope` with required top-level fields
   `schema_version`, `envelope_id` (UUIDv7), `issued_at` (RFC3339 UTC),
   `issuer` (service DNS name + release), `project_id`, `job_id`,
   `job_name`, `job_type`, `pipeline` (nullable: `id`, `instance`),
   `run_id`, `client_id`, `pod_id`, `refs` (`branch`, `build`,
   `flavor`, `release`, `commit_sha`), `params` (typed map),
   `scoped_secrets` (materialized short-lived tokens), `results`
   (`backend_key_prefix`, `backend_driver`), `forwarding`
   (`progress_url`, `summary_url`, `auth_method`), `deadline`
   (`soft_deadline_at`, `hard_deadline_at`), and `extension_claims`
   (map keyed by `EnvelopeFieldExtension.field_name`).
2. IF any required field is absent from `dispatch_request` THEN the
   system SHALL raise `SemanticError` naming every missing field in a
   multiline message — envelope construction MUST NOT fall back to
   defaults for structural identifiers.
3. WHEN a caller deserializes an envelope with an unknown
   `schema_version` THEN the system SHALL raise
   `EnvelopeSchemaVersionError` naming both the envelope version and
   the supported version range.
4. WHERE an `EnvelopeFieldExtension` is registered with
   `field_name="x-infra-scope"` the system SHALL serialize its typed
   value under `extension_claims["x-infra-scope"]` AND include the
   field name in the signature payload.
5. WHILE the envelope is in transit the `scoped_secrets` block SHALL
   contain only short-lived tokens (TTL ≤ `hard_deadline_at + 5
   minutes`) — raw vault keys MUST never appear in an envelope.

### Requirement 2: Detached Ed25519 Signing and Verification

**User Story:** As a service operator, I want every envelope signed
with the service's private key and verifiable by the client, so that a
compromised link cannot inject fake dispatch orders into a pod.

**Acceptance Criteria (EARS):**

1. WHEN `envelope_codec.sign(envelope, signing_key)` is called THEN
   the system SHALL emit a `SignedJobEnvelope` containing the canonical
   JSON payload, a detached `Ed25519` signature, and a `key_id` that
   resolves to the signing key in the service's JWKS.
2. WHEN `envelope_codec.verify(signed_envelope, jwks)` is called AND
   any byte of the payload differs from the signed bytes THEN the
   system SHALL return `VerificationResult(valid=False,
   reason="signature_mismatch")` in constant time relative to payload
   size.
3. IF `signed_envelope.signed_at` is older than `max_envelope_age`
   (default 300 seconds at issuance time) at verification THEN the
   system SHALL return `VerificationResult(valid=False,
   reason="expired")`.
4. WHERE the `key_id` is absent from the JWKS the system SHALL return
   `VerificationResult(valid=False, reason="unknown_key")` — never
   crash, never fall through to an alternate key silently.
5. WHEN an envelope is signed THEN the canonical JSON SHALL use
   RFC8785 JCS (JSON Canonicalization Scheme) so order-independent
   serialization does not produce distinct signatures for equivalent
   payloads.

### Requirement 3: Extension-Contributed Signed Claims

**User Story:** As an extension author shipping an infra-orchestration
pack, I want to attach a signed `x-infra-scope` claim to envelopes my
jobs dispatch, so that downstream infra tooling can trust the envelope
as proof of authorization without a second round-trip.

**Acceptance Criteria (EARS):**

1. WHEN the extension host discovers an `EnvelopeFieldExtension`
   subclass THEN the system SHALL register its `field_name`, typed
   schema (`pydantic`-style `BaseModel`), and `required_for_job_types`
   predicate in the envelope registry.
2. WHERE a job's `job_type` matches an extension's
   `required_for_job_types(job_type)` the system SHALL reject
   envelopes that omit that `field_name` with
   `EnvelopeClaimMissingError` naming both the extension and the
   job type.
3. IF two `EnvelopeFieldExtension` subclasses declare the same
   `field_name` THEN the system SHALL raise `ConfigurationError` at
   load time naming both classes — envelope claim keys are a unique
   namespace.
4. WHEN an extension-contributed claim value fails the extension's
   schema validation THEN the system SHALL raise `SemanticError` —
   never sign an envelope with a structurally invalid claim.

## Property-Based Test Requirements

### Property 1: Signature Tampering Detected in Constant Time

- **Invariant:** For any signed envelope `e` and any single-byte
  mutation of its payload, `envelope_codec.verify(e_tampered, jwks)`
  returns `valid=False` with `reason="signature_mismatch"`, and the
  verification wall time variance across mutation positions stays
  within a 5% band of the mean (constant-time property).
- **Generator:** `hypothesis.strategies.builds(JobEnvelope, ...)` with
  random `params` (map of up to 32 typed entries), random
  `extension_claims` (0–4 keys), payload byte length stratified at
  256 B, 2 KiB, 16 KiB, 128 KiB. For each envelope, pick a random
  byte index in `[0, len(payload))` and flip a random bit.
- **Assertion:** every tampered envelope verifies to
  `VerificationResult(valid=False, reason="signature_mismatch")` AND
  timing variance ≤ 5% of mean across mutation positions within each
  size bucket.
- **Sample size:** 1000 generated cases per size bucket (4000 total)

### Property 2: Canonical Round-Trip Preserves Equality

- **Invariant:** For any `JobEnvelope e` produced by `build`,
  `parse(serialize_canonical(e)) == e` AND
  `sign(parse(serialize_canonical(e))) == sign(e)` (same key_id,
  same signature bytes). JSON key ordering must not affect signatures.
- **Generator:** `hypothesis.strategies.builds(JobEnvelope, ...)`
  with shuffled key insertion order in intermediate dicts (via a
  custom strategy that reinserts keys in random order before
  canonicalization).
- **Assertion:** structural and signature equality holds across all
  re-orderings.
- **Sample size:** 1000 generated cases

## Non-Functional Requirements

- **NFR-1 (Performance):** `envelope_codec.build` p99 < 4 ms for
  envelopes ≤ 64 KiB. `envelope_codec.sign` p99 < 2 ms on the service;
  `verify` p99 < 2 ms on the client for payloads ≤ 64 KiB. Envelope
  serialization SHALL NOT exceed 128 KiB absent extension claims —
  extension claims are capped at 64 KiB total via
  `max_extension_claims_bytes`.
- **NFR-2 (Security):** Signing key lives in `1-secrets-vault` and is
  loaded into memory only at process start; rotation is supported by
  overlapping `key_id`s published in the JWKS. `scoped_secrets` MUST be
  minted per-dispatch from `1-secrets-vault`'s short-lived-credential
  interface; TTL capped at `hard_deadline_at + 300 s`; rotation on
  reuse MUST be rejected (`envelope_id` is one-shot). Envelope schema
  validation MUST reject unknown top-level keys (`additionalProperties:
  false`) to prevent smuggling.
- **NFR-3 (Observability):** Emit metrics
  `pychestrate_job_envelope_built_total{project,job_type}` (counter),
  `pychestrate_job_envelope_build_duration_seconds{project,job_type}`
  (histogram), `pychestrate_job_envelope_bytes{project,job_type}`
  (histogram), `pychestrate_job_envelope_signed_total{key_id}`
  (counter), `pychestrate_job_envelope_verify_failures_total{reason}`
  (counter), `pychestrate_job_envelope_extension_claims_total{field_name}`
  (counter). Log events `pychestrate.job_envelope.built`,
  `pychestrate.job_envelope.signed`, `pychestrate.job_envelope.verify.failed`.
  Trace span `pychestrate.job_envelope.build` with attributes
  `project`, `job_type`, `job_id`, `run_id`, `envelope_id`.
- **NFR-4 (Reliability):** A JWKS reload failure MUST NOT block
  envelope issuance for in-flight dispatch requests — the signer
  continues with the already-loaded key and flips a health probe to
  `degraded`. Unknown-key verification on the client side MUST NOT
  retry against a network JWKS endpoint more than once per 60 seconds
  per `key_id`.

## Out of Scope

- Dispatch routing, capability matching, queueing — owned by
  `5-job-dispatch`.
- Client-issued local run id assignment — owned by
  `5-dispatch-receipt`.
- Run state transitions — owned by `5-run-state-machine`.
- Live progress ingestion or result tree parsing.
- Long-term archive of envelopes (only the last N per run are kept in
  hot storage per `2-retention-policies`).

## Dependencies

- **Depends on:** `0-persistence` (envelope archive rows),
  `0-message-bus` (emits `entity.run.dispatched`-adjacent lifecycle
  events), `1-secrets-vault` (signing key + short-lived token mint),
  `2-projects` (project id validation), `3-client-registry`
  (`client_id`, `pod_id`), `E-extension-host`, `E-resource-extensions`
  (envelope field extensions).
- **Depended on by:** `5-job-dispatch`, `5-dispatch-receipt`,
  `5-run-state-machine`, `5-progress-ingest`,
  `5-result-ingest-watcher`, `5-cancel-reconcile`, `5-offline-tolerance`,
  `6-test-orchestration`, `6-build-orchestration`,
  `6-infra-orchestration`.
- **Extension points exposed:** `resource: EnvelopeFieldExtension` —
  see implementation-plan.md Layer 5 section.
