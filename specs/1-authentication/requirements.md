# 1-authentication — Requirements

## Introduction

`1-authentication` establishes *who* a caller is. It terminates SSO flows
(OIDC and SAML), maintains a local credential fallback for emergencies and
service accounts, issues and tracks sessions, and registers the
`MFAMethodExtension` resource surface so extension packs can add TOTP,
WebAuthn, backup codes, or organization-specific factors. It sits between
`1-user-management` (which owns the user record) and `1-rbac` (which
evaluates permissions against an authenticated principal), and it is the
first feature every REST controller consults. This feature ships in
**Phase 1 — Identity & Projects**.

## Requirements

### Requirement 1: OIDC Sign-In with Discovery

**User Story:** As an end user at an enterprise with an OIDC identity
provider, I want to sign into Pychestrate with my corporate account, so
that I reuse existing credentials and MFA.

**Acceptance Criteria (EARS):**

1. WHEN an operator configures an `auth_provider` of kind `oidc` with an
   `issuer_url` THEN the system SHALL fetch the provider's
   `/.well-known/openid-configuration` document at startup, cache it with
   the `max-age` indicated by the response (minimum 5 minutes, maximum 24
   hours), and refresh it no later than the cached expiry.
2. WHEN a user initiates sign-in THEN the system SHALL generate a
   cryptographically random `state` and `nonce`, persist the binding for
   10 minutes, and redirect the browser to the provider's authorization
   endpoint with `response_type=code` and PKCE `S256`.
3. WHEN the provider posts back to the callback endpoint with a valid
   authorization code THEN the system SHALL exchange the code for tokens,
   validate the `id_token` signature against the discovery `jwks_uri`,
   check `iss`, `aud`, `exp`, `iat`, and `nonce`, and open a session bound
   to the resolved `user_id`.
4. IF `id_token` validation fails for any reason THEN the system SHALL
   reject the sign-in with an `AuthenticationError`, log a structured
   `auth.oidc.rejected` event with the failure category, and SHALL NOT
   open a session.
5. WHERE the provider issues a refresh token and the session's access
   token is within 60 seconds of expiry the system SHALL refresh the
   token before the next downstream call, rotating any refresh token
   supplied, and preserving the session id.

### Requirement 2: SAML Sign-In with Assertion Validation

**User Story:** As an operator bound to a SAML-only IdP, I want Pychestrate
to accept SAML 2.0 assertions, so that my enterprise SSO continues to work.

**Acceptance Criteria (EARS):**

1. WHEN a user is redirected to the SAML ACS endpoint with a signed
   assertion THEN the system SHALL verify the XML signature against the
   configured IdP certificate, check `NotBefore` / `NotOnOrAfter` with 2
   minutes of clock skew tolerance, verify `Audience` matches the
   configured SP entity id, and ensure `InResponseTo` matches a
   still-valid auth request.
2. IF the assertion is unsigned, fails signature validation, or has a
   missing `InResponseTo` THEN the system SHALL reject the sign-in with
   an `AuthenticationError` and SHALL NOT write any session row.
3. WHEN the assertion validates successfully THEN the system SHALL
   resolve or provision the user via
   `1-user-management.run_directory_sync` using the SAML
   `NameID` + `Issuer` as `external_id`, open a session, and publish
   `entity.session.opened`.
4. WHILE a SAML IdP's metadata document is configured to refresh
   periodically the system SHALL re-read it every
   `metadata_refresh_seconds` (default 3600) and rotate the trusted
   certificate set atomically.

### Requirement 3: Local Credential Fallback and Session Lifecycle

**User Story:** As a bootstrapping administrator, I want a local login
path with strong password hashing, so that I can reach the service before
SSO is configured or during an IdP outage.

**Acceptance Criteria (EARS):**

1. WHEN the feature flag `auth.local_fallback_enabled` is set THEN the
   system SHALL accept `POST /api/v1/auth/local/login` with
   `{login_name, password, mfa_code?}`, verify the password against an
   Argon2id hash, enforce the configured MFA policy, and open a session
   on success.
2. IF a local login attempt fails THEN the system SHALL increment
   `pychestrate_auth_local_login_failures_total{reason}` and apply
   exponential backoff keyed on `login_name` + source IP (starting at 1s,
   capping at 60s).
3. WHEN a session is opened THEN the system SHALL issue a session cookie
   named `pychestrate_session` with `HttpOnly=true`, `Secure=true`,
   `SameSite=Lax`, `Path=/`, `Domain` set to the configured host, and
   `Max-Age` matching the configured session TTL (default 12 hours).
