# 8-rest-api-v1 — Requirements

## Introduction

`8-rest-api-v1` is Pychestrate's versioned external HTTP API, published at
`/api/v1/...` and mirroring every capability exposed by the service —
projects, pods, clients, runs, resources, reservations, artifacts, metrics,
and users. It is the authoritative machine-readable surface consumed by
`8-cli`, `8-webhooks-in`, `8-webhooks-out`, `8-embeddable-views`, and every
external automation caller. The feature also declares the
`RestEndpointExtension` resource base so extensions can contribute endpoints
under `/api/v1/ext/<ext-name>/...` without ever colliding with core routes.
A minimal slice of this feature ships with Layer 5 in **Phase 3 — Minimal
Test Run End-to-End** (just enough surface to drive a testbase run), and the
feature is hardened to full coverage in **Phase 10 — Public Surface &
Extensibility Completion**. It sits between `1-authentication` /
`1-rbac` (which supply and gate the principal) and the REST clients above
it.

## Requirements

### Requirement 1: Versioning Policy and Breaking Change Discipline

**User Story:** As an external automation owner, I want a predictable
versioning policy with an explicit deprecation window, so that my
integrations do not silently break between releases.

**Acceptance Criteria (EARS):**

1. WHEN the core API introduces any backwards-incompatible change to an
   existing `/api/v1/...` route THEN the system SHALL publish the change
   only under a new major version `/api/v2/...` and SHALL keep the `v1`
   behavior unchanged for a deprecation window of **12 months** from the
   `v2` GA date.
2. WHEN a `/api/v1/...` route is reached on or after the announced
   deprecation date THEN the response SHALL include
   `Deprecation: true`, `Sunset: <RFC 7231 date>`, and
   `Link: <successor-route>; rel="successor-version"` headers, and the
   system SHALL publish an `entity.api.deprecation_hit` event.
3. IF a change is additive (new optional field, new endpoint, new
   enum value with server-side default behavior for unknown values)
   THEN the system SHALL ship the change under `v1` without a version
   bump, and SHALL record the addition in the machine-readable API
   changelog at `GET /api/v1/_meta/changelog`.
4. WHILE an API version is within its deprecation window the system
   SHALL serve its OpenAPI document at
   `GET /api/<version>/_meta/openapi.json` and SHALL NOT modify the
   document contents except to append `x-deprecated` annotations.
5. WHERE a client sends `Accept: application/vnd.pychestrate.v1+json`
   the system SHALL route the request as if the path prefix were
   `/api/v1/...`, enabling content-negotiated versioning for
   non-prefix-aware clients.

### Requirement 2: Core Resource Endpoint Coverage

**User Story:** As an external automation caller, I want every Pychestrate
entity exposed as a REST resource under a stable schema, so that I can
drive the service without reaching into the web UI.

**Acceptance Criteria (EARS):**

1. WHEN the service is running THEN the following resource roots SHALL be
   reachable under `/api/v1/...`: `users`, `projects`, `pods`, `clients`,
   `runs`, `resources`, `reservations`, `artifacts`, and `metrics`.
2. WHEN a `GET /api/v1/<resource>` is issued with query parameters
   `?cursor=&limit=` THEN the response SHALL be a paginated envelope
   `{ items: [...], next_cursor: str | null, total_estimate: int }`
   with `limit` clamped to `[1, 200]` and a default of `50`.
3. WHEN a `POST`, `PATCH`, or `DELETE` is issued to a resource THEN the
   system SHALL accept an `Idempotency-Key` header, SHALL deduplicate
   by `(principal, resource, idempotency_key)` for 24 hours, and SHALL
   return the stored response on replays.
4. IF a request body fails validation against the declared JSON Schema
   THEN the system SHALL respond `400 Bad Request` with a
   `application/problem+json` body listing `errors[].pointer` and
   `errors[].code` for every offending field.
5. WHERE RBAC denies a call the system SHALL respond `403 Forbidden`
   with `problem+json` detailing the missing permission key; unauthenticated
   callers SHALL receive `401 Unauthorized`.

### Requirement 3: Authentication Modes (Session Cookie, Bearer Token, mTLS)

