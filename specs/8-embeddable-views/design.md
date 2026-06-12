# 8-embeddable-views — Design

## Architecture

`8-embeddable-views` lives under
`source/site/ccai/pychestrate/webservice/embed/` and owns two
things: a *signing service* that issues signed embed URLs, and an
*embed renderer* that verifies those URLs and returns a minimal HTML
document hosting the appropriate `9-*` WebComponent. Issuance is an
authenticated API call under `8-rest-api-v1`; rendering is a
public-accessible route under `/embed/<view_kind>/<resource_id>`.
The signing keys live in `1-secrets-vault` and are keyed by a
short `key_id` included in the URL so multiple keys can be active
simultaneously during rotation. Inside the embed, data fetches go
through `8-rest-api-v1` authenticated with an inline
permission-intersected bearer token that shares the URL's TTL. The
authoritative state is the `embed_signing_keys` table (key
lifecycle) in `0-persistence`; nothing else is persistent — URLs
themselves are stateless. This feature ships in **Phase 10 —
Public Surface & Extensibility Completion**.

## Data Model

`embed_signing_keys` table:

- `key_id: str` — PK; 12-byte base32 identifier.
- `secret_ref: str` — pointer into `1-secrets-vault`
  (`embed.signing_key.<key_id>`).
- `role: KeySigningRole` — `current | in_grace | revoked`.
- `created_at: datetime`, `became_current_at: datetime`,
  `grace_expires_at: Optional[datetime]`,
  `revoked_at: Optional[datetime]`.
- Unique on `role` when role is `current` (only one current key
  at a time).

`embed_issuance_audit` table (lightweight log; primary audit lives in
`1-audit-log`):

- `issuance_id: UUID` — PK.
- `issued_at: datetime`, `issued_by: UUID`, `project_id: UUID`.
- `view_kind: str`, `resource_id: str`, `audience: str`,
  `expires_at: datetime`, `ttl_seconds: int`, `key_id: str`,
  `allowed_origins: list[str]`, `public: bool`.
- Index: `(project_id, issued_at)`.

Dataclasses:

```python
@dataclass(frozen=True)
class EmbedViewKind:
    view_kind_name: str
    declared_read_scope: list[str]    # permission keys
    supports_anonymous: bool
    component_tag: str                # e.g. 'pyc-run-detail'


@dataclass(frozen=True)
class SignedEmbedUrl:
    url: str
    iframe_snippet: str
    webcomponent_snippet: str
    key_id: str
    expires_at: datetime
```

## Interfaces

### Public API

Issuance (authenticated, under `/api/v1`):

- `POST /api/v1/projects/{project_id}/embeds` — mint a URL with
  body `{view_kind, resource_id, audience?, ttl_seconds,
  allowed_origins[], public?}`; returns `SignedEmbedUrl`.
- `GET /api/v1/projects/{project_id}/embeds` — list recent
  issuances (audit view).

Signing key management (authenticated, `system:embed.admin`
permission):

- `GET /api/v1/embeds/_meta/keys` — list keys with roles.
- `POST /api/v1/embeds/_meta/keys:rotate` — rotate the current
  key; responds with the new `key_id` and
  `grace_expires_at`.
- `POST /api/v1/embeds/_meta/keys/{key_id}:revoke` — force revoke.

Rendering (public):

- `GET /embed/<view_kind>/<resource_id>?a=&e=&k=&s=` — serve
  minimal HTML with the `9-*` WebComponent tag and inline
  permission-intersected bearer token.
- `GET /embed/<view_kind>/<resource_id>` with
  `Accept: application/json` — return descriptor JSON.

### Internal API

Module
`ccai.pychestrate.webservice.embed.signing`:

```python
def issue_signed_url(
        *,
        view_kind: str,
        resource_id: str,
        audience: str,
        ttl_seconds: int,
        allowed_origins: list[str],
        public: bool,
        issuing_principal_id: UUID,
        issuing_project_id: UUID
    ) -> SignedEmbedUrl:
    """
        Mint a signed embed URL.

        :raises: ConfigurationError, ValidationError
    """
    ...


def verify_signed_url(
        *,
        view_kind: str,
        resource_id: str,
        audience: str,
        expires_unix: int,
        key_id: str,
        signature_hex: str,
        request_origin: Optional[str],
        now: datetime
    ) -> EmbedVerificationResult:
    """
        Verify the signature and TTL; enforce origin allow-list.

        :raises: EmbedRejectedError
    """
    ...
```

Module
`ccai.pychestrate.webservice.embed.key_service`:

