# 5-job-envelope — Design

## Architecture

The envelope subsystem is a small, pure-Python codec layer owned by
`source/site/automojo/pychestrate/webservice/jobs/envelope/`. It sits
at the seam between `5-job-dispatch` (which assembles the
`DispatchRequest`) and the pod client (which receives the
`SignedJobEnvelope` over `3-client-agent-protocol`). The codec is
stateless apart from two singletons loaded at process start: the
active signing key (pulled from `1-secrets-vault`) and the JWKS used
for verification during re-entry tests. Extension-contributed fields
are collected from `EnvelopeFieldExtension` subclasses at service
start and fed into a typed registry the codec consults on every build.
Authoritative source of truth for an envelope's bytes is the signed
artifact itself — once signed, an envelope is immutable; a reissued
envelope is a new record with a new `envelope_id`. This feature lands
in **Phase 3** and must not regress the Phase 0.5 extension host
contract.

## Data Model

Persistent rows (Postgres via `0-persistence`):

- `job_envelope`:
  - `envelope_id: UUID` (PK, UUIDv7)
  - `run_id: UUID` (FK → `run.run_id`, indexed)
  - `project_id: UUID` (FK, indexed)
  - `job_id: UUID`
  - `job_type: str`
  - `schema_version: str`
  - `issued_at: datetime`
  - `signed_at: datetime`
  - `key_id: str` (FK → `signing_key.key_id`)
  - `payload_bytes: bytea` (canonical JSON)
  - `signature_bytes: bytea`
  - `size_bytes: int`
  - `extension_claim_names: text[]` (indexed GIN)
  - `hard_deadline_at: datetime`
  - Unique constraint: `(run_id, envelope_id)`.

- `signing_key`:
  - `key_id: str` (PK)
  - `public_jwk: jsonb`
  - `activated_at: datetime`
  - `retired_at: datetime | None`

In-memory value objects (no DB row):

- `DispatchRequest` — assembled by `5-job-dispatch`, consumed here.
- `JobEnvelope` — validated Pydantic model matching the schema in
  Requirement 1 AC #1.
- `SignedJobEnvelope`:
  - `payload: bytes` (canonical JSON)
  - `signature: bytes` (Ed25519)
  - `key_id: str`
  - `signed_at: datetime`
- `VerificationResult`:
  - `valid: bool`
  - `reason: str | None` (`"ok"`, `"signature_mismatch"`, `"expired"`,
    `"unknown_key"`, `"schema_version"`, `"malformed"`)
  - `envelope: JobEnvelope | None`

## Interfaces

### Public API

N/A — internal. Envelope bytes travel over `3-client-agent-protocol`.

### Internal API

```python
class EnvelopeCodec:
    def __init__(
        self,
        signing_key_loader: SigningKeyLoader,
        jwks_resolver: JwksResolver,
        field_registry: EnvelopeFieldRegistry,
        config: EnvelopeCodecConfig
    ) -> None:
        self._signing_key_loader = signing_key_loader
        self._jwks_resolver = jwks_resolver
        self._field_registry = field_registry
        self._config = config
        return

    def build(
        self,
        dispatch_request: DispatchRequest
    ) -> JobEnvelope:
        """
            Build a JobEnvelope from a DispatchRequest, materializing
            scoped secrets and extension-contributed claims.

            :param dispatch_request: Fully populated dispatch payload
                                     from 5-job-dispatch.

            :returns: JobEnvelope ready to sign.
            :raises: SemanticError, EnvelopeClaimMissingError,
                     ConfigurationError
        """
        ...

    def sign(
        self,
        envelope: JobEnvelope,
        aspects: SignAspects | None = None
    ) -> SignedJobEnvelope:
        """
            Canonicalize and Ed25519-sign an envelope.

            :param envelope: The envelope to sign.
            :param aspects: Behavior parameters (timeout, logging).

            :returns: Signed envelope ready for transport.
            :raises: SigningKeyUnavailableError
        """
        ...

    def verify(
        self,
        signed_envelope: SignedJobEnvelope,
        aspects: VerifyAspects | None = None
    ) -> VerificationResult:
        """
            Verify envelope signature, schema, and freshness. Constant
            time relative to payload size.

            :param signed_envelope: The signed envelope to verify.
            :param aspects: Behavior parameters.

            :returns: VerificationResult.
            :raises: None — all failures map to VerificationResult.
        """
        ...

    def serialize_canonical(
        self,
        envelope: JobEnvelope
    ) -> bytes:
        """
            Produce RFC8785 JCS bytes for an envelope.

            :param envelope: The envelope to serialize.

            :returns: Canonical UTF-8 JSON bytes.
            :raises: SemanticError
        """
        ...

    def parse(
        self,
        payload_bytes: bytes
    ) -> JobEnvelope:
        """
            Parse canonical bytes back into a JobEnvelope.

            :param payload_bytes: Canonical JSON bytes.

            :returns: JobEnvelope.
            :raises: EnvelopeSchemaVersionError, SemanticError
        """
        ...
```

