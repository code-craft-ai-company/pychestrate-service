# 3-client-enrollment — Requirements

## Introduction

Client Enrollment turns a short-lived bootstrap token into a long-lived mTLS
identity for a pod's client agent, and provides the revocation lifecycle for
that identity. It lives in Layer 3 and ships in Phase 2. The enrollment path
is the *only* way a `client` row comes into existence, and the mTLS certificate
it issues is the single credential that authorizes all subsequent pod traffic
per the architectural ground rule "pod client is the sole point of contact".
Upstream, it depends on `1-secrets-vault` for CA material and
`3-client-agent-protocol` for the wire framing. Downstream, every other Layer 3
feature assumes that a `client_id` references a row whose cert chain this
feature vouches for.

## Requirements

### Requirement 1: Bootstrap token issuance is authenticated and bounded

**User Story:** As a project admin, I want to issue a bootstrap token bound to a
project and a declared pod name, so that I can hand it to a new machine without
leaking any broader authority.

**Acceptance Criteria (EARS):**

1. WHEN an admin calls `POST /api/v1/projects/{project_id}/enrollment-tokens` with
   RBAC permission `client.enroll.issue` THEN the system SHALL return a
   `BootstrapToken` with `issued_at`, `expires_at <= issued_at + 24h`, `scope.project_id`,
   `scope.pod_name`, and a single-use `nonce`.
2. IF the caller lacks `client.enroll.issue` THEN the system SHALL respond with HTTP
   403 and SHALL NOT create any token row.
3. WHILE a token is unredeemed the system SHALL keep it visible on
   `GET /api/v1/projects/{project_id}/enrollment-tokens` as `status=pending`.
4. WHERE the optional `one_shot` flag is true the system SHALL reject the second
   redemption attempt with `TokenAlreadyRedeemed` even if the token has not expired.

### Requirement 2: Token redemption produces an mTLS certificate bound to the pod

**User Story:** As a fresh client agent, I want to redeem my bootstrap token and
receive an mTLS certificate with a stable identity, so that my later heartbeats
and dispatches authenticate without re-presenting the token.

**Acceptance Criteria (EARS):**

1. WHEN a `ClientEnrollRequest` carries a valid unexpired token and a CSR whose
   Subject CN equals `scope.pod_name` THEN the system SHALL sign the CSR against
   the Pychestrate internal CA and return the cert plus the issuer chain.
2. IF the CSR Subject CN disagrees with the token scope THEN the system SHALL
   respond `ClientEnrollReject{reason="scope_mismatch"}` and the token SHALL remain
   in `status=pending`.
3. IF the token `expires_at` is past THEN the system SHALL respond
   `ClientEnrollReject{reason="token_expired"}` and SHALL emit
   `entity.client.enroll_rejected{reason=token_expired}`.
4. WHEN redemption succeeds THEN the system SHALL persist a `client` row with the
   issued cert's serial as the stable identity and SHALL mark the token
   `status=redeemed`.

### Requirement 3: Revocation terminates authority immediately

**User Story:** As an operator who has discovered a compromised client machine,
I want to revoke the client's identity and force any open session to close, so
that the pod cannot accept further dispatches.

**Acceptance Criteria (EARS):**

1. WHEN `POST /api/v1/clients/{client_id}/revoke` is called with RBAC permission
   `client.enroll.revoke` THEN the system SHALL write a `client_revocation` row,
   add the cert serial to the revocation list, and emit `entity.client.revoked`.
2. IF a live session exists for the revoked `client_id` THEN the system SHALL
   force-close it within 1 second of the revocation commit.
3. WHILE a client is revoked the system SHALL reject any re-enrollment that
   presents the same cert serial and SHALL require a new token.
4. WHERE the revocation record carries `reason=compromised` the system SHALL
   write an `1-audit-log` entry tagged `severity=high` and SHALL notify the
   project admins via `2-notification-hub`.

## Property-Based Test Requirements

### Property 1: Token redemption is exactly-once