```python
def get_current_signing_key() -> EmbedSigningKey:
    """Return the current signing key (cached, single-flight on miss)."""
    ...


def rotate_signing_key(*, rotated_by: UUID) -> EmbedSigningKey:
    """
        Mint a new key, demote the current key to `in_grace`,
        and publish `entity.embed.signing_key_rotated`.
    """
    ...


def revoke_signing_key(*, key_id: str, revoked_by: UUID) -> None:
    """
        Mark the named key revoked immediately.

        :raises: ConfigurationError
    """
    rtnval = None
    return rtnval


def resolve_key_by_id(*, key_id: str, now: datetime) -> EmbedSigningKey:
    """
        Return a key if and only if it is current or still in grace.

        :raises: EmbedSigningKeyUnknownError, EmbedSigningKeyExpiredError
    """
    ...
```

Module
`ccai.pychestrate.webservice.embed.inline_token`:

```python
def mint_inline_token(
        *,
        issuing_principal_id: UUID,
        view_kind: EmbedViewKind,
        resource_id: str,
        expires_at: datetime,
        public: bool
    ) -> InlineBearerToken:
    """
        Mint a short-lived bearer token carrying the intersection of
        the principal's permissions and the view-kind's read-scope.

        :returns: Bearer token string plus its claims.
    """
    ...
```

Module
`ccai.pychestrate.webservice.embed.renderer`:

```python
def render_embed_document(
        *,
        view_kind: EmbedViewKind,
        resource_id: str,
        inline_token: InlineBearerToken,
        ttl_remaining_seconds: int,
        allowed_origins: list[str]
    ) -> HtmlResponse:
    """Assemble the minimal HTML with the WebComponent tag."""
    ...
```

### Extension Surface

None. The view-kind catalog is intentionally fixed so the attack
surface is enumerable. Adding a new embedable view is an in-tree
change; extensions that want embedable output can ship a dedicated
WebComponent under `9-*` and the view catalog can be extended in a
later release.

### Events Emitted

- `entity.embed.url_issued` —
  `{issuance_id, view_kind, resource_id, audience,
  expires_at, key_id, issued_by, project_id, public}`.
- `entity.embed.url_verified` —
  `{view_kind, resource_id, audience, key_id, origin,
  verified_at}`.
- `entity.embed.url_expired` —
  `{view_kind, resource_id, audience, key_id, observed_at}`.
- `entity.embed.url_rejected` —
  `{reason, view_kind, resource_id, key_id, origin, observed_at}`.
- `entity.embed.signing_key_rotated` —
  `{new_key_id, demoted_key_id, grace_expires_at, rotated_by,
  rotated_at}`.
- `entity.embed.signing_key_revoked` —
  `{key_id, revoked_by, revoked_at}`.

### Events Consumed

- `entity.project.deleted` — revoke outstanding issuances for the
  project (by refusing to mint new, not by revoking outstanding;
  individual URLs age out within TTL).
- `entity.secret.rotated` — key service invalidates the affected
  in-process secret cache entry.

## Component Breakdown

```
source/site/ccai/pychestrate/webservice/embed/
    __init__.py
    signing.py                     # issue_signed_url, verify_signed_url
    key_service.py                 # get_current/rotate/revoke/resolve
    inline_token.py                # mint_inline_token
    renderer.py                    # render_embed_document
    view_catalog.py                # fixed EmbedViewKind registry
    restapi/
        v1/
            issuance_controller.py   # POST /api/v1/projects/.../embeds
            keys_controller.py       # /api/v1/embeds/_meta/keys...
    public/
        embed_controller.py          # GET /embed/...
    models.py                      # SignedEmbedUrl, EmbedViewKind, ...
    exceptions.py
```

## Key Flows

**Issue a Run-Detail Embed:**

1. PM calls
   `POST /api/v1/projects/42/embeds` with
   `{view_kind: "run_detail", resource_id: "<run_id>",
   audience: "pm@corp.example.com", ttl_seconds: 3600,
   allowed_origins: ["https://wiki.corp.example.com"]}`.
2. `signing.issue_signed_url` validates TTL ceiling, looks up the
   current signing key via `key_service.get_current_signing_key`,
   composes `"<view_kind>|<resource_id>|<audience>|<expires>|<key_id>"`,
   computes HMAC-SHA-256.
3. Response returns `SignedEmbedUrl` plus paste-ready snippets
   and writes `embed_issuance_audit`.
4. `entity.embed.url_issued` publishes.

**Render an Embed:**

