# 1-authentication — Tasks

## Milestones

- **M1 — Skeleton:** `auth_provider` factory protocol declared,
  `auth_sessions` table live, local credential login with Argon2id,
  cookie issuance, and session-resolver middleware running on every
  request.
- **M2 — Core Behavior:** OIDC flow with discovery + PKCE + refresh,
  SAML flow with metadata refresh and assertion validation,
  `MFAMethodExtension` base with `TotpMfaMethod` reference, MFA
  challenge/verify endpoints.
- **M3 — Hardening:** Concurrency-safe token refresh, replay cache
  sweeping, metrics/logs/traces complete, Sphinx docs, out-of-tree MFA
  extension exercised in integration tests.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Declare the `AuthProviderProtocol` `FactoryProtocolBase`
      with `factory_protocol_name = "auth_provider"` and
      `protocol_schema_version = 1`.
- [ ] T1.2 — Land the `auth_sessions`, `auth_local_credentials`,
      `auth_oidc_state`, `auth_saml_replay_cache`, and
      `auth_mfa_enrollments` tables as an `EntityMigrationExtension` pack.
- [ ] T1.3 — Implement `cookies.build_session_cookie` honoring
      `HttpOnly`, `Secure`, `SameSite`, `Domain`, `Path`, `Max-Age`.
- [ ] T1.4 — Implement `middleware.resolve_session` and wire it into
      the WebWorks request pipeline.
- [ ] T1.5 — Implement `local_flow.verify_local_credentials` with
      Argon2id (memory ≥ 64 MiB, iterations ≥ 3) and exponential
      backoff keyed on `login_name` + source IP.
- [ ] T1.6 — Implement `session_service.open_session`,
      `resolve_session`, `close_session`.
- [ ] T1.7 — Wire `POST /api/v1/auth/local/login` and
      `POST /api/v1/auth/logout` controllers.

### M2 — Core Behavior

- [ ] T2.1 — Implement `oidc_discovery.load_and_cache` with TTL honoring
      the response's `max-age` (clamped to [5 min, 24 h]).
- [ ] T2.2 — Implement `oidc_flow.begin_oidc_login` producing PKCE S256
      + state + nonce stored in `auth_oidc_state`.
- [ ] T2.3 — Implement `oidc_flow.complete_oidc_callback` with full
      `id_token` validation (iss/aud/exp/iat/nonce + JWKS).
- [ ] T2.4 — Implement `oidc_flow.refresh_oidc_session` with per-session
      single-flight lock and refresh-token rotation.
- [ ] T2.5 — Ship `OidcAuthProvider` reference implementation
      (`PRECEDENCE = 1000`).
- [ ] T2.6 — Implement `saml_metadata.refresh_metadata_document` with
      atomic trust-set rotation and 3600s default refresh.
- [ ] T2.7 — Implement `saml_flow.validate_saml_assertion` with
      `exc-c14n`, signature verification, audience/conditions check,
      and 2-minute clock skew tolerance.
- [ ] T2.8 — Implement SAML replay cache using
      `auth_saml_replay_cache` keyed on `Response/@ID`.
- [ ] T2.9 — Ship `SamlAuthProvider` reference implementation.
- [ ] T2.10 — Declare `MFAMethodExtension` resource base with
      `initiate_challenge` and `verify_response` classmethods.
- [ ] T2.11 — Implement `TotpMfaMethod` reference MFA extension.
- [ ] T2.12 — Wire `POST /api/v1/auth/mfa/challenge` and
      `POST /api/v1/auth/mfa/verify`.

### M3 — Hardening

- [ ] T3.1 — Emit every metric in requirements.md NFR-3
      (`pychestrate_auth_*`).
- [ ] T3.2 — Emit every log event listed in NFR-3 and tag token-bearing
      fields with `log_field_class=SECRET` so they are scrubbed.
- [ ] T3.3 — Add trace spans `oidc.callback`, `oidc.token_exchange`,
      `oidc.refresh`, `saml.validate`, `saml.metadata_refresh`,
      `session.resolve`, `mfa.verify`.
- [ ] T3.4 — Implement a background sweep for
      `auth_saml_replay_cache` and expired `auth_oidc_state` rows.
- [ ] T3.5 — Load-test session resolution against a 100k-session
      fixture and hold < 50 ms p95 on the hot path.
- [ ] T3.6 — Generate Sphinx docs for the public and internal API;
      document the `auth_provider` factory protocol and the
      `MFAMethodExtension` base.
- [ ] T3.7 — Ship an out-of-tree `pychestrate-ext-mfa-fixture` sample
      MFA method loaded via `E-extension-host` in the integration
      suite.

## Test Tasks

- [ ] TT-1 — Unit tests covering every EARS acceptance criterion in
      Requirements 1–4.
- [ ] TT-2 — Hypothesis-based property tests: Property 1 (cookie scope
      invariant), Property 2 (OIDC refresh idempotency), Property 3
      (SAML replay resistance), 1000 cases each.
- [ ] TT-3 — Integration test: configure a fake OIDC and a fake SAML
      IdP, exercise full login including MFA, token refresh, and
      logout; assert `1-audit-log` records each event exactly once.
- [ ] TT-4 — Extension-point test: register
      `pychestrate-ext-mfa-fixture` at `PRECEDENCE = 500` as an MFA
      method, enroll, challenge, and verify; verify the in-tree
      `TotpMfaMethod` continues to load unaffected.

## Definition of Done

- [ ] All EARS requirements have passing acceptance tests
- [ ] Property-based tests pass across 1000+ generated cases each
- [ ] Extension surface has at least one in-tree reference
      implementation (`OidcAuthProvider`, `SamlAuthProvider`,
      `LocalCredentialAuthProvider`, `TotpMfaMethod`) and one test-only
      override using a different `PRECEDENCE`
- [ ] Metrics / logs / traces emitted per requirements.md NFR-3
- [ ] Sphinx docs generated for public and internal APIs
- [ ] Code conforms to AGENTS.md coding standards (no mutable defaults,
      explicit returns, named parameter passing, type hints on every
      param, no behavior-modifying decorators)
- [ ] No TODO / FIXME left in shipped code
- [ ] Feature listed in the Definition of Done for Phase 1 —
      Identity & Projects in specs/implementation-plan.md
