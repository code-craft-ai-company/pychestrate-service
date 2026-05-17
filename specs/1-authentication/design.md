# 1-authentication — Design

## Architecture

`1-authentication` lives under
`source/site/automojo/pychestrate/webservice/security/auth/`. It wires a
WebWorks middleware that resolves every incoming request's session cookie
to a principal, plus a family of inbound endpoints for each `auth_provider`
kind (OIDC, SAML, local). The feature declares the `auth_provider` factory
protocol and the `MFAMethodExtension` resource base; concrete providers
ship in-tree and additional providers arrive through
`E-extension-host`. The authoritative state is the `auth_sessions` table
in `0-persistence`; IdP discovery and JWKS documents are held in an
in-process cache that survives requests but not restarts. Every
authentication event is a published entity event on `0-message-bus`;
`1-audit-log` is a downstream consumer. This feature ships in
**Phase 1 — Identity & Projects**.

## Data Model

The `auth_sessions` table holds the authoritative session state:

- `session_id: UUID` — primary key.
- `user_id: UUID` — FK → `users.user_id`.
- `provider_kind: AuthProviderKind` — `{OIDC, SAML, LOCAL}`.
- `provider_name: str` — which configured provider instance opened it.
- `opened_at: datetime`, `expires_at: datetime`, `last_seen_at: datetime`.
- `idle_timeout_seconds: int`.
- `access_token_enc: bytes` — AES-GCM sealed ID/access token payload for
  providers that need it; never returned over the wire.
- `refresh_token_enc: Optional[bytes]` — same sealing.
- `mfa_method_name: Optional[str]` — factor used, if any.
- `ip_fingerprint: str`, `user_agent_fingerprint: str`.

Indexes: `PRIMARY(session_id)`, `INDEX(user_id, expires_at)`,
`INDEX(last_seen_at)`.

The `auth_local_credentials` table holds local fallback hashes:

- `user_id: UUID` — PK / FK.
- `argon2id_hash: bytes`, `algo_params: JSON`.
- `must_rotate_after: datetime`, `last_changed_at: datetime`.

The `auth_saml_replay_cache` table:

- `response_id: str` — PK.
- `not_on_or_after: datetime` — used to prune.

The `auth_mfa_enrollments` table:

- `enrollment_id: UUID`, `user_id: UUID`, `method_name: str`,
  `secret_ref: str` (pointer into `1-secrets-vault`),
  `verified_at: datetime`, `last_used_at: datetime`.

Unique on `(user_id, method_name, enrollment_id)`.

The `auth_oidc_state` table:

- `state: str` — PK.
- `nonce: str`, `pkce_verifier_enc: bytes`, `provider_name: str`,
  `created_at: datetime`, `expires_at: datetime`,
  `redirect_target: str`.

## Interfaces

### Public API

REST routes:

- `GET /api/v1/auth/providers` — enumerate configured providers (name,
  kind, display label, enabled).
- `GET /auth/oidc/{provider_name}/login` — begin OIDC flow, 302 to IdP.
- `GET /auth/oidc/{provider_name}/callback` — receive OIDC response.
- `GET /auth/saml/{provider_name}/login` — begin SAML flow.
- `POST /auth/saml/{provider_name}/acs` — SAML assertion consumer.
- `POST /api/v1/auth/local/login` — local credential fallback.
- `POST /api/v1/auth/logout` — clear current session.
- `POST /api/v1/auth/mfa/challenge` — issue an MFA challenge for the
  current partial session.
- `POST /api/v1/auth/mfa/verify` — submit a method-specific response.

HTML browser surface (Requirement 5 — unified login):

- `GET /login` — render the canonical HTML login page; honors `next`
  query parameter (validated per NFR-2 before being echoed into the
  form action / hidden field). Chromeless (rendered outside the site
  shell — see `9-site-shell`).
- `POST /login` — thin HTML adapter that translates the form payload
  into the appropriate provider call (today: delegate to
  `local_flow.verify_local_credentials`; for OIDC/SAML the form posts a
  provider-selection that 302s into `/auth/oidc/...` or
  `/auth/saml/...`). On success, issue the session cookie and 303 to
  the validated `next` target (or `/`). On failure, re-render `/login`
  with an inline error and HTTP 400.
