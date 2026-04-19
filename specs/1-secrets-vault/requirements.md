# 1-secrets-vault — Requirements

## Introduction

`1-secrets-vault` is Pychestrate's secret storage and reference layer. It
offers a uniform `secret_ref` surface every other feature uses when it
needs to materialize credentials (SCM tokens, notification channel
webhooks, infra-tool tokens, pod-scoped secrets), backed by either a local
encrypted store or an external delegating backend through the
`secrets_backend` factory protocol. It ships in **Phase 1 — Identity &
Projects**, sits between `1-rbac` (per-secret ACL evaluation) and
`1-audit-log` (every access is audited), and is consumed by
`2-global-variables`, `2-notification-hub`, `3-client-enrollment`, and
every Layer 6 feature. The feature honors AGENTS.md's "Aspects" pattern:
caller-supplied `SecretsAspects` objects control sync/async behavior,
timeouts, and logging verbosity rather than behavior-modifying decorators.

## Requirements

### Requirement 1: Write-Through Encrypted Storage

**User Story:** As a project administrator, I want to store a secret
under a stable `secret_ref` with an ACL, so that downstream features
resolve it at runtime without plaintext ever being checked in.

**Acceptance Criteria (EARS):**

1. WHEN an administrator calls `put_secret(secret_ref, plaintext,
   acl, aspects)` THEN the system SHALL encrypt the plaintext under the
   current data encryption key, persist the ciphertext + wrapped DEK +
   version + metadata, publish `entity.secret.created` (first version)
   or `entity.secret.rotated` (later versions), and return the new
   `SecretVersion` descriptor.
2. IF the `secret_ref` is not of the form
   `project:<id>:<name>` or `system:<name>` THEN the system SHALL
   reject the call with `SemanticError` listing expected namespaces.
3. WHEN `put_secret` is called with `aspects.sync = True` THEN the
   system SHALL return only after the write has been flushed to the
   configured backend and confirmed.
4. IF `aspects.sync = False` THEN the system SHALL accept the write
   into a durable outbox, return immediately, and guarantee
   eventual application with retry on transient backend errors.
5. WHERE an external `secrets_backend` is configured for the
   namespace the system SHALL delegate the write to the backend and
   SHALL NOT retain a local copy of the ciphertext.

### Requirement 2: Read with ACL Evaluation

**User Story:** As any feature author, I want to resolve a
`secret_ref` to plaintext at runtime subject to per-secret ACL, so
that authorization happens at the point of use.

**Acceptance Criteria (EARS):**

1. WHEN a caller invokes
   `read_secret(principal, secret_ref, aspects)` THEN the system
   SHALL evaluate the secret's ACL against the principal via
   `1-rbac`, materialize the plaintext into a `SecretBytes`
   wrapper, emit `entity.secret.accessed`, and return the wrapper.
2. IF the principal's ACL evaluation returns deny THEN the system
   SHALL raise `SecretAccessDeniedError`, emit
   `entity.secret.access_denied`, and SHALL NOT return or log the
   ciphertext or plaintext.
3. WHILE `aspects.timeout_seconds` is set the system SHALL abort any
   backend call that has not produced bytes within that timeout,
   raising `SecretReadTimeoutError` and emitting
   `pychestrate_secrets_read_timeouts_total`.
4. WHEN `aspects.include_metadata = True` the system SHALL return
   the secret's version, created_at, and rotation lineage alongside
   the plaintext wrapper.

### Requirement 3: Rotation and Expiry

**User Story:** As a security operator, I want to rotate secrets on a
schedule and force-expire compromised ones, so that blast radius is
bounded.

**Acceptance Criteria (EARS):**

1. WHEN an administrator calls `rotate_secret(secret_ref, new_plaintext,
   aspects)` THEN the system SHALL retain the previous version as
   `superseded`, install the new version as `active`, publish
   `entity.secret.rotated`, and keep the previous version readable
   for a configured grace window (default 1 hour) to cover in-flight
   operations.
2. IF a rotation grace window elapses THEN the system SHALL mark the
   prior version `expired`, schedule crypto-erasure of the
   ciphertext, and publish `entity.secret.expired`.
3. WHEN a secret is force-expired the system SHALL take effect
   immediately, bypassing the grace window, and SHALL publish
   `entity.secret.force_expired`.
4. WHERE a `secrets_backend` declares native rotation support the
   system SHALL delegate the rotation and record the returned
   external version id in the local metadata row.

### Requirement 4: External Backend Delegation

**User Story:** As an enterprise operator, I want Pychestrate to
delegate to HashiCorp Vault / AWS Secrets Manager / Azure Key Vault /
GCP Secret Manager for secrets in a declared namespace, so that
corporate secret governance continues to apply.

**Acceptance Criteria (EARS):**

1. WHEN an operator configures a `secrets_backend` extension with a
   `namespace_pattern` THEN the system SHALL route every
   `secret_ref` matching the pattern through that backend and SHALL
   hold no plaintext or ciphertext locally for those refs.
2. IF two registered `secrets_backend` implementations claim the
   same `namespace_pattern` THEN the system SHALL pick the lower
   `PRECEDENCE` (higher priority) per `E-extension-precedence` and
   log a `secrets.backend.override` event.