### Extension Surface

Resource extension base class declared here:

```python
class EnvelopeFieldExtension(ResourceExtension):
    """
        Contribute a typed, signed claim to every envelope that
        matches required_for_job_types.
    """
    field_name: str = ""
    schema_model: type[BaseModel] = BaseModel

    @classmethod
    def required_for_job_types(
        cls,
        job_type: str
    ) -> bool:
        """
            Return True if the job_type requires this claim.

            :param job_type: The job's declared type string.

            :returns: True if required, False otherwise.
            :raises: None
        """
        rtnval = False
        return rtnval

    @classmethod
    def materialize(
        cls,
        dispatch_request: DispatchRequest
    ) -> BaseModel:
        """
            Compute the claim value from the dispatch request.

            :param dispatch_request: The dispatch request.

            :returns: A BaseModel instance matching schema_model.
            :raises: SemanticError
        """
        ...
```

Reference implementations shipped in-tree (under
`source/site/automojo/extensions/pychestrate/envelope_fields/`):

- `TestBaseBuildInfoField` — `field_name = "x-build-info"`; mirrors
  testbase's `BuildInfo` block (`branch`, `build`, `flavor`,
  `release`) for every `job_type` starting with `test.`.
- `TestBasePipelineField` — `field_name = "x-pipeline"`; carries
  testbase's `pipeline.id` / `pipeline.instance` for every job
  dispatched as part of a pipeline.

### Events Emitted

On `0-message-bus`:

- `entity.run.dispatched` — `{run_id: UUID, envelope_id: UUID,
  project_id: UUID, pod_id: UUID, client_id: UUID, issued_at:
  datetime}`
- `pychestrate.job_envelope.signed` — internal instrumentation
  (consumed by `1-audit-log`, `7-metrics-ingest`).
- `pychestrate.job_envelope.verify.failed` — emitted when a client
  re-presents an envelope for reconciliation and verification fails
  (consumed by `1-audit-log`).

### Events Consumed

- `extension.reloaded` — rebuilds the `EnvelopeFieldRegistry`.
- `signing_key.rotated` (from `1-secrets-vault`) — rotates the
  active signing key and updates JWKS.

## Component Breakdown

All paths rooted at `source/site/automojo/pychestrate/webservice/`:

- `jobs/envelope/__init__.py`
- `jobs/envelope/schema.py` — `JobEnvelope`, `SignedJobEnvelope`,
  `VerificationResult` Pydantic models with
  `additionalProperties: false`.
- `jobs/envelope/codec.py` — `EnvelopeCodec` facade.
- `jobs/envelope/canonical.py` — RFC8785 JCS serializer/parser.
- `jobs/envelope/signer.py` — Ed25519 signing helper.
- `jobs/envelope/verifier.py` — constant-time verify helper.
- `jobs/envelope/field_registry.py` — `EnvelopeFieldRegistry` built
  from `EnvelopeFieldExtension` subclasses.
- `jobs/envelope/errors.py` — `EnvelopeSchemaVersionError`,
  `EnvelopeClaimMissingError`, `SigningKeyUnavailableError`.
- `jobs/envelope/hooks.py` — startup hook that loads signing key and
  field registry.
- `jobs/envelope/repository.py` — `JobEnvelopeRepository` (persistence).

Extensions live under
`source/site/automojo/extensions/pychestrate/envelope_fields/`.

## Key Flows

### Flow 1 — Build and Sign at Dispatch Time

1. `5-job-dispatch` calls `codec.build(dispatch_request)`.
2. Codec validates every required structural field; missing ones
   raise `SemanticError` with a multiline message.
3. Codec walks `field_registry` and, for each extension that returns
   `required_for_job_types(job.job_type)`, calls `materialize` and
   places the result under `extension_claims[field_name]`.
4. Codec mints `scoped_secrets` short-lived tokens via
   `1-secrets-vault` with TTL clamped to `hard_deadline_at + 300 s`.
5. Codec produces canonical JSON, then `signer.sign` returns
   `SignedJobEnvelope`.
6. Repository persists the `job_envelope` row.
7. `entity.run.dispatched` published on the bus.

### Flow 2 — Client-Side Verify on Receipt

1. Client receives `SignedJobEnvelope` bytes.
2. Client JWKS resolver looks up `key_id`; miss → constant-time
   `unknown_key`.
