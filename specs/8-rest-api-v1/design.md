# 8-rest-api-v1 — Design

## Architecture

`8-rest-api-v1` lives under
`source/site/ccai/pychestrate/webservice/restapi/` with one
sub-package per major version. The authoritative v1 tree is
`source/site/ccai/pychestrate/webservice/restapi/versions/v1/` —
each major version is a sibling folder (e.g. `.../versions/v2/`) so a
future version can ship without disturbing v1 code paths. A thin
top-level dispatcher (`restapi/api_root.py`) mounts every version's
blueprint under its path prefix (`/api/v1`, `/api/v2`, ...) and
negotiates content-type versioning against
`Accept: application/vnd.pychestrate.v<N>+json`. Extension-contributed
routes are collected by scanning for `RestEndpointExtension` subclasses
at service startup via `E-extension-host` and are mounted beneath
`/api/v1/ext/<ext-name>/...`. The authoritative source of truth for each
resource is its owning domain feature's repository (e.g. projects
repository in `2-projects`); this feature contains *only* controllers,
serializers, validators, authenticators, and rate limiting. The
OpenAPI document is generated from controller metadata at startup and
cached in-process for the lifetime of the service process. This
feature ships a minimal slice in **Phase 3** (enough for a testbase
run) and is hardened to full resource coverage in **Phase 10**.

## Data Model

The feature owns three auxiliary tables:

- `api_idempotency_records` — deduplication of mutating requests.
  - `idempotency_scope: str` — PK component (`principal_id:method:path`).
  - `idempotency_key: str` — PK component.
  - `request_body_hash: bytes` — SHA-256 of the canonicalized body.
  - `response_status: int`, `response_body: bytes`,
    `response_headers_json: str`.
  - `stored_at: datetime`, `expires_at: datetime` (24 h).
  - Index: `(expires_at)` for sweeper.

- `api_rate_limit_buckets` — per-principal token buckets.
  - `principal_id: str` — PK.
  - `tier: str` — `anonymous | user | service | mtls_client | admin`.
  - `tokens: float`, `capacity: float`, `refill_rate: float`,
    `last_refill_at: datetime`.

- `api_deprecation_events` — aggregated deprecation hits for
  reporting.
  - `event_id: UUID`, `principal_id: str`, `route: str`,
    `version: str`, `observed_at: datetime`.
  - Index: `(route, version, observed_at)`.

No entity state lives in this feature; domain repositories remain
authoritative for users, projects, pods, clients, runs, resources,
reservations, artifacts, and metrics.

## Interfaces

### Public API

Core v1 resource roots (every root supports `GET` list + `GET /{id}`
detail; mutating verbs listed per root):

- `/api/v1/users` — `GET`, `POST`, `PATCH /{user_id}`,
  `DELETE /{user_id}`.
- `/api/v1/projects` — `GET`, `POST`, `PATCH /{project_id}`,
  `DELETE /{project_id}`; nested:
  `/api/v1/projects/{project_id}/members`,
  `/api/v1/projects/{project_id}/variables`.
- `/api/v1/pods` — `GET`, `POST /{...register}`,
  `PATCH /{pod_id}`, `DELETE /{pod_id}`.
- `/api/v1/clients` — `GET`, `POST /enroll`,
  `PATCH /{client_id}`, `DELETE /{client_id}`.
- `/api/v1/runs` — `GET`, `POST` (dispatch),
  `POST /{run_id}:cancel`.
- `/api/v1/resources` — `GET`, `POST`, `PATCH /{resource_id}`,
  `DELETE /{resource_id}`.
- `/api/v1/reservations` — `GET`, `POST` (checkout),
  `POST /{reservation_id}:release`.
- `/api/v1/artifacts` — `GET`, `GET /{artifact_id}`,
  `GET /{artifact_id}/download` (presigned).
- `/api/v1/metrics` — `GET` (PromQL-style query), `GET /definitions`.

Meta routes:

- `GET /api/v1/_meta/openapi.json` — live OpenAPI document.
- `GET /api/v1/_meta/changelog` — JSON changelog feed.
- `GET /api/v1/_meta/versions` — configured major versions with
  `ga_date` and `sunset_date`.

Extension routes:

- `/api/v1/ext/<ext-name>/...` — every `RestEndpointExtension`
  registered subclass.

### Internal API

Module
`ccai.pychestrate.webservice.restapi.versions.v1.routing`:

```python
def register_route(
        *,
        route_spec: RouteSpec,
        handler: Callable[[RequestContext], ResponseEnvelope],
        required_permissions: list[str],
        is_public: bool,
        is_idempotent: bool,
        rate_limit_class: str
    ) -> None:
    """
        Register a v1 route in the dispatcher.

        :param route_spec: Method + path pattern + request/response schemas.
        :param handler: Callable invoked with a validated RequestContext.
        :param required_permissions: RBAC keys required to invoke the handler.
        :param is_public: True to bypass authentication (narrow allow-list).
        :param is_idempotent: True for GET/HEAD/OPTIONS or replayable mutations.
        :param rate_limit_class: One of {core_read, core_write, dispatch, heavy}.

        :returns: None.
        :raises: ConfigurationError
    """
    rtnval = None
    return rtnval
```

