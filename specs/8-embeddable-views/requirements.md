# 8-embeddable-views — Requirements

## Introduction

`8-embeddable-views` lets external portals (corporate wikis, PR
comments, Jira tickets, custom dashboards) embed Pychestrate UI
fragments — a run detail, a live log stream, an artifact preview,
a pipeline DAG, a project dashboard tile — via signed URLs with a
TTL and a rotatable signing key. A signed URL binds a view kind, a
resource id, an audience, an expiry, and (optionally) a scope of
inline data the embed is permitted to fetch. Receivers render the
embed inside an `<iframe>` (preferred) or as a WebComponent
hydrated from the URL. It sits downstream of `8-rest-api-v1` (for
data reads inside the embed) and `9-*` WebComponents (for the
rendered fragments). This feature ships in **Phase 10 — Public
Surface & Extensibility Completion**.

## Requirements

### Requirement 1: Signed URL Issuance

**User Story:** As a project admin, I want to mint a signed embed
URL with a TTL and an explicit audience, so that I can paste it
into a wiki without exposing broader Pychestrate access.

**Acceptance Criteria (EARS):**

1. WHEN an authenticated caller holding permission
   `project:embed.issue` invokes
   `POST /api/v1/projects/{project_id}/embeds`
   with `{view_kind, resource_id, audience, ttl_seconds}` THEN the
   system SHALL return a URL of the form
   `https://<host>/embed/<view_kind>/<resource_id>?a=<audience>&e=<expires_unix>&k=<key_id>&s=<signature>`
   where `signature = HMAC-SHA-256(secret_for(k), "<view_kind>|<resource_id>|<audience>|<expires_unix>|<key_id>")`.
2. IF the requested `ttl_seconds` exceeds the configured
   maximum (default 3600, configurable per project up to 86400)
   THEN the system SHALL reject with `400 Bad Request` code
   `embed.ttl_exceeded`.
3. WHEN an audience is omitted THEN the system SHALL default it to
   the calling principal's primary email address; the audience
   SHALL be included in the signature so URLs cannot be retargeted.
4. WHERE the `view_kind` is not in the registered embedable-views
   catalog the system SHALL reject with `400 Bad Request` code
   `embed.unknown_view_kind` at issuance time.

### Requirement 2: Signature Verification on Load

**User Story:** As a receiver loading a signed embed URL, I want
tampering to produce a hard failure, so that altered URLs cannot
smuggle a different resource past me.

**Acceptance Criteria (EARS):**

1. WHEN `GET /embed/<view_kind>/<resource_id>` is requested THEN
   the system SHALL recompute the signature using the key id's
   secret and SHALL compare in constant time; mismatches SHALL
   respond `403 Forbidden` with a minimal HTML stub.
2. IF `expires_unix` is in the past at load time THEN the system
   SHALL respond `410 Gone` with a minimal HTML stub and SHALL
   publish `entity.embed.url_expired`.
3. WHEN the signature verifies and `expires_unix` is in the future
   THEN the system SHALL publish `entity.embed.url_verified` and
   render the embed.
4. WHERE the request comes from an `Origin` not in the per-embed
   `allowed_origins` list (configured at issuance) the system
   SHALL respond `403 Forbidden` code `embed.origin_not_allowed`,
   and SHALL NOT set `Access-Control-Allow-Origin`.
5. WHILE the URL is verified the server response SHALL include
   `X-Frame-Options: ALLOWALL-FROM <origin>` (replaced per
   allowed origin) and `Content-Security-Policy: frame-ancestors
   <allowed_origins>` to constrain the embed context.

### Requirement 3: Key Rotation and Multi-Key Acceptance

**User Story:** As an operator, I want to rotate the embed signing
key without invalidating outstanding URLs, so that rotation is a
non-event.

**Acceptance Criteria (EARS):**

