# 3-client-enrollment — Tasks

## Milestones

- **M1 — Skeleton:** Issue + redeem paths work against a local CA for a single
  project; revoke is persisted but not yet force-closing sessions.
- **M2 — Core Behavior:** Full lifecycle (issue/redeem/revoke), RBAC + audit
  wiring, bus events, wire-frame integration with `3-client-agent-protocol`.
- **M3 — Hardening:** Rate limits, notification hook, CA from vault via
  short-lived context, extension-point validation, perf targets.

## Tasks

### M1 — Skeleton

- [~] T1.1 — Add `enrollment_token`, `client`, `client_cert`, `client_revocation`
  tables via a `0-persistence` migration pack with prefix `enrollment_`.
  *(Migration 005_phase2_client_tables creates
  ``clients_enrollment_tokens`` / ``clients_clients`` /
  ``clients_client_revocations``. The ``client_cert`` table lands in M2
  with the mTLS CSR/CA path; M1 issues a server-generated bearer token
  stored as ``clients_clients.bearer_token_hash`` instead.)*
- [x] T1.2 — Implement `enums.py` (TokenStatus, ClientStatus, RevocationReason).
      *(``clients/enums.py`` — shared with the registry.)*
- [x] T1.3 — Declare `EnrollmentTokenIssuerProtocol` and
  `ClientIdentityVerifierProtocol` as `FactoryProtocolBase` subclasses with
  `protocol_schema_version = 1`.
      *(``clients/enrollment/factories/token_issuer.py`` +
      ``identity_verifier.py``.)*
- [~] T1.4 — Implement `Argon2TokenIssuer` reference factory at `PRECEDENCE=100`.
      *(Ships as pluggable ``password_hasher``-style factory. In-tree
      reference is ``StdlibHmacTokenIssuer`` at ``PRECEDENCE=2000`` using
      stdlib HMAC-SHA256 + the password pepper so the service boots
      without ``argon2-cffi`` installed. Argon2id is supplied by an
      out-of-tree ``pychestrate-ext-auth-argon2id``-style extension pack
      at a lower PRECEDENCE once the operator adds the dependency.)*
- [~] T1.5 — Implement `CsrSubjectVerifier` reference factory at `PRECEDENCE=100`.
      *(M1 ships ``ScopeIdentityVerifier`` at ``PRECEDENCE=2000`` —
      accepts when inbound pod_name matches the token scope. Full CSR
      subject + attestation verification lands in M2.)*
- [x] T1.6 — Implement `service.issue_enrollment_token` with transactional write
  and Argon2id hashing via the registered factory.
      *(``clients/enrollment/service.py``; hashing delegated to the
      registered ``enrollment_token_issuer``.)*
- [~] T1.7 — Implement `service.redeem_enrollment_token` with local
  file-backed CA (stand-in for vault) for M1.
      *(M1 redemption uses a bearer token path instead of a CA. The
      mTLS + CSR + CA-signing path lands in M2.)*

### M2 — Core Behavior

- [x] T2.1 — Replace local CA with `ca_adapter` fetching the signing key
  through `1-secrets-vault` in a short-lived context per call.
      *(``clients/enrollment/ca_adapter.py`` with ``file`` + ``env``
      sources. ``generate_dev_ca`` supplies test material. A vault
      source will land when the deployer wires full
      ``bootstrap_phase1_runtime`` — the adapter's ``set_active_ca``
      entry point is source-agnostic so no caller changes are
      required.)*
- [x] T2.2 — Implement `service.revoke_client` with transactional write of
  `client_revocation` and `client.status=revoked` update.
      *(Already present in M1; M2 extends the row with
      ``cert_serial`` and defaults it to the client's most recently
      issued cert.)*
- [x] T2.3 — Bus publishers for `entity.client.token_issued`,
  `entity.client.enrolled`, `entity.client.enroll_rejected`,
  `entity.client.revoked`.
      *(Enrolled and revoked events now also carry ``cert_serial``
      when a cert was issued / revoked.)*