- `GET /logout` *(browser convenience)* — invokes the same logic as
  `POST /api/v1/auth/logout` and 303s the browser to `/login`.

The legacy `/config/login` and `/config/logout` paths are explicitly
retired by this design; the setup-gate middleware in `0-web-app-host`
continues to own `/setup/*` and takes precedence over `/login` while
the first-run wizard is incomplete.

### Internal API

Module `automojo.pychestrate.webservice.security.auth.session_service`:

```python
def open_session(
        *,
        user_id: UUID,
        provider_kind: AuthProviderKind,
        provider_name: str,
        mfa_method_name: Optional[str],
        access_token_payload: Optional[bytes],
        refresh_token_payload: Optional[bytes],
        request_fingerprint: RequestFingerprint,
        idle_timeout_seconds: int,
        max_lifetime_seconds: int
    ) -> AuthSession:
    """
        Persist a new session row and return it.

        :param user_id: Authenticated principal.
        :param provider_kind: OIDC | SAML | LOCAL.
        :param provider_name: Name of the configured provider instance.
        :param mfa_method_name: Method used for 2FA, if any.
        :param access_token_payload: Optional IdP access token sealed bytes.
        :param refresh_token_payload: Optional IdP refresh token sealed bytes.
        :param request_fingerprint: IP + user-agent fingerprint.
        :param idle_timeout_seconds: Inactivity deadline.
        :param max_lifetime_seconds: Absolute ceiling.

        :returns: The persisted `AuthSession`.
        :raises: ConfigurationError
    """
    ...


def resolve_session(*, session_id: UUID, now: datetime) -> AuthPrincipal:
    """
        Validate a session cookie and return the authenticated principal.

        :param session_id: Session id from the cookie.
        :param now: Evaluation timestamp.

        :returns: An `AuthPrincipal` bound to the live session.
        :raises: SessionExpiredError, SessionNotFoundError
    """
    ...


def close_session(*, session_id: UUID) -> None:
    """
        Close a session and publish `entity.session.closed`.
    """
    rtnval = None
    return rtnval
```

Module `automojo.pychestrate.webservice.security.auth.oidc_flow`:

```python
def begin_oidc_login(*, provider_name: str, redirect_target: str) -> OidcRedirect:
    """
        Generate state/nonce/PKCE verifier and build the authorization URL.
    """
    ...


def complete_oidc_callback(
        *,
        provider_name: str,
        state: str,
        authorization_code: str,
        request_fingerprint: RequestFingerprint
    ) -> AuthSession:
    """
        Complete the OIDC authorization code flow.

        :raises: AuthenticationError, ConfigurationError
    """
    ...


def refresh_oidc_session(*, session_id: UUID) -> AuthSession:
    """
        Refresh the access token using the stored refresh token.
    """
    ...
```

Module `automojo.pychestrate.webservice.security.auth.saml_flow`:

```python
def validate_saml_assertion(
        *,
        provider_name: str,
        saml_response_xml: bytes,
        relay_state: Optional[str]
    ) -> SamlPrincipalClaims:
    """
        Parse, signature-verify, and semantically validate a SAML response.

        :raises: AuthenticationError
    """
    ...
```

Module `automojo.pychestrate.webservice.security.auth.local_flow`:

```python
def verify_local_credentials(
        *,
        login_name: str,
        password: str,
        mfa_code: Optional[str],
        source_ip: str
    ) -> AuthSession:
    """
        Verify local credentials under Argon2id with backoff enforcement.

        :raises: AuthenticationError, MfaRequiredError
    """
    ...
```

### Extension Surface

Factory protocol `auth_provider` declared in
`automojo.pychestrate.webservice.security.auth.factories.auth_provider`:

```python
class AuthProviderProtocol(FactoryProtocolBase):
    factory_protocol_name: str = "auth_provider"
    protocol_schema_version: int = 1

    @classmethod
    def provider_kind(cls) -> AuthProviderKind:
        """Return OIDC / SAML / LOCAL."""
        ...

    @classmethod
    def build_begin_login_redirect(cls, *, provider_name: str, redirect_target: str) -> RedirectDescriptor:
        """Construct the initial redirect for the flow."""
        ...

    @classmethod
    def complete_callback(cls, *, provider_name: str, inbound: InboundFlowPayload) -> CompletedFlow:
        """Consume the provider callback and return claims + token bundle."""
        ...
```