1. WHEN an operator triggers
   `POST /api/v1/embeds/_meta/keys:rotate` THEN the system SHALL
   mint a new signing key, set it as the *current* key, retain the
   previous key as valid for the configured grace window (default
   7 days), and publish
   `entity.embed.signing_key_rotated`.
2. WHEN a URL's `k=<key_id>` matches a retired-but-still-in-grace
   key THEN the system SHALL verify the signature against that
   key's secret and SHALL serve the embed.
3. IF a URL references a key id that is unknown or past its grace
   window THEN the system SHALL respond `403 Forbidden` code
   `embed.signing_key_unknown` or `embed.signing_key_expired`
   respectively.
4. WHILE a key is *compromised* an operator SHALL be able to
   force-revoke it with
   `POST /api/v1/embeds/_meta/keys/{key_id}:revoke`; from that
   moment all URLs signed with that key SHALL fail verification
   immediately (no grace).

### Requirement 4: View Catalog and Data Scoping

**User Story:** As an implementer, I want a fixed catalog of
embedable view kinds with a declared data scope, so that I cannot
accidentally ship an embed that leaks more than intended.

**Acceptance Criteria (EARS):**

1. WHEN `8-embeddable-views` initializes THEN the registered view
   kinds SHALL be: `run_detail`, `run_log_stream`,
   `artifact_preview`, `pipeline_dag`, `project_dashboard_tile`;
   unknown kinds SHALL be refused at issuance.
2. WHEN an embed renders THEN the in-iframe requests to
   `/api/v1/...` SHALL be scoped by a server-side derived bearer
   token whose permissions are the *intersection* of the issuing
   principal's permissions and the view kind's declared
   read-scope.
3. IF the view-kind's read-scope is violated (e.g., an
   `artifact_preview` embed attempts to list a different
   project's artifacts) THEN the inline bearer SHALL respond
   `403` for the out-of-scope call.
4. WHERE a view kind declares `supports_anonymous = True` AND the
   issuing principal marks the embed `public = True` the embed
   SHALL be reachable without session auth but SHALL still enforce
   origin allow-listing and TTL.

### Requirement 5: Ergonomic Rendering Surface

**User Story:** As a wiki author, I want a paste-ready snippet, so
that rendering inside my portal is zero-work.

**Acceptance Criteria (EARS):**

1. WHEN the issuance endpoint returns THEN the response body SHALL
   include `{url, iframe_snippet, webcomponent_snippet}` where
   each snippet is a ready-to-paste string with the signed URL
   already interpolated.
2. WHEN the embed URL is requested with `Accept: text/html` THEN
   the response SHALL be a minimal HTML document loading the
   appropriate `9-*` WebComponent with the resource id and inline
   token as attributes.
3. WHEN the embed URL is requested with
   `Accept: application/json` THEN the response SHALL be a small
   JSON descriptor `{view_kind, resource_id, snapshot_endpoint,
   live_events_endpoint, ttl_remaining_seconds}` suitable for
   custom renderers.

## Property-Based Test Requirements

### Property 1: Tamper Invalidates Signature

- **Invariant:** For any signed embed URL, any single-character
  mutation to any of the signed fields (`view_kind`,
  `resource_id`, `audience`, `expires_unix`, `key_id`) SHALL
  cause verification to fail with one of the documented
  `403`/`410` codes, and SHALL NEVER render the embed.
- **Generator:** Hypothesis strategy producing signed URLs over
  the full view-kind / resource-id Cartesian product; for each, a
  random single-character mutation position and replacement
  character drawn from the URL-safe set.
- **Assertion:** No tampered URL renders an embed; every tampered
  URL returns a `403` or `410` with a documented code; no server
  `5xx` is observed.
- **Sample size:** 1000 generated cases.

### Property 2: Verification Latency Bound

- **Invariant:** For any validly signed URL and any active signing
  key (current or in-grace), signature verification SHALL complete
  in `< 5 ms` p99 measured at the server on a cold cache and
  `< 1 ms` p99 on a warm cache.
