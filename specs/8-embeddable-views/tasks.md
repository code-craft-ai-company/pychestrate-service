# 8-embeddable-views — Tasks

## Milestones

- **M1 — Skeleton:** Fixed view-kind catalog, one signing key
  minted into `1-secrets-vault`, `run_detail` end-to-end:
  issuance endpoint, embed render endpoint, signature verification.
- **M2 — Core Behavior:** All five view kinds
  (`run_detail`, `run_log_stream`, `artifact_preview`,
  `pipeline_dag`, `project_dashboard_tile`), inline bearer token
  with permission intersection, origin allow-listing with CSP,
  key rotation with 7-day grace, forced revoke endpoint.
- **M3 — Hardening:** Verification p99 < 5 ms benchmark, full
  metric/log/trace coverage, Sphinx docs, integration with Layer 9
  WebComponents.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Land `embed_signing_keys` and
      `embed_issuance_audit` tables via
      `EntityMigrationExtension` pack.
- [ ] T1.2 — Mint an initial signing key at service startup if
      none exists; store the secret in `1-secrets-vault` under
      `embed.signing_key.<key_id>`.
- [ ] T1.3 — Implement `view_catalog.register_view_kinds` with
      the five fixed view kinds.
- [ ] T1.4 — Implement `signing.issue_signed_url` composing
      `"<view_kind>|<resource_id>|<audience>|<expires_unix>|<key_id>"`
      signed with HMAC-SHA-256.
- [ ] T1.5 — Implement `signing.verify_signed_url` with
      constant-time compare and TTL check.
- [ ] T1.6 — Implement `renderer.render_embed_document`
      minimal HTML emitter for the `run_detail` view kind.
- [ ] T1.7 — Wire `POST /api/v1/projects/{id}/embeds` and
      `GET /embed/<view_kind>/<resource_id>` controllers.

### M2 — Core Behavior

- [ ] T2.1 — Extend `view_catalog` to cover
      `run_log_stream`, `artifact_preview`, `pipeline_dag`,
      `project_dashboard_tile` with each view's declared
      read-scope and `supports_anonymous` flag.
- [ ] T2.2 — Implement `inline_token.mint_inline_token` minting
      a bearer token scoped to the intersection of
      `issuing_principal_permissions` and
      `view_kind.declared_read_scope`; `exp` matches URL TTL.
- [ ] T2.3 — Enforce origin allow-listing in
      `embed_controller` and set
      `Content-Security-Policy: frame-ancestors <origins>` and
      `X-Frame-Options` headers.
- [ ] T2.4 — Implement
      `key_service.rotate_signing_key` with `in_grace` role and
      7-day default `grace_expires_at`.
- [ ] T2.5 — Implement
      `key_service.revoke_signing_key` for immediate revocation.
- [ ] T2.6 — Implement
      `key_service.resolve_key_by_id` distinguishing
      `unknown` from `expired`; cache with single-flight.
- [ ] T2.7 — Wire
      `GET /api/v1/embeds/_meta/keys`,
      `POST .../keys:rotate`,
      `POST .../keys/{key_id}:revoke`.
- [ ] T2.8 — Add `Accept: application/json` variant to
      `GET /embed/...` returning the JSON descriptor.
- [ ] T2.9 — Emit paste-ready `iframe_snippet` and
      `webcomponent_snippet` in the issuance response.

### M3 — Hardening

- [ ] T3.1 — Benchmark `verify_signed_url` hot path; hit
      p99 < 5 ms cold and p99 < 1 ms warm.
- [ ] T3.2 — Emit every metric in requirements.md NFR-3.
- [ ] T3.3 — Emit every log event
      (`embed.url_issued|verified|rejected|expired|signing_key_rotated|signing_key_revoked|inline_token_minted`).
- [ ] T3.4 — Add trace spans `embed.issue`, `embed.verify`,
      `embed.render`, `embed.mint_inline_token`, `embed.key_lookup`.
- [ ] T3.5 — Integrate `9-wc-log-stream`,
      `9-wc-result-viewer`, `9-wc-pipeline-dag`, `9-wc-metric-tile`
      components into the rendered HTML with inline-token
      attributes.
- [ ] T3.6 — Startup check asserting every `view_kind` has a
      matching Layer 9 component; refuse to start otherwise with
      `ConfigurationError`.
- [ ] T3.7 — Audit-log writer for every issuance and every key
      action.
- [ ] T3.8 — Sphinx docs for the signing contract, view catalog,
      and operator key-rotation runbook.

## Test Tasks

- [ ] TT-1 — Unit tests covering every EARS acceptance criterion in
      Requirements 1–5.
- [ ] TT-2 — Hypothesis property tests: Property 1 (tamper
      invalidates signature), Property 2 (verification latency
      bound), Property 3 (audience binding), 1000 cases each.
- [ ] TT-3 — Integration test: issue a `run_detail` URL, fetch it
      from a whitelisted origin, assert the rendered HTML loads
      the `pyc-run-detail` component with a valid inline token
      that can hit `/api/v1/runs/<id>` but NOT
      `/api/v1/projects/<other>/...`.
- [ ] TT-4 — Rotation test: sign a URL under `key-A`, rotate to
      `key-B`, assert the URL still verifies during grace;
      advance past grace, assert it fails
      `embed.signing_key_expired`.
- [ ] TT-5 — Revocation test: sign under `key-A`, revoke `key-A`,
      assert the URL fails `embed.signing_key_unknown`
      immediately (no grace honored on revoke).
- [ ] TT-6 — Origin test: request an embed with a spoofed
      `Origin` not in the allow-list; assert `403
      embed.origin_not_allowed`.

## Definition of Done

- [ ] All EARS requirements have passing acceptance tests
- [ ] Property-based tests pass across 1000+ generated cases each
- [ ] No extension surface — the view-kind catalog is fixed;
      catalog changes require an in-tree code review
- [ ] Metrics / logs / traces emitted per requirements.md NFR-3
- [ ] Sphinx docs generated for public and internal APIs plus an
      operator rotation runbook
- [ ] Code conforms to AGENTS.md coding standards (no mutable defaults,
      explicit returns, named parameter passing, type hints on every
      param, no behavior-modifying decorators)
- [ ] No TODO / FIXME left in shipped code
- [ ] Feature listed in the Definition of Done for Phase 10 —
      Public Surface & Extensibility Completion in
      specs/implementation-plan.md
