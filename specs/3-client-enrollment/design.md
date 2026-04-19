# 3-client-enrollment — Design

## Architecture

Enrollment lives at
`source/site/automojo/pychestrate/webservice/clients/enrollment/`. It is a
REST-fronted admin surface (token issuance + revocation) plus an internal
hook exposed to `3-client-agent-protocol` that converts an inbound
`ClientEnrollRequest` frame into a persisted client identity. Token
generation is pluggable via the `enrollment_token_issuer` factory protocol;
identity checks beyond CSR Subject validation are pluggable via the
`client_identity_verifier` factory protocol. The CA private key lives in
`1-secrets-vault` and is fetched on demand per-request through a short-lived
issuing context — this module never holds the key in a long-lived attribute.
Authoritative state: the `client`, `client_cert`, `enrollment_token`, and
`client_revocation` tables, all persisted through `0-persistence`.

## Data Model

```
enrollment_token
    token_id:        UUID           primary key
    token_hash:      str            argon2id hash of secret, unique
    project_id:      UUID           foreign key -> project
    pod_name:        str            not null
    issued_by:       UUID           foreign key -> user
    issued_at:       datetime       not null
    expires_at:      datetime       not null
    one_shot:        bool           not null default true
    status:          TokenStatus    enum (pending|redeemed|expired|revoked)
    redeemed_at:     datetime       nullable
    redeemed_by_client_id: UUID     nullable
    (project_id, status) index

client
    client_id:       UUID           primary key
    project_id:      UUID           foreign key -> project, not null
    pod_name:        str            not null
    status:          ClientStatus   enum (active|suspended|revoked)
    enrolled_at:     datetime       not null
    (project_id, pod_name) unique

client_cert
    cert_serial:     str            primary key
    client_id:       UUID           foreign key -> client
    not_before:      datetime
    not_after:       datetime
    issuer_chain_id: UUID           foreign key -> ca_chain
    pem_public:      text
    (client_id, not_after desc) index

client_revocation
    revocation_id:   UUID           primary key
    client_id:       UUID           foreign key -> client
    cert_serial:     str            not null
    reason:          RevocationReason enum
    revoked_by:      UUID           foreign key -> user
    revoked_at:      datetime       not null
    (cert_serial) index
```

Enumerations (`clients/enrollment/enums.py`):

```
class TokenStatus(str, Enum):
    PENDING = "pending"
    REDEEMED = "redeemed"
    EXPIRED = "expired"
    REVOKED = "revoked"


class ClientStatus(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REVOKED = "revoked"


class RevocationReason(str, Enum):
    ROTATED = "rotated"
    DECOMMISSIONED = "decommissioned"
    COMPROMISED = "compromised"
    ADMIN_REQUEST = "admin_request"
```

## Interfaces

### Public API

- `POST /api/v1/projects/{project_id}/enrollment-tokens`
  - Permission: `client.enroll.issue`.
  - Body: `{ "pod_name": str, "ttl_seconds": int <= 86400, "one_shot": bool }`.
  - Response: `{ "token_id", "secret", "expires_at", "scope": {...} }`
    (`secret` returned exactly once).
- `GET /api/v1/projects/{project_id}/enrollment-tokens` — list (no secrets).
- `DELETE /api/v1/projects/{project_id}/enrollment-tokens/{token_id}` —
  admin rescind (sets `status=revoked`).
- `POST /api/v1/clients/{client_id}/revoke`
  - Permission: `client.enroll.revoke`.
  - Body: `{ "reason": RevocationReason, "note": str }`.

### Internal API

```python
def issue_enrollment_token(
    *,
    project_id: UUID,
    pod_name: str,
    ttl_seconds: int,
    one_shot: bool,
    issued_by: UUID,
) -> IssuedToken:
    ...


def redeem_enrollment_token(
    *,
    token_secret: str,
    csr_der: bytes,
    presenting_cert_fingerprint: Optional[str],
) -> EnrollmentResult:
    ...


def revoke_client(
    *,
    client_id: UUID,
    reason: RevocationReason,
    revoked_by: UUID,
    note: str,
) -> None:
    ...


def is_cert_revoked(*, cert_serial: str) -> bool:
    ...
```

Every function signature obeys AGENTS.md (snake_case, type hints,
named-parameter-only call convention at call sites, explicit returns).

### Extension Surface

Factory protocols:

```python
class EnrollmentTokenIssuerProtocol(FactoryProtocolBase):
    factory_protocol_name = "enrollment_token_issuer"
    protocol_schema_version = 1

    @classmethod
    def generate_secret(cls, *, entropy_bits: int) -> str:
        ...

    @classmethod
    def hash_secret(cls, *, secret: str) -> str:
        ...

    @classmethod
    def verify_secret(cls, *, secret: str, stored_hash: str) -> bool:
        ...


class ClientIdentityVerifierProtocol(FactoryProtocolBase):
    factory_protocol_name = "client_identity_verifier"
    protocol_schema_version = 1

    @classmethod
    def verify(
        cls,
        *,
        token_scope: TokenScope,
        csr: ParsedCsr,
        attestation_blob: Optional[bytes],
    ) -> VerificationReport:
        ...
```

Reference implementations shipped in-tree:

- `Argon2TokenIssuer` (`PRECEDENCE=100`) at
  `source/site/automojo/pychestrate/factories/enrollment_token_issuer/argon2_random.py`.