- **Generator:** Strategy producing `(url, cache_state,
  key_role)` triples, with `cache_state ∈ {cold, warm}` and
  `key_role ∈ {current, in_grace}`.
- **Assertion:** Measured verification times are within the
  latency envelope on 100% of samples; histogram tails bounded.
- **Sample size:** 1000 generated cases.

### Property 3: Audience Binding

- **Invariant:** For any signed URL `(view_kind, resource_id,
  audience_A, expires, key_id, sig_A)` and any other audience
  `audience_B != audience_A`, swapping only the `a=` query
  parameter to `audience_B` while keeping `sig_A` SHALL cause
  verification to fail.
- **Generator:** Strategy producing `(audience_A, audience_B)`
  pairs and a fixed URL body; performs the swap and re-verifies.
- **Assertion:** 100% of swapped URLs reject with
  `embed.signature_invalid`.
- **Sample size:** 1000 generated cases.

## Non-Functional Requirements

- **NFR-1 (Performance):** Signed-URL verification SHALL be
  `< 5 ms` p99 (server-side) on a cold key-lookup cache. Embed
  HTML document SHALL be sub-100 KiB and fully loaded in
  `< 500 ms` p95 on a typical connection. URL issuance SHALL
  complete in `< 30 ms` p95.
- **NFR-2 (Security):** Signatures use HMAC-SHA-256 with
  constant-time comparison. Signing keys live only in
  `1-secrets-vault`. The TTL ceiling is enforced server-side.
  Origin allow-listing is enforced before the HTML body is
  returned. The inline bearer token passed to the embedded
  WebComponent is scoped to the intersection of the issuer's
  permissions and the view kind's read-scope, and it carries the
  same TTL as the URL. CSRF is N/A (GET-only); write endpoints
  under embed context are unreachable by design.
- **NFR-3 (Observability):** Emit
  `pychestrate_embed_urls_issued_total{view_kind}`,
  `pychestrate_embed_urls_verified_total{view_kind,outcome}`,
  `pychestrate_embed_verify_duration_seconds` (histogram),
  `pychestrate_embed_signing_key_age_seconds` (gauge per key),
  `pychestrate_embed_rejections_total{reason}`, and log events
  `embed.url_issued`, `embed.url_verified`, `embed.url_rejected`,
  `embed.signing_key_rotated`, `embed.signing_key_revoked`,
  `embed.url_expired`. Trace spans: `embed.issue`,
  `embed.verify`, `embed.render`.
- **NFR-4 (Reliability):** Key rotation SHALL be non-disruptive
  — outstanding URLs remain valid for the grace window. Loss of
  the in-process key cache SHALL NOT prevent verification; the
  system SHALL hit `1-secrets-vault` on a cache miss with a
  bounded concurrency (single-flight) so a stampede is avoided.

## Out of Scope

- The rendered WebComponents themselves — owned by Layer 9
  features (`9-wc-log-stream`, `9-wc-result-viewer`, etc.).
- Writable embeds (i.e., an embed that can mutate state) —
  deferred; `8-embeddable-views` is read-only in Phase 10.
- User-facing UI for managing outstanding URLs — deferred;
  initial surface is API-only.
- CDN caching strategies for embed HTML — deferred to
  `10-observability` / infra layer.

## Dependencies

- **Depends on:** `8-rest-api-v1`, `1-authentication`, `1-rbac`,
  `1-secrets-vault` (signing key storage), `1-audit-log`,
  `9-*` WebComponents (for the rendered fragments).
- **Depended on by:** External portals; no internal features
  depend on this.
- **Extension points exposed:** None — the view-kind catalog is
  intentionally fixed. Events:
  `entity.embed.url_issued`, `entity.embed.url_verified`,
  `entity.embed.url_expired`,
  `entity.embed.signing_key_rotated`,
  `entity.embed.signing_key_revoked`. See implementation-plan.md
  Layer 8.