3. Client calls `verifier.verify(signed_envelope, jwks)`; signature
   check runs over the *full* payload regardless of mismatch position
   (constant-time).
4. On `valid=True`, client parses `JobEnvelope`, extracts
   `results.backend_key_prefix` and `forwarding.*`, and hands off to
   its own runner. No more round trips to Pychestrate for context.

### Flow 3 — Reconciliation Re-Verification

1. On client reconnect (see `5-cancel-reconcile`), client presents
   its stored `SignedJobEnvelope` and local run id.
2. Service re-verifies through `codec.verify`; mismatch publishes
   `pychestrate.job_envelope.verify.failed` and the run is flagged
   `needs_investigation` in `5-run-state-machine`.

## Error Handling

- `SemanticError` (missing required field, invalid claim shape,
  invalid key regex): never caught — bubbles to
  `5-job-dispatch` which fails the dispatch deterministically.
- `EnvelopeSchemaVersionError`: domain error; dispatch aborts and the
  run is marked `dispatch_failed` with reason `schema_version`.
- `EnvelopeClaimMissingError`: domain error; fail the dispatch with a
  multiline message listing the job type and all missing extensions.
- `SigningKeyUnavailableError`: bubbles to caller; dispatcher retries
  after `signing_key.rotated` or health probe recovery.
- `ConfigurationError`: raised at startup when two extensions claim
  the same `field_name`; process exits with non-zero status.
- Verify path never raises — every failure is encoded in
  `VerificationResult.reason`. This is the only tolerated
  exception-to-value translation in the feature and exists because
  verification sits on the critical path of every reconnect.

Example multiline error at build-time:

```python
err_msg_lines = ["Envelope missing extension-required claims."]
err_msg_lines.append("JOB_TYPE: {}".format(job_type))
err_msg_lines.append("REQUIRED CLAIMS:")
for ext_name, field_name in missing:
    err_msg_lines.append("    {} -> {}".format(ext_name, field_name))

err_msg = os.linesep.join(err_msg_lines)
raise EnvelopeClaimMissingError(err_msg) from None
```

## Security Considerations

- Signing key is held only in process memory; backed by
  `1-secrets-vault`. `SigningKeyLoader.__repr__` redacts key bytes.
- All signing operations are audited via `1-audit-log` subscriber on
  `pychestrate.job_envelope.signed`.
- `scoped_secrets` are minted fresh per envelope; reuse of an
  `envelope_id` is rejected by the repository's unique constraint.
- RBAC: envelope *building* is gated at the `5-job-dispatch` layer;
  this feature trusts in-process callers. `verify` is side-effect free
  and needs no auth.
- Canonical schema uses `additionalProperties: false` throughout —
  unknown top-level or nested keys fail parse, preventing a
  compromised extension from smuggling out-of-schema data past the
  signature boundary.
- Rate limiting: envelope signing is capped at
  `max_signatures_per_second_per_client` (default 100) — a burst
  limit protecting the signing key from a compromised dispatch queue.

## Observability

Metrics:

- `pychestrate_job_envelope_built_total{project,job_type}` — counter
- `pychestrate_job_envelope_build_duration_seconds{project,job_type}`
  — histogram
- `pychestrate_job_envelope_bytes{project,job_type}` — histogram
- `pychestrate_job_envelope_signed_total{key_id}` — counter
- `pychestrate_job_envelope_verify_failures_total{reason}` — counter
- `pychestrate_job_envelope_extension_claims_total{field_name}` —
  counter

Log events:

- `pychestrate.job_envelope.built`
- `pychestrate.job_envelope.signed`
- `pychestrate.job_envelope.verify.failed`
- `pychestrate.job_envelope.signing_key.rotated`

Trace span: `pychestrate.job_envelope.build` with attributes
`project`, `job_type`, `job_id`, `run_id`, `envelope_id`,
`extension_claim_count`.

Dashboards: envelope-throughput tile under `7-orchestration-metrics`;
verification-failure rate feeds `7-alerts-budgets`.

## Open Questions

- Do we offer key rotation with a grace period (sign with old key
  while advertising the new key for N minutes) or hard-cut? Timebox:
  Phase 3 exit before the first multi-operator deployment.
- Is Ed25519 the right primitive or should we default to Ed448 for
  longer-horizon security margin? Timebox: Phase 3 design review.
- Should `scoped_secrets` always be a reference to a short-lived
  token endpoint, or should we support inline cleartext blobs for
  drivers that cannot hit a token endpoint? Timebox: Phase 3 exit —
  aligned with `1-secrets-vault` short-lived-creds support.