4. WHEN a user signs out OR a session reaches its idle timeout (default
   2 hours) THEN the system SHALL invalidate the session row, publish
   `entity.session.closed`, and clear the cookie in the response.
5. WHILE a session is active the system SHALL refresh `last_seen_at` no
   more than once per 60 seconds to avoid write amplification.

### Requirement 4: MFA Extension Surface

**User Story:** As a security-team operator, I want to add new MFA factors
(WebAuthn, push, hardware tokens) without forking Pychestrate, so that our
standards evolve on our schedule.

**Acceptance Criteria (EARS):**

1. WHEN an extension registers an `MFAMethodExtension` subclass THEN the
   system SHALL include the method in the user's enrollable-factor list
   and in the challenge-selection UI, gated on a feature-flag
   `auth.mfa.<method-name>.enabled`.
2. WHERE an MFA method declares `requires_second_factor = True` the
   system SHALL require a successful challenge before opening a session,
   even when the primary credential path succeeds.
3. IF every registered MFA method for a user fails or is unavailable
   THEN the system SHALL reject the sign-in with an
   `MfaRequiredError`, emit
   `pychestrate_auth_mfa_failures_total{method}`, and SHALL NOT open a
   session.

### Requirement 5: Unified HTML Login Surface

**User Story:** As any human visitor — administrator, project member, or
auditor alike — I want one well-known login page that every protected
route redirects me to, so that I never have to learn separate login
URLs for admin vs non-admin areas of the product.

**Acceptance Criteria (EARS):**

1. WHEN an unauthenticated browser issues `GET /login` THEN the system
   SHALL serve the HTML login page at the canonical path `/login` (NOT
   `/config/login` and NOT any admin-scoped path) with
   `Content-Type: text/html; charset=utf-8` and HTTP 200.
2. WHEN the login form is submitted THEN the browser SHALL `POST` to
   `/login`, which the system SHALL accept as a thin HTML adapter
   delegating to the existing `POST /api/v1/auth/local/login` (and any
   future provider-specific form posts) declared in this feature's
   Public API, and SHALL set the `pychestrate_session` cookie on
   success per Requirement 3.
3. WHEN an unauthenticated request targets any protected HTML page
   (any HTML route that is not itself chromeless — see `9-site-shell`)
   THEN the system SHALL respond with HTTP 303 to
   `/login?next=<percent-encoded-original-path-and-query>`, and SHALL
   NOT carry the original request's body or non-cookie headers into
   the redirect target.
4. WHEN a login completes successfully AND the request carries a
   `next` query parameter THEN the system SHALL redirect the browser
   to that target if and only if it passes the same-origin safety
   check defined in NFR-2; otherwise the system SHALL redirect to
   `/`.
5. WHILE the first-run setup wizard owned by `0-web-app-host` /
   `1-user-management` is incomplete (the setup gate middleware is
   diverting every browser navigation to `/setup/*`) the system SHALL
   treat `/login` as gated identically to any other non-setup route:
   any `GET /login` SHALL 303 to `/setup/unlock`. WHEN the wizard
   completes THEN `/login` SHALL become the unauthenticated entry
   point on the very next request without a process restart.
6. WHEN a user signs out from a browser session via the logout
   endpoint THEN the system SHALL clear the `pychestrate_session`
   cookie per Requirement 3 AND SHALL respond with HTTP 303 to
   `/login` (no `next` parameter), so the next navigation lands on
   the login page rather than a 401 fragment.

## Property-Based Test Requirements

### Property 1: Session Cookie Scope Invariant

- **Invariant:** For any session opened against any configured host and
  any auth provider, the issued `Set-Cookie` header has
  `HttpOnly`, `Secure`, `SameSite=Lax`, `Path=/`, and a non-zero
  `Max-Age` less than or equal to the configured session TTL.
- **Generator:** Strategy producing combinations of {host, auth kind
  (OIDC, SAML, local), configured TTL in [60, 86400] seconds}.
- **Assertion:** Parsing the returned `Set-Cookie` header yields the
  required attributes on every generated case, and `Max-Age <= TTL`.
- **Sample size:** 1000 generated cases.

### Property 2: OIDC Token Refresh Idempotency

- **Invariant:** For any session whose access token is refreshed N times
  in a single request window, the resulting session has exactly one
  valid access token, exactly one refresh token (rotated if the IdP
  supplied one), the session id is preserved, and exactly one
  `entity.session.refreshed` event is published per *distinct*
  refresh — concurrent refreshes collapse to one.