**User Story:** As a caller, I want to authenticate via whatever mode fits
my client (interactive browser, service account, or mTLS-only network), so
that a single API surface serves humans, bots, and agents uniformly.

**Acceptance Criteria (EARS):**

1. WHEN a request carries a valid `pychestrate_session` cookie THEN the
   system SHALL resolve the principal via `1-authentication` and SHALL
   enforce CSRF on any non-idempotent method.
2. WHEN a request carries `Authorization: Bearer <token>` THEN the
   system SHALL validate the token through `1-authentication`'s bearer
   verifier and SHALL NOT consult the session cookie.
3. WHEN a request arrives over mTLS with a client certificate whose
   `Subject` maps via `1-client-enrollment` to a registered identity
   THEN the system SHALL resolve the request's principal as that client
   identity.
4. IF more than one authentication mode is asserted simultaneously
   (e.g., cookie plus bearer) THEN the system SHALL reject the request
   with `400 Bad Request` code `auth.mode_conflict`.
5. WHERE a route is annotated `public=True` (a narrow set — health,
   OpenAPI doc, changelog) the system SHALL serve it with no
   authentication requirement but SHALL apply the anonymous rate limit.

### Requirement 4: Extension-Contributed Endpoints Namespace

**User Story:** As an extension author, I want to publish REST endpoints
from my `pychestrate-ext-<name>` package, so that my extension's
capabilities are usable by `8-cli` and external callers.

**Acceptance Criteria (EARS):**

1. WHEN an extension registers a `RestEndpointExtension` subclass with
   `ext_name = "foo"` THEN its routes SHALL mount under
   `/api/v1/ext/foo/...` and SHALL NOT be reachable under any other
   prefix.
2. IF two extensions declare colliding sub-paths under the same
   `ext_name` THEN the extension host SHALL raise
   `ConfigurationError` at load time and SHALL NOT start the service.
3. WHEN an extension's endpoint is reached THEN the system SHALL
   enforce the extension's declared capability set from
   `E-extension-sandbox` before invocation; missing capabilities
   respond `403 Forbidden` code `ext.capability_denied`.
4. WHERE an extension declares `protocol_schema_version` that is
   incompatible with the running host (per `E-extension-compat-check`)
   the extension's routes SHALL NOT mount and the host SHALL emit a
   loud `ConfigurationError` at startup.

### Requirement 5: Rate Limiting and Quotas

**User Story:** As an operator, I want per-principal rate limits with
clear feedback, so that runaway clients cannot starve the rest of the
user base.

**Acceptance Criteria (EARS):**

1. WHEN a principal exceeds its configured quota THEN the system SHALL
   respond `429 Too Many Requests` with `Retry-After` set to the
   number of seconds until the next refill, `RateLimit-Limit`,
   `RateLimit-Remaining`, and `RateLimit-Reset` headers.
2. WHILE a request is served the system SHALL increment
   `pychestrate_api_requests_total{route,method,status,auth_mode}` and
   observe `pychestrate_api_request_duration_seconds` as a histogram.
3. IF the anonymous tier exceeds its quota THEN the system SHALL reject
   with `429` *before* any route handler runs.

## Property-Based Test Requirements

### Property 1: Cross-Version Compatibility

- **Invariant:** For any two REST API versions `V1` and `V2` defined in
  the version registry, a request that is valid and successful under
  `V1` SHALL either (a) be valid and successful under `V2` with an
  equivalent response shape, or (b) return a documented deprecation
  response with `Deprecation: true`, `Sunset: <date>`, and a
  `Link: rel="successor-version"` header pointing at a
  `V2`-addressable resource.
- **Generator:** Hypothesis strategy producing `(route, method, body)`
  triples drawn from the union of the V1 and V2 OpenAPI documents,
  parameterized by principal role.
- **Assertion:** No generated request terminates in
  `500 Internal Server Error`; every V1-success case yields either a
  V2-success or a deprecation response with all required headers
  populated and a resolvable `Link` target.
- **Sample size:** 1000 generated cases.

### Property 2: Idempotency-Key Replay Determinism