1. Wiki page loads
   `https://pychestrate.example.com/embed/run_detail/<run_id>?a=...&e=...&k=...&s=...`.
2. `embed_controller` calls
   `signing.verify_signed_url`:
   - `key_service.resolve_key_by_id` returns the active or
     in-grace key (or raises).
   - HMAC recomputed; constant-time compare against `s=`.
   - `e=` checked against `now`; if past, returns 410.
   - `Origin` (or `Referer`) checked against `allowed_origins`.
3. `inline_token.mint_inline_token` issues a bearer token for
   `view_kind.declared_read_scope ∩ issuing_principal_permissions`
   with TTL = URL TTL remaining.
4. `renderer.render_embed_document` returns HTML with
   `<pyc-run-detail run-id="..." inline-token="..." live>`
   plus CSP `frame-ancestors` per `allowed_origins`.
5. `entity.embed.url_verified` publishes.

**Key Rotation (Non-Disruptive):**

1. Operator calls
   `POST /api/v1/embeds/_meta/keys:rotate`.
2. `key_service.rotate_signing_key` mints a new key via
   `1-secrets-vault`, sets it `current`, demotes the previous
   key to `in_grace` with `grace_expires_at = now + 7 d`.
3. `entity.embed.signing_key_rotated` publishes.
4. For 7 days, URLs signed with either key verify.

**Force Revoke (Compromise Response):**

1. Operator calls
   `POST /api/v1/embeds/_meta/keys/abc123:revoke`.
2. `key_service.revoke_signing_key` sets the role to `revoked`
   with `revoked_at = now`.
3. `entity.embed.signing_key_revoked` publishes.
4. Any URL bearing `k=abc123` fails verification immediately.

## Error Handling

- `EmbedRejectedError` — parent type for
  `signature_invalid`, `origin_not_allowed`,
  `signing_key_unknown`, `signing_key_expired`,
  `url_expired`; each maps to 403 or 410 with a single-word HTML
  stub body.
- `ConfigurationError` — raised when the fixed view catalog and
  the `9-*` components are out of sync at startup; service
  refuses to start.
- `TtlExceededError` — raised at issuance; rejects the API call.
- `ViewKindUnknownError` — raised at issuance.
- `SemanticError` — raised on internal misuse; never caught.
- Multiline error messages via `os.linesep.join([...])`
  including `view_kind`, `resource_id`, and `key_id` for
  traceability.

## Security Considerations

- Signing uses HMAC-SHA-256 with constant-time comparison.
- Signing secrets live only in `1-secrets-vault`; cached in
  `SecretBytes`; evicted on rotation or revoke.
- Audience is part of the signed string — swapping `a=` to
  another value invalidates the signature.
- Origin allow-list is enforced server-side *before* the HTML is
  emitted; CSP `frame-ancestors` further constrains clients that
  did not set an Origin header.
- TTL ceiling is enforced server-side (3600 s default, up to
  86400 s project-configured).
- Inline bearer tokens are scoped to the intersection of the
  issuer's permissions and the view-kind's declared read-scope;
  their `exp` matches the URL TTL.
- Revocation bypasses the grace window for compromise response.
- `system:embed.admin` gates the meta endpoints;
  `project:embed.issue` gates issuance.
- Audit log records every issuance and every key action.

## Observability

Metrics:

- `pychestrate_embed_urls_issued_total{view_kind}`
- `pychestrate_embed_urls_verified_total{view_kind,outcome}`
- `pychestrate_embed_verify_duration_seconds` (histogram)
- `pychestrate_embed_signing_key_age_seconds` (gauge per key)
- `pychestrate_embed_rejections_total{reason}`
- `pychestrate_embed_inline_tokens_minted_total`

Log events: `embed.url_issued`, `embed.url_verified`,
`embed.url_rejected`, `embed.url_expired`,
`embed.signing_key_rotated`, `embed.signing_key_revoked`,
`embed.inline_token_minted`.

Trace spans: `embed.issue`, `embed.verify`, `embed.render`,
`embed.mint_inline_token`, `embed.key_lookup`.

## Open Questions

- Do we offer a `GET /embed/.../live` WebSocket endpoint for
  log-stream embeds, or keep live updates over the in-iframe
  inline-token-authenticated SSE? Leaning SSE for simplicity.
- Should we expose the embed audit listing through a UI in
  `9-admin-ui`, or leave API-only in Phase 10? Defer to post-GA.
- Outbound CSP reporting — hook up to
  `10-observability`? Close during Phase 10.