3. WHEN an external backend returns a transient error THEN the
   system SHALL retry per `aspects.retry_budget` (default 3
   attempts with exponential backoff 0.25s, 1s, 4s) before raising
   `SecretBackendUnavailableError`.
4. WHEN the backend reports a non-existent ref the system SHALL
   raise `SecretNotFoundError` WITHOUT retrying.

## Property-Based Test Requirements

### Property 1: Read Produces Exactly One Audit Record

- **Invariant:** For any secret write followed by any sequence of
  successful reads, the count of `entity.secret.accessed` events
  equals the number of successful reads, and denied reads produce
  exactly one `entity.secret.access_denied` each and zero
  `entity.secret.accessed`.
- **Generator:** Strategy producing up to 10 writes, up to 50
  interleaved read attempts with random allowed/denied principals,
  and optional `aspects.sync` toggles.
- **Assertion:** After the full sequence, the emitted event counts
  match the observed read outcomes exactly.
- **Sample size:** 1000 generated cases.

### Property 2: Rotation Preserves Live Readers During Grace

- **Invariant:** For any rotation, any reader that successfully
  captured a version id prior to rotation can still read that version
  until the grace window elapses; after the grace window no read of
  the prior version succeeds.
- **Generator:** Strategy producing rotation timestamps and a set of
  "captured" version ids with read times before, inside, and after
  the grace window.
- **Assertion:** Reads inside the grace window succeed; reads after
  the grace window raise `SecretVersionExpiredError`.
- **Sample size:** 1000 generated cases.

### Property 3: Plaintext Never Leaks to Logs

- **Invariant:** For any combination of `put_secret`, `read_secret`,
  `rotate_secret`, and internal error paths, no log record written by
  this feature contains the plaintext bytes; every secret field goes
  through the `SecretBytes.repr_safe()` path.
- **Generator:** Strategy producing plaintexts drawn from a small
  marker alphabet (so greps are reliable) across every API and every
  error path (timeouts, denied, backend unavailable, rotation race).
- **Assertion:** For every generated case, scanning the captured log
  stream for the marker substrings returns zero matches; the
  structured log field `secret.value` is always the literal string
  `"<redacted>"`.
- **Sample size:** 1000 generated cases.

## Non-Functional Requirements

- **NFR-1 (Performance):** `read_secret` against the local backend
  SHALL complete in < 10 ms p95 on warm cache, < 30 ms p99.
  Delegated backends may add their own latency but SHALL NOT
  degrade unrelated reads — per-backend connection pools are required.
- **NFR-2 (Security):** **Secrets MUST never be logged in
  plaintext.** All in-memory handling uses `SecretBytes` wrappers
  whose `__repr__` returns `"<redacted>"` and whose bytes are zeroized
  on drop. Ciphertext uses AES-GCM with a per-secret DEK wrapped by a
  KEK loaded at startup from an operator-owned key source. No write
  endpoint exists that bypasses the per-secret ACL. Every read and
  mutation is delivered to `1-audit-log` — a failed audit write
  SHALL fail the request.
- **NFR-3 (Observability):** The feature SHALL emit
  `pychestrate_secrets_reads_total{backend,outcome}`,
  `pychestrate_secrets_writes_total{backend,outcome}`,
  `pychestrate_secrets_read_duration_seconds{backend}` (histogram),
  `pychestrate_secrets_read_timeouts_total`,
  `pychestrate_secrets_rotations_total`,
  `pychestrate_secrets_backend_errors_total{backend,kind}`, and
  structured log events `secret.read.allowed`, `secret.read.denied`,
  `secret.rotated`, `secret.expired`, `secret.backend.failed`. Log
  records SHALL include `secret_ref` but never `secret.value`.
- **NFR-4 (Reliability):** A single failing backend SHALL NOT affect
  reads routed to a different backend. Writes with
  `aspects.sync = False` SHALL survive a process restart via the
  outbox and apply on recovery. Audit-log unavailability SHALL fail
  writes closed to preserve the append-only guarantee of
  `1-audit-log`.

## Out of Scope

- Secret *values* for authentication credentials (password hashes
  live in `1-authentication`; only its `password_pepper` goes
  through this vault).
- Configuration *schemas* — `2-global-variables` owns resolution of
  `secret_ref` values inside variable trees.
- Secret UI — lives in `9-wc-secret-editor` (Phase 10).
- Long-term archival of secret ciphertext — owned by
  `10-backup-dr`.

## Dependencies

- **Depends on:** `1-user-management`, `1-authentication`, `1-rbac`,
  `1-audit-log`, `0-persistence`, `0-message-bus`,
  `E-extension-host`.
- **Depended on by:** `1-authentication` (password pepper, OIDC
  client secrets), `2-global-variables`, `2-notification-hub`,
  `3-client-enrollment`, every Layer 6 feature.
- **Extension points exposed:** `factory: secrets_backend` — local
  DB, HashiCorp Vault, AWS Secrets Manager, Azure Key Vault, GCP
  Secret Manager, custom. Reference implementation
  `LocalEncryptedSecretsBackend` ships in-tree. See
  implementation-plan.md Layer 1.