Module
`ccai.pychestrate.webservice.restapi.versions.v1.idempotency`:

```python
def lookup_or_record(
        *,
        principal_id: str,
        method: str,
        path: str,
        idempotency_key: str,
        canonical_body_hash: bytes
    ) -> Optional[StoredResponse]:
    """
        Return the stored response for a prior (key, body) pair, else None.

        :raises: IdempotencyBodyMismatchError
    """
    ...


def store_response(
        *,
        principal_id: str,
        method: str,
        path: str,
        idempotency_key: str,
        canonical_body_hash: bytes,
        response: ResponseEnvelope
    ) -> None:
    """Persist the response under the key for 24 hours."""
    rtnval = None
    return rtnval
```

Module
`ccai.pychestrate.webservice.restapi.versions.v1.versioning`:

```python
def resolve_requested_version(
        *,
        path: str,
        accept_header: Optional[str]
    ) -> ApiVersion:
    """
        Pick the target API version from path prefix or Accept header.

        :raises: UnknownApiVersionError
    """
    ...


def record_deprecation_hit(
        *,
        principal_id: str,
        route: str,
        version: str
    ) -> None:
    """Increment metrics and publish `entity.api.deprecation_hit`."""
    rtnval = None
    return rtnval
```

Module
`ccai.pychestrate.webservice.restapi.versions.v1.rate_limit`:

```python
def consume_token(
        *,
        principal_id: str,
        tier: str,
        rate_limit_class: str,
        cost: float
    ) -> RateLimitDecision:
    """
        Return allow/deny + retry-after for the refill-token-bucket model.
    """
    ...
```

Module
`ccai.pychestrate.webservice.restapi.ext_router`:

```python
def mount_extension_routes(*, host_registry: ExtensionHostRegistry) -> None:
    """
        Collect every RestEndpointExtension and mount its blueprint
        under /api/v1/ext/<ext_name>/.

        :raises: ConfigurationError
    """
    rtnval = None
    return rtnval
```

### Extension Surface

Resource base `RestEndpointExtension` declared in
`ccai.pychestrate.webservice.restapi.extensions.rest_endpoint`:

```python
class RestEndpointExtension(ResourceExtension):
    ext_name: str
    endpoint_version: int

    @classmethod
    def declare_routes(cls) -> list[ExtensionRouteSpec]:
        """Return the list of routes to mount under /api/v1/ext/<ext_name>/."""
        ...

    @classmethod
    def required_capabilities(cls) -> list[str]:
        """Sandbox capability keys that must be granted to mount this set."""
        ...
```

Reference implementations (in-tree):
`HealthExtensionEndpoints` (`/api/v1/ext/health/...`) and
`ExampleEchoEndpoints` (`/api/v1/ext/example/echo`) shipped in the
`pychestrate-ext-example` sample package for test coverage.

### Events Emitted

- `entity.api.deprecation_hit` —
  `{principal_id, route, version, observed_at, user_agent}`.
- `entity.api.extension_route_mounted` —
  `{ext_name, method, path, endpoint_version, mounted_at}`.
- `entity.api.rate_limit_exceeded` —
  `{principal_id, tier, rate_limit_class, retry_after_seconds,
  observed_at}`.

### Events Consumed

- `entity.extension.loaded` — triggers `mount_extension_routes`
  remount on dynamic reload.
- `entity.extension.unloaded` — unmounts an extension's blueprint.
- `entity.auth.session.closed` — invalidate any cached principal
  lookup in the 30 s trust window.

## Component Breakdown

```
source/site/ccai/pychestrate/webservice/restapi/
    __init__.py
    api_root.py                     # top-level dispatcher; mounts /api/v<N>
    ext_router.py                   # collects RestEndpointExtension
    versions/
        __init__.py
        v1/
            __init__.py
            routing.py              # register_route
            versioning.py           # resolve_requested_version, deprecation hits
            idempotency.py
            rate_limit.py
            problem_json.py         # RFC 7807 builders
            serializers.py          # canonical JSON encoder/decoder
            openapi.py              # OpenAPI doc builder
            feature/
                __init__.py
                users_controller.py
                projects_controller.py
                pods_controller.py
                clients_controller.py
                runs_controller.py
                resources_controller.py
                reservations_controller.py
                artifacts_controller.py
                metrics_controller.py
                meta_controller.py
    extensions/
        __init__.py
        rest_endpoint.py            # ResourceExtension base
    models.py                       # RouteSpec, RequestContext, ResponseEnvelope
    exceptions.py                   # IdempotencyBodyMismatchError, ...
```

