# 8-rest-api-v1 — Tasks

## Milestones

- **M1 — Skeleton:** Versioned dispatcher at `/api/v1`, core
  read-only resources (`projects`, `pods`, `clients`, `runs`,
  `artifacts`) wired to their domain repositories, authentication
  middleware plugged in, OpenAPI doc generated at startup. Minimal
  slice ships in **Phase 3**.
- **M2 — Core Behavior:** Full CRUD on every resource root
  (users, projects, pods, clients, runs, resources, reservations,
  artifacts, metrics), idempotency store, rate limits,
  `RestEndpointExtension` surface with one in-tree reference
  implementation. Lands in **Phase 10**.
- **M3 — Hardening:** Deprecation-header machinery, changelog feed,
  versioning policy enforcement, content-type version negotiation,
  full metric/log/trace coverage, load test at 200 req/s per pod,
  Sphinx docs for every controller, out-of-tree extension loaded and
  exercised.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Land `restapi/api_root.py` with path-prefix dispatch to
      `versions/v1/` blueprints.
- [ ] T1.2 — Implement `versions/v1/routing.register_route` with
      mandatory `required_permissions` validation at startup.
- [ ] T1.3 — Wire the `1-authentication` cookie, bearer, and mTLS
      resolvers behind a single request-scoped principal middleware.
- [ ] T1.4 — Implement `problem_json.build_problem_response` per
      RFC 7807.
- [ ] T1.5 — Implement the `projects`, `pods`, `clients`, `runs`,
      and `artifacts` *read* controllers (GET list + GET detail)
      calling their owning domain repositories.
- [ ] T1.6 — Implement `openapi.build_document` and serve it at
      `GET /api/v1/_meta/openapi.json` with in-process caching.
- [ ] T1.7 — Implement pagination envelope
      `{items, next_cursor, total_estimate}` with `limit` clamp.
- [ ] T1.8 — Ship `POST /api/v1/runs` dispatch endpoint (Phase 3
      requirement — the testbase slice).

### M2 — Core Behavior

- [ ] T2.1 — Land `api_idempotency_records` table and implement
      `idempotency.lookup_or_record` + `store_response`.
- [ ] T2.2 — Implement `rate_limit.consume_token` with a
      refill-token-bucket backed by `api_rate_limit_buckets`.
- [ ] T2.3 — Ship full CRUD controllers for `users`, `projects`,
      `pods`, `clients`, `resources`, `reservations`, `artifacts`,
      and `metrics`.
- [ ] T2.4 — Wire nested routes (`projects/{id}/members`,
      `projects/{id}/variables`,
      `runs/{run_id}:cancel`, `reservations/{id}:release`).
- [x] T2.5 — Declare `RestEndpointExtension` resource base and
      implement `ext_router.mount_extension_routes` with collision
      detection.
      *(Resource base + ``RestEndpointDescriptor`` dataclass at
      ``webservice.extensions.rest_endpoint_protocol``; framework-free
      so the actual HTTP mount layer can be Flask-, ASGI-, or stdlib-
      backed. ``ext_router.mount_extension_routes`` walks
      ``RestEndpointExtension.__subclasses__``, validates each
      descriptor (canonical HTTP method, leading-slash suffix,
      non-empty endpoint list), refuses duplicate ``ext_name`` across
      classes and duplicate ``(method, path_suffix)`` within a single
      class, and returns a frozen :class:`MountManifest`. Wired into
      ``app_pychestrate_main.register_service_extensions`` after the
      plugin-api catalog build so misconfigured extensions fail loud
      at startup. The ``extensions=`` injection seam keeps the
      collision tests off the live ``__subclasses__`` tree.)*
- [~] T2.6 — Ship `HealthExtensionEndpoints` and
      `ExampleEchoEndpoints` reference extensions under
      `pychestrate-ext-example`.
      *(``ExampleEchoEndpoints`` reference impl landed in-tree at
      ``webservice.extensions.rest_endpoint_example``; declares
      ``GET /api/v1/ext/example/echo`` and a stub ``echo`` handler.
      ``HealthExtensionEndpoints`` plus the out-of-tree
      ``pychestrate-ext-example`` distribution remain pending.)*