- **Invariant:** For any interleaving of `N` concurrent redemption attempts (N in
  `[2, 20]`) against the same `one_shot` token, exactly one succeeds and all
  others receive `TokenAlreadyRedeemed`.
- **Generator:** hypothesis strategy producing concurrent task sets that invoke
  `redeem_enrollment_token` with the same `token_id` and randomized delays
  drawn from `floats(0, 0.05)`.
- **Assertion:** the final `enrollment_token.status` equals `redeemed`; exactly
  one `client` row exists; all other attempts raised `TokenAlreadyRedeemed`; no
  two `client` rows share the same cert serial.
- **Sample size:** 1000 generated cases

### Property 2: Revocation is a one-way transition

- **Invariant:** For any sequence of admin actions
  `{issue, redeem, revoke, attempt_re_enroll}` applied to the same identity,
  once `client_revocation` is written for `(client_id, cert_serial)`, no
  subsequent action can transition the client back to `status=active` without
  issuing a **new** token and a **new** cert serial.
- **Generator:** hypothesis strategy generating action sequences of length 2-12
  drawn from the action set above.
- **Assertion:** the database invariant `revocation_row_exists(cert_serial)
  implies client.status != active` holds after every prefix of every sequence.
- **Sample size:** 1000 generated cases

### Property 3: Expired tokens never yield a cert

- **Invariant:** For any token with `expires_at < now`, no CSR input produces
  a signed cert.
- **Generator:** hypothesis strategy varying the CSR Subject CN, the skew
  between `now` and `expires_at` (always negative), and the signature algorithm.
- **Assertion:** `redeem_enrollment_token` raises `TokenExpired`; no row is
  written to `client` or `client_cert`.
- **Sample size:** 1000 generated cases

## Non-Functional Requirements

- **NFR-1 (Performance):** p99 end-to-end enrollment latency (token presented
  -> cert returned) <= 750 ms on a host with a hot intermediate CA; issuance
  throughput >= 20 enrollments/sec sustained.
- **NFR-2 (Security):** tokens are 256-bit random, stored as Argon2id hashes;
  CA private key never leaves `1-secrets-vault`; all token + revocation actions
  written to `1-audit-log`; enrollment endpoint requires either a valid
  `BootstrapToken` *or* a project-scoped issuing admin session (no anonymous
  path). Tokens rate-limited to 100/hour per project.
- **NFR-3 (Observability):** metrics
  `pychestrate_client_enrollments_total{result}`,
  `pychestrate_client_tokens_issued_total`,
  `pychestrate_client_revocations_total{reason}`,
  `pychestrate_client_enroll_latency_seconds` (histogram); log events
  `pychestrate_client_enroll_attempt`, `pychestrate_client_enroll_rejected`,
  `pychestrate_client_revoked`; trace span `client_enrollment.redeem`.
- **NFR-4 (Reliability):** token redemption is transactional: either the
  `client` row + cert row are both persisted and the token is marked redeemed,
  or all three are rolled back. Revocation is eventually-consistent with
  session force-close under 1 s.

## Out of Scope

- Wire framing of the enroll request (see `3-client-agent-protocol`).
- CA bootstrap / root-of-trust rotation (owned by `1-secrets-vault`).
- Capability reporting after enrollment (see `3-client-capability-advertisement`).
- Client inventory UI (see `3-client-inventory-ui`).

## Dependencies

- **Depends on:** `0-persistence`, `0-message-bus`, `1-secrets-vault`,
  `1-rbac`, `1-audit-log`, `3-client-agent-protocol`.
- **Depended on by:** `3-client-registry`, `3-static-pods`, `3-dynamic-pods`,
  `3-pod-lifecycle`, `3-agent-upgrade-channel`, every Layer 5 dispatch feature.
- **Extension points exposed:**
  - `factory: enrollment_token_issuer` — token generators (local random, HSM-backed,
    external provisioning system).
  - `factory: client_identity_verifier` — identity checks beyond CSR Subject
    (e.g., TPM attestation, cloud-instance identity doc verifier).
  See implementation-plan.md Layer 3.