- **Generator:** Strategy producing 1–20 concurrent refresh requests
  against a fake IdP that returns deterministic tokens and optionally
  rotates refresh tokens.
- **Assertion:** Post-run session state matches the single-refresh
  outcome; event count equals 1; no race produces a zombie refresh
  token.
- **Sample size:** 1000 generated cases.

### Property 3: SAML Replay Resistance

- **Invariant:** For any SAML assertion, replaying the same
  `Response/@ID` within its `NotOnOrAfter` window SHALL succeed exactly
  once and SHALL fail on every subsequent submission with
  `AuthenticationError(reason="replay_detected")`.
- **Generator:** Strategy producing valid signed assertions with varying
  `NotBefore`/`NotOnOrAfter` spreads and replay counts 2–10.
- **Assertion:** Only the first submission opens a session; every
  subsequent attempt is rejected; replay cache row is removed only
  after the assertion's `NotOnOrAfter` passes.
- **Sample size:** 1000 generated cases.

## Non-Functional Requirements

- **NFR-1 (Performance):** Session validation on a request hot path
  (cookie → principal resolution) SHALL complete in < 50 ms p95,
  < 150 ms p99. Token refresh SHALL not add more than 100 ms p95 to
  the request it is triggered on.
- **NFR-2 (Security):** Passwords SHALL be hashed with Argon2id
  (memory ≥ 64 MiB, iterations ≥ 3, parallelism ≥ 1). ID tokens and
  refresh tokens SHALL NEVER be written to any log. Session cookies
  SHALL always carry `HttpOnly`, `Secure`, and `SameSite=Lax` (or
  `Strict` when `session.strict_samesite` is set). CSRF protection
  SHALL apply to every non-idempotent request on session-cookie-backed
  endpoints. The post-login `next` parameter (Requirement 5) SHALL be
  validated as same-origin before redirect: the system SHALL accept
  only values that, when resolved against the request's own origin,
  produce a URL whose scheme + host + port match the request's own
  scheme + host + port and whose path begins with `/`. Any value that
  is absolute (contains a scheme or authority), is protocol-relative
  (`//host/...`), contains an embedded credential, or resolves to a
  different host SHALL be rejected and the post-login redirect SHALL
  fall back to `/`. Rejections SHALL emit a structured
  `auth.login.next_rejected` log event with the offending value
  hashed for forensics.
- **NFR-3 (Observability):** The feature SHALL emit
  `pychestrate_auth_login_duration_seconds{provider,outcome}`
  (histogram), `pychestrate_auth_login_total{provider,outcome}`,
  `pychestrate_auth_local_login_failures_total{reason}`,
  `pychestrate_auth_mfa_failures_total{method}`,
  `pychestrate_auth_session_active`, and structured log events
  `auth.login.succeeded`, `auth.login.rejected`, `auth.session.opened`,
  `auth.session.closed`, `auth.session.refreshed`, and
  `auth.oidc.discovery.refreshed`.
- **NFR-4 (Reliability):** IdP discovery refresh failures SHALL NOT
  invalidate an already-cached document; the cache SHALL continue to
  serve validation until TTL expiry. SAML metadata refresh failures
  SHALL preserve the current trusted certificate set and emit
  `pychestrate_auth_saml_metadata_refresh_failures_total`.

## Out of Scope

- The user and group tables themselves — owned by `1-user-management`.
- Role and permission semantics — owned by `1-rbac`; this feature only
  supplies the authenticated principal the RBAC check consumes.
- Secret storage — credentials live in `1-secrets-vault` referenced by
  `secret_ref`; only password hashes for local fallback live in this
  feature's table.
- API-key auth for machine-to-machine — deferred to Phase 10
  `8-plugin-api`.

## Dependencies

- **Depends on:** `1-user-management`, `0-persistence`, `0-message-bus`,
  `E-extension-host`, `E-resource-extensions`, `1-secrets-vault` (for
  client-secret storage), `1-feature-flags` (for `auth.*` toggles).
- **Depended on by:** every controller in Layers 2–9; `1-rbac` consumes
  the authenticated principal.
- **Extension points exposed:** `factory: auth_provider` (per protocol —
  OIDC, SAML, local); `resource: MFAMethodExtension`. Reference
  implementations: `OidcAuthProvider`, `SamlAuthProvider`,
  `LocalCredentialAuthProvider`, `TotpMfaMethod`. See
  implementation-plan.md Layer 1.