Reference implementations (in-tree):
`OidcAuthProvider` (`PRECEDENCE = 1000`),
`SamlAuthProvider` (`PRECEDENCE = 1000`),
`LocalCredentialAuthProvider` (`PRECEDENCE = 1000`).

Resource base `MFAMethodExtension` declared in
`automojo.pychestrate.webservice.security.auth.extensions.mfa_method`:

```python
class MFAMethodExtension(ResourceExtension):
    method_name: str
    requires_second_factor: bool

    @classmethod
    def initiate_challenge(cls, *, user_id: UUID, enrollment: MFAEnrollment) -> MFAChallenge:
        ...

    @classmethod
    def verify_response(cls, *, user_id: UUID, challenge: MFAChallenge, submitted: MFAResponse) -> MFAResult:
        ...
```

Reference implementation: `TotpMfaMethod` shipping in-tree.

### Events Emitted

- `entity.session.opened` — `{session_id, user_id, provider_kind, provider_name, mfa_method_name, opened_at}`
- `entity.session.closed` — `{session_id, user_id, reason, closed_at}`
- `entity.session.refreshed` — `{session_id, refreshed_at}`
- `entity.auth.login.rejected` — `{provider_kind, provider_name, reason, remote_ip_hash, attempted_login_name_hash, at}`
- `entity.mfa.enrollment.created` — `{user_id, method_name, enrollment_id, created_at}`
- `entity.mfa.enrollment.removed` — `{user_id, method_name, enrollment_id, removed_at}`

### Events Consumed

- `entity.user.deactivated` — revoke all sessions for the user.
- `entity.user.updated` — if `primary_email` changed, invalidate
  pending MFA enrollments gated on email ownership.

## Component Breakdown

```
source/site/automojo/pychestrate/webservice/security/auth/
    __init__.py
    middleware.py                     # request-scoped session resolver
    session_service.py
    oidc_flow.py
    oidc_discovery.py                 # cached /.well-known + JWKS
    saml_flow.py
    saml_metadata.py                  # IdP metadata refresh
    local_flow.py
    mfa_service.py
    cookies.py                        # Set-Cookie builder with policy
    csrf.py                           # double-submit token helper
    fingerprint.py                    # RequestFingerprint builder
    extensions/
        mfa_method.py                 # ResourceExtension base
        totp_method.py                # reference impl
    factories/
        auth_provider.py              # FactoryProtocolBase
        oidc_provider.py              # reference impl
        saml_provider.py              # reference impl
        local_provider.py             # reference impl
    restapi/
        v1/
            auth_controller.py
            mfa_controller.py
    htmlui/
        login_view.py                 # GET/POST /login (Requirement 5)
        logout_view.py                # GET /logout convenience
        next_validator.py             # same-origin `next` parameter guard
    models.py                         # AuthSession, AuthLocalCredentials, ...
    events.py
    exceptions.py
```

## Key Flows

**OIDC Login:**

1. Browser hits `GET /auth/oidc/{provider_name}/login`.
2. `oidc_flow.begin_oidc_login` generates `state`, `nonce`, PKCE
   verifier; stores them in `auth_oidc_state`; returns a 302 to the
   provider's authorization endpoint.
3. Provider posts back to `.../callback`.
4. `complete_oidc_callback` validates `state`, exchanges the code at
   the token endpoint using the stored PKCE verifier, validates the
   `id_token` against JWKS (cached under the discovery document), and
   resolves the `user_id` via `1-user-management`.
5. `session_service.open_session` writes the row, `cookies.build` sets
   `pychestrate_session`, `entity.session.opened` publishes.

**SAML Login:**

1. `saml_flow` constructs the AuthnRequest, stores `InResponseTo`.
2. IdP posts to `/auth/saml/{provider_name}/acs`.
3. `validate_saml_assertion` verifies the XML signature against the
   currently-trusted certificate set (from `saml_metadata`), checks
   audience/conditions/clock skew, and rejects replays using
   `auth_saml_replay_cache`.