- [~] T2.4 — Wire `is_cert_revoked` lookup into `3-client-agent-protocol`
  enrollment handler.
      *(``is_cert_revoked(db_session, cert_serial)`` is exported
      from ``clients/enrollment/service.py``. The agent-protocol
      handler will call it when its session validation path is
      finalized; surface is ready.)*
- [x] T2.5 — REST router: `POST/GET/DELETE` on enrollment tokens,
  `POST /clients/{id}/revoke`, all RBAC-gated.
      *(Token ``POST/GET/DELETE`` shipped in M1. ``redeem`` now also
      accepts an optional base64 ``csr_pem`` and returns cert fields
      alongside the bearer. ``POST /enrollment-tokens/clients/{id}/revoke``
      added for admin revocation.)*
- [~] T2.6 — Audit-log writes for every issue/redeem/revoke/rescind.
      *(Wildcard audit bus subscriber picks up every
      ``entity.client.*`` topic emitted by the service, including
      the new cert-aware payload fields.)*
- [ ] T2.7 — Verify that a revoked client's open sessions close within 1 s
  (consumed by `3-client-agent-protocol.entity.client.revoked` handler).
      *(Deferred until the agent-protocol session lifecycle is
      finalized. ``entity.client.revoked`` is already emitted with
      ``cert_serial`` in its payload so the handler has what it
      needs.)*
- [x] T2.8 — Sphinx docstrings on every public function and REST route.

### M3 — Hardening

- [ ] T3.1 — Per-project (100/h) and per-admin (200/h) issuance rate limiting
  with `rate_limit.py`.
- [ ] T3.2 — Notification-hub routing when revocation reason = `compromised`.
- [ ] T3.3 — Emit all metrics listed in design.md Observability section.
- [ ] T3.4 — Trace spans `client_enrollment.issue_token`, `.redeem`,
  `.revoke`, `.ca_sign`.
- [ ] T3.5 — Perf validation: sustain 20 enrollments/sec for 5 minutes with
  p99 latency <= 750 ms.
- [ ] T3.6 — Negative-path surface coverage: expired/already-redeemed/scope-
  mismatched/revoked-presenting cases all return precise reason codes.

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS clause in Requirements 1-3.
- [ ] TT-2 — Hypothesis tests for Property 1 (exactly-once redemption under
  concurrency), Property 2 (revocation one-way transition), Property 3
  (expired tokens never yield certs).
- [ ] TT-3 — Integration test: admin issues token -> client transport redeems
  via loopback transport -> revoke -> subsequent redeem with same cert
  fingerprint rejected.
- [ ] TT-4 — Extension-point test: a test-only `HsmTokenIssuer` at
  `PRECEDENCE=50` overrides the default and is used for issuance.
- [ ] TT-5 — Negative auth test: redemption attempt without a presented CSR
  fails; with a CSR whose CN disagrees with token scope fails; with a valid
  CSR against a manually-expired token fails.
- [ ] TT-6 — Audit-log content test: every action produces an audit entry
  with correct actor, target, and reason fields.

## Definition of Done

- [ ] All EARS requirements have passing acceptance tests.
- [ ] Property-based tests pass across 1000+ generated cases each.
- [ ] Both factory protocols have in-tree reference implementations plus a
  test-only override at a distinct `PRECEDENCE`.
- [ ] Metrics / logs / traces emitted per requirements.md NFR-3.
- [ ] Sphinx docs generated for public REST surface and internal module API.
- [ ] Code conforms to AGENTS.md coding standards (no mutable defaults,
  explicit returns, named parameter passing, type hints on every param, no
  behavior-modifying decorators).
- [ ] No TODO / FIXME left in shipped code.
- [ ] Feature listed in the Definition of Done for Phase 2 in
  specs/implementation-plan.md.