## Key Flows

**Authenticated Mutating Request:**

1. `api_root.dispatch` resolves the version via
   `versioning.resolve_requested_version`.
2. Authentication middleware from `1-authentication` resolves the
   principal (cookie | bearer | mTLS).
3. If the route is annotated deprecated, `record_deprecation_hit`
   fires and the response assembler appends `Deprecation`, `Sunset`,
   and `Link` headers.
4. `rate_limit.consume_token` either admits the request or
   short-circuits with `429`.
5. `idempotency.lookup_or_record` returns a stored response if the
   key+body matches; else control proceeds to the handler.
6. The controller validates the body against its JSON Schema, invokes
   the domain repository through the owning feature's internal API,
   and emits the response envelope.
7. `idempotency.store_response` writes the tuple for 24 h.

**Extension-Contributed Endpoint:**

1. At service startup, `ext_router.mount_extension_routes` walks every
   `RestEndpointExtension` subclass collected by `E-extension-host`.
2. For each subclass, capabilities are checked against
   `E-extension-sandbox`; any missing capability raises
   `ConfigurationError` and the whole extension's blueprint is
   skipped with a loud log event.
3. The blueprint mounts under `/api/v1/ext/<ext_name>/...`;
   `entity.api.extension_route_mounted` publishes.
4. Requests are dispatched via the same pipeline as core routes with
   one extra guard: handler wall-clock timeout of 30 s wrapping the
   extension callable.

**Version Negotiation by Accept Header:**

1. Client sends `GET /api/resources?...` with
   `Accept: application/vnd.pychestrate.v1+json`.
2. `resolve_requested_version` rewrites the effective path to
   `/api/v1/resources`.
3. The rest of the pipeline is identical to path-prefixed requests.

## Error Handling

- `UnknownApiVersionError` — 404 with
  `application/problem+json` body `{ "type":
  ".../unknown-api-version" }`.
- `IdempotencyBodyMismatchError` — 409 `problem+json`.
- `RateLimitExceededError` — 429 with `Retry-After`.
- `ValidationError` — 400 with per-field pointer list.
- `ExtensionCapabilityDeniedError` — 403.
- `ConfigurationError` — raised at startup if a route declares no
  permissions, two extensions collide, or a sandbox capability is
  missing for an extension endpoint; service refuses to start.
- `SemanticError` — raised on internal misuse (e.g., a handler
  returning no envelope); always bubbles, never caught.
- All error messages are built via
  `os.linesep.join(["Summary.", "ROUTE: {}".format(route),
  "PRINCIPAL: {}".format(principal_id_hash)])` so context is
  preserved.

## Security Considerations

- Every route declares `required_permissions` at registration;
  missing metadata is a hard startup failure.
- Authentication modes are mutually exclusive per request
  (`auth.mode_conflict`).
- Bearer token verification has a 30 s local trust window; beyond
  that, `1-authentication` is re-consulted.
- Extension routes are sandboxed through
  `E-extension-sandbox`: a route requiring `dispatch:jobs` will be
  refused if the extension's manifest does not grant that capability.
- CSRF is enforced for cookie-authenticated mutating requests via the
  double-submit cookie pattern from `1-authentication`.
- Rate limits are per-principal with a distinct anonymous tier.
- All `4xx`/`5xx` responses use `application/problem+json` and never
  echo request credentials or bearer tokens.
- `system:api.admin` permission gates the meta routes other than
  `openapi.json` (which requires `system:api.read`).

## Observability

Metrics:

- `pychestrate_api_requests_total{route,method,status,auth_mode}`
- `pychestrate_api_request_duration_seconds` (histogram)
- `pychestrate_api_deprecation_hits_total{route,version}`
- `pychestrate_api_rate_limited_total{principal_tier,rate_limit_class}`
- `pychestrate_api_idempotency_replays_total{route}`
- `pychestrate_api_extension_routes_registered` (gauge)
- `pychestrate_api_extension_handler_errors_total{ext_name,route}`

Log events: `api.request.served`, `api.request.rejected`,
`api.deprecation.hit`, `api.extension.route.mounted`,
`api.extension.route.unmounted`, `api.rate_limit.exceeded`,
`api.idempotency.replay`, `api.openapi.rebuilt`.

Trace spans: `api.dispatch`, `api.version_resolve`, `api.auth`,
`api.authorize`, `api.rate_limit`, `api.idempotency`, `api.handler`,
`api.handler.ext`.

## Open Questions

- Should `Deprecation` header adoption track the IETF draft literally
  or Pychestrate's own profile? Close before Phase 10 GA.
- Do we expose gRPC alongside REST from day one, or ship as a
  separate Layer 8 feature? Deferred: out of scope for `8-rest-api-v1`.
- How aggressive is the idempotency store — 24 h or configurable per
  tier? Close before Phase 10 GA with data from Phase 3 usage.