4. User is resolved or provisioned; session opens.

**Token Refresh:**

1. `middleware` on a hot-path request detects `expires_at` within 60
   seconds.
2. `oidc_flow.refresh_oidc_session` acquires a short per-session lock
   so concurrent refreshes collapse, calls the token endpoint, rotates
   refresh tokens if returned, and updates the row.
3. `entity.session.refreshed` publishes.

## Error Handling

- `AuthenticationError` — every signature/validity failure surfaces as
  this; the caller sees HTTP 401 with no detail. Reasons logged
  server-side (`signature`, `nonce`, `aud`, `replay_detected`, ...).
- `MfaRequiredError` — HTTP 401 with `WWW-Authenticate:
  PychestrateMfa realm="..."`; client follows the MFA challenge flow.
- `SessionExpiredError` / `SessionNotFoundError` — 401 with cookie
  clear.
- `ConfigurationError` — raised when a provider's discovery refuses or
  a SAML metadata document fails to parse on the *first* load; HTTP 503.
- `SemanticError` — raised on internal misuse; never caught.
- Multiline error messages built via
  `os.linesep.join(["Message.", "PROVIDER: {}".format(...)])` so
  context is preserved without string concatenation.

Token payloads are only ever passed in sealed bytes or in-memory
`SecretBytes` wrappers so they cannot be accidentally logged.

## Security Considerations

- OIDC: enforce PKCE `S256`, state/nonce binding, token audience/issuer
  checks, and JWKS kid rotation.
- SAML: XML canonicalization (`exc-c14n`), signed-response-or-assertion
  required, replay cache keyed on `Response/@ID`, `KeyInfo` ignored —
  trust set comes only from metadata.
- Local: Argon2id with parameters listed in NFR-2; pepper loaded from
  `1-secrets-vault` under key `auth.local.password_pepper`; backoff
  enforced in Redis-backed rate limiter.
- Cookies: `HttpOnly`, `Secure`, `SameSite=Lax` default
  (`Strict` when configured); domain scoping from service config.
- CSRF: double-submit cookie on any state-changing endpoint
  authenticated solely via the session cookie.
- All tokens stored only inside sealed columns with an AES-GCM DEK
  wrapped by the KEK that `1-secrets-vault` owns.
- `system:auth.admin` permission gates provider configuration;
  session introspection requires `system:auth.read`.
- The HTML login surface's `next` query parameter is run through
  `htmlui.next_validator.is_safe_same_origin_target` before any
  redirect; any absolute, protocol-relative, credentialed, or
  cross-host value is rejected and falls back to `/`. This is the only
  user-controlled input that influences a post-login redirect target.

## Observability

Metrics:

- `pychestrate_auth_login_total{provider,outcome}`
- `pychestrate_auth_login_duration_seconds{provider,outcome}` (histogram)
- `pychestrate_auth_local_login_failures_total{reason}`
- `pychestrate_auth_mfa_failures_total{method}`
- `pychestrate_auth_session_active` (gauge)
- `pychestrate_auth_saml_metadata_refresh_failures_total`
- `pychestrate_auth_oidc_discovery_refresh_failures_total`
- `pychestrate_auth_token_refresh_total{outcome}`

Log events: `auth.login.succeeded`, `auth.login.rejected`,
`auth.session.opened`, `auth.session.closed`,
`auth.session.refreshed`, `auth.oidc.discovery.refreshed`,
`auth.saml.metadata.refreshed`, `auth.mfa.challenge.issued`,
`auth.mfa.challenge.verified`.

Trace spans: `oidc.callback`, `oidc.token_exchange`, `oidc.refresh`,
`saml.validate`, `saml.metadata_refresh`, `session.resolve`,
`mfa.verify`.

## Open Questions

- Should SAML-side `SingleLogout` be in-scope for Phase 1 or deferred?
  Proposed: deferred to Phase 10 unless a Phase 1 customer requires
  it.
- Session store sharding: are we comfortable keeping sessions in the
  primary RDBMS, or do we front it with Redis from day one? Revisit
  after the Phase 1 load test.
- Device binding: do we include a stable device id in the session or
  rely solely on IP/UA fingerprint? Defer until `1-feature-flags`
  ships.