- [ ] T2.7 — Wire every controller's `required_permissions` to
      `1-rbac` permission keys.
- [ ] T2.8 — Enforce `auth.mode_conflict` rejection when two
      authentication modes are asserted.
- [ ] T2.9 — Implement `Accept: application/vnd.pychestrate.v1+json`
      content-type version negotiation.

### M3 — Hardening

- [ ] T3.1 — Implement `versioning.record_deprecation_hit` and
      attach `Deprecation`, `Sunset`, `Link: rel="successor-version"`
      headers on annotated routes.
- [ ] T3.2 — Build the machine-readable changelog feed at
      `GET /api/v1/_meta/changelog`.
- [ ] T3.3 — Emit every metric in requirements.md NFR-3
      (`pychestrate_api_*`).
- [ ] T3.4 — Emit every log event
      (`api.request.served`, `api.request.rejected`,
      `api.deprecation.hit`, `api.extension.route.mounted`,
      `api.rate_limit.exceeded`, `api.idempotency.replay`).
- [ ] T3.5 — Add trace spans `api.dispatch`, `api.version_resolve`,
      `api.auth`, `api.authorize`, `api.rate_limit`,
      `api.idempotency`, `api.handler`, `api.handler.ext`.
- [ ] T3.6 — Sweeper job that prunes
      `api_idempotency_records` past `expires_at`.
- [ ] T3.7 — 30 s wall-clock timeout wrapper for every extension
      handler; handler errors do not leak into next request state.
- [ ] T3.8 — Load-test at 200 req/s per pod and hold p95 < 100 ms on
      `GET` core reads.
- [ ] T3.9 — Sphinx docs for every controller, the
      `RestEndpointExtension` base, and the versioning policy.

## Test Tasks

- [ ] TT-1 — Unit tests covering every EARS acceptance criterion in
      Requirements 1–5 (versioning, resource coverage, auth modes,
      extension namespace, rate limiting).
- [ ] TT-2 — Hypothesis property tests: Property 1 (cross-version
      compatibility), Property 2 (idempotency replay determinism),
      Property 3 (pagination totality), 1000 cases each.
- [ ] TT-3 — Integration test: end-to-end dispatch of a testbase run
      via `POST /api/v1/runs` that exercises the Phase 3 slice and
      asserts every response field matches the domain repository
      state.
- [ ] TT-4 — Extension-point test: load
      `pychestrate-ext-example` out-of-tree, hit
      `/api/v1/ext/example/echo`, assert sandbox gates a capability
      removal with `403 ext.capability_denied`, and assert collision
      with a duplicate `ext_name` fails startup with
      `ConfigurationError`.
- [ ] TT-5 — Contract test: the generated OpenAPI doc at
      `/api/v1/_meta/openapi.json` round-trips through a schema
      validator and is consumed by the `8-cli` generator without
      error.

## Definition of Done

- [ ] All EARS requirements have passing acceptance tests
- [ ] Property-based tests pass across 1000+ generated cases each
- [ ] Extension surface has the `HealthExtensionEndpoints` and
      `ExampleEchoEndpoints` in-tree references and at least one
      test-only override at a different `PRECEDENCE`
- [ ] Metrics / logs / traces emitted per requirements.md NFR-3
- [ ] Sphinx docs generated for public and internal APIs
- [ ] Code conforms to AGENTS.md coding standards (no mutable defaults,
      explicit returns, named parameter passing, type hints on every
      param, no behavior-modifying decorators)
- [ ] No TODO / FIXME left in shipped code
- [ ] Feature listed in the Definition of Done for Phase 3 (minimal
      slice) and Phase 10 (full hardening) in
      specs/implementation-plan.md