- **Invariant:** For any mutating request `(method, path, body,
  idempotency_key, principal)`, submitting the tuple N times within
  the 24-hour window yields exactly one state change and identical
  response bodies and status codes on submissions 2..N.
- **Generator:** Strategy producing mutating routes with random
  idempotency keys, 1..10 concurrent replays, and random body
  perturbations (must *not* perturb the body or the second submission
  SHALL be rejected `409 Conflict` code `idempotency.body_mismatch`).
- **Assertion:** State delta is observed once; responses on replays
  are byte-identical to the first; body-mismatch replays reject with
  `409`.
- **Sample size:** 1000 generated cases.

### Property 3: Pagination Totality

- **Invariant:** For any collection route with N items and any valid
  cursor chain, walking cursors from the empty cursor to
  `next_cursor == null` yields each item exactly once.
- **Generator:** Strategy producing collections sized `[0, 10_000]`
  with `limit` drawn from `[1, 200]` and ordering drawn from the
  declared sort keys.
- **Assertion:** Item multiset of concatenated pages equals the item
  multiset of the underlying store; no page exceeds `limit`;
  `next_cursor` is null exactly on the terminal page.
- **Sample size:** 1000 generated cases.

## Non-Functional Requirements

- **NFR-1 (Performance):** Core `GET` read-path p95 latency SHALL be
  `< 100 ms` at a workload of 200 req/s per pod. `POST /api/v1/runs`
  (dispatch path) SHALL be `< 250 ms` p95. Cold-start OpenAPI doc
  generation SHALL not block the first request past 500 ms.
- **NFR-2 (Security):** Every route SHALL declare its required
  permission(s) in metadata; a missing annotation SHALL refuse to
  register at startup (`ConfigurationError`). Bearer tokens SHALL be
  verified through `1-authentication` on every request with no local
  trust cache beyond 30 seconds. All `4xx`/`5xx` bodies SHALL use the
  `application/problem+json` schema and SHALL NEVER echo request
  credentials.
- **NFR-3 (Observability):** The feature SHALL emit
  `pychestrate_api_requests_total{route,method,status,auth_mode}`,
  `pychestrate_api_request_duration_seconds` (histogram),
  `pychestrate_api_deprecation_hits_total{route,version}`,
  `pychestrate_api_rate_limited_total{principal_tier}`,
  `pychestrate_api_extension_routes_registered`, and log events
  `api.request.served`, `api.request.rejected`,
  `api.deprecation.hit`, `api.extension.route.mounted`. Trace spans:
  `api.dispatch`, `api.auth`, `api.authorize`, `api.handler`.
- **NFR-4 (Reliability):** A single misbehaving extension route SHALL
  NOT degrade core routes; each extension's handler SHALL run with a
  wall-clock timeout of 30 s and a failure SHALL NOT leak state into
  subsequent requests. Health and OpenAPI endpoints SHALL remain
  reachable while any non-core route returns `5xx`.

## Out of Scope

- Authentication flows themselves — owned by `1-authentication`.
- RBAC evaluation — this feature *calls* `1-rbac` but does not own
  permission semantics.
- The CLI that consumes this surface — `8-cli`.
- Outbound webhooks and embeddable views — separate Layer 8 features.
- `v2` and later API versions — this feature is the `v1` surface
  only; subsequent majors live under their own folders
  (`source/.../restapi/versions/v2/...`).

## Dependencies

- **Depends on:** `0-web-app-host`, `1-authentication`, `1-rbac`,
  `1-audit-log`, `E-extension-host`, `E-resource-extensions`,
  `E-extension-sandbox` (gating extension routes),
  `E-extension-compat-check`.
- **Depended on by:** `8-cli`, `8-webhooks-in`, `8-webhooks-out`,
  `8-embeddable-views`, `8-plugin-api`, every external integration,
  and the in-browser UI fetch clients.
- **Extension points exposed:** `resource: RestEndpointExtension`
  (extensions contribute routes under `/api/v1/ext/<ext-name>/...`);
  `event: entity.api.deprecation_hit`. See implementation-plan.md
  Layer 8.