- `CsrSubjectVerifier` (`PRECEDENCE=100`) at
  `source/site/automojo/pychestrate/factories/client_identity_verifier/csr_subject.py`.

### Events Emitted

```
entity.client.token_issued     { token_id, project_id, pod_name, issued_by }
entity.client.enrolled         { client_id, cert_serial, project_id, pod_name }
entity.client.enroll_rejected  { token_id, reason }
entity.client.revoked          { client_id, cert_serial, reason, revoked_by }
```

### Events Consumed

- `entity.client.session_opened` (from `3-client-agent-protocol`) — used to
  evaluate whether the presented cert serial is current/unrevoked.

## Component Breakdown

```
source/site/automojo/pychestrate/webservice/clients/enrollment/
    __init__.py
    enums.py
    dtos.py                   -- IssuedToken, EnrollmentResult, TokenScope, ParsedCsr
    service.py                -- issue/redeem/revoke functions
    ca_adapter.py             -- short-lived CA signing context via secrets-vault
    repository.py             -- ClientEnrollmentRepository (SQL)
    rest.py                   -- Flask-RestX router
    rate_limit.py             -- per-project token issuance limiter

source/site/automojo/pychestrate/factories/enrollment_token_issuer/
    argon2_random.py
source/site/automojo/pychestrate/factories/client_identity_verifier/
    csr_subject.py
```

## Key Flows

**Admin issues a token.** Admin calls REST endpoint -> `service.issue_enrollment_token`
-> factory `enrollment_token_issuer.generate_secret` + `hash_secret` -> repository
writes row -> `entity.client.token_issued` -> response returns the secret exactly once.

**Client redeems the token.** Wire frame arrives at `3-client-agent-protocol` ->
dispatch handler calls `service.redeem_enrollment_token` with the presented
secret and CSR DER -> factory `client_identity_verifier.verify` is invoked ->
`ca_adapter.sign_csr` produces the cert via a short-lived secrets-vault context
-> a DB transaction writes `client`, `client_cert`, and updates
`enrollment_token.status=redeemed` atomically -> `entity.client.enrolled`
published -> transport sends `ClientEnrollAccept`.

**Operator revokes.** Admin calls REST endpoint -> `service.revoke_client` ->
writes `client_revocation` row and updates `client.status=revoked` in one
transaction -> `entity.client.revoked` published -> `3-client-agent-protocol`
force-closes the session within 1 s -> audit log + notification hub events fire.

## Error Handling

- `TokenExpired`, `TokenAlreadyRedeemed`, `ScopeMismatch`, `UnknownToken`,
  `RevokedCertPresented` — all subclasses of a `ClientEnrollmentError` base
  that is NOT a `SemanticError` (these are recoverable rejection paths). REST
  layer translates to HTTP 4xx; wire layer translates to `ClientEnrollReject`.
- `CertificateAuthorityUnavailable` — raised when the vault fetch fails.
  Caught at the REST/wire boundary, re-classified to include the vault backend
  name, and returned as HTTP 503.
- `ConfigurationError` — raised at startup if required factories are missing
  or the CA chain cannot be loaded. Service refuses to start.
- `SemanticError` — raised only for genuinely programmer-error conditions
  (e.g., repository invariant violation); never caught.
- Multiline error messages use `os.linesep.join([...])` with per-line prefixes
  `PROJECT:`, `POD:`, `REASON:`, etc.

## Security Considerations

- Bootstrap token secrets: 256-bit random; transported only in the
  `Authorization: Bearer pcx-<b64>` header over TLS; never logged.
- Token hashes stored with Argon2id `time_cost=2, memory_cost=64 MiB, parallelism=1`.
- CA private key sourced from `1-secrets-vault` per-request; module holds a
  context manager, never a long-lived key handle.
- RBAC: `client.enroll.issue`, `client.enroll.revoke`, `client.enroll.read`
  (read list of tokens).
- Every issue/redeem/revoke action produces a `1-audit-log` entry with
  `actor`, `project_id`, `pod_name`, `reason`.
- Issuance rate-limited per project (100/hour) and per admin (200/hour).
- Revocations with `reason=compromised` route a `2-notification-hub` alert at
  `severity=high` to the project admin channel.

## Observability

Metrics:

- `pychestrate_client_enrollments_total{result}` — counter.
- `pychestrate_client_tokens_issued_total{project_id}` — counter.
- `pychestrate_client_revocations_total{reason}` — counter.
- `pychestrate_client_enroll_latency_seconds` — histogram.
- `pychestrate_client_ca_sign_latency_seconds` — histogram.

Log events: `pychestrate_client_enroll_attempt`,
`pychestrate_client_enroll_rejected`, `pychestrate_client_enroll_accepted`,
`pychestrate_client_revoked`.

Trace spans: `client_enrollment.issue_token`, `client_enrollment.redeem`,
`client_enrollment.revoke`, `client_enrollment.ca_sign`.

## Open Questions

- Do we support an explicit `rotate_cert` flow distinct from revoke+re-issue?
  (Useful for scheduled rotations without a compromise event.) Decide by end
  of M2.
- Should revocation propagate to a CRL distribution point consumed by external
  systems (pods talking to third-party services with our CA trust)? Decide by
  end of M3; blocked on Phase 10 plugin API surface.
