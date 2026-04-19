# 9-wc-secret-editor — Tasks

## Milestones

- **M1 — Skeleton:** `<pyc-secret-editor>` registered, fetches metadata, renders read-only view themed via tokens, plaintext-guard hard-refuses plaintext-carrying responses.
- **M2 — Core Behavior:** Buffered edits, ACL editor + preview, save with reason, rotate / revoke with confirmation, audit link rendering, RBAC-driven affordance visibility.
- **M3 — Hardening:** Property tests, client metrics, accessibility, idempotency keys, conflict handling, Sphinx docs.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Scaffold `source/site/automojo/pychestrate/webservice/webinterface/components/pyc-secret-editor/` with TypeScript build wiring.
- [ ] T1.2 — Implement `pyc-secret-editor.ts::PycSecretEditor` Custom Element with observed attributes `secret-id`, `read-only`, `require-confirm-label`, `aria-label`.
- [ ] T1.3 — Implement `plaintext-guard.ts` scanning JSON for forbidden field names and emitting `pyc-secret-editor-policy-violation` on match.
- [ ] T1.4 — Implement `transport/secret-transport.ts` fetching `/api/v1/secrets/{secret_id}/metadata` and rendering read-only view.
- [ ] T1.5 — Author `styles.css` referencing `--pyc-secret-editor-*` tokens, multi-line per AGENTS.md.
- [ ] T1.6 — Populate `slot="audit-link"` with the audit URL and count.
- [ ] T1.7 — Serve bundle at `/ui/components/pyc-secret-editor/pyc-secret-editor.js`.

### M2 — Core Behavior

- [ ] T2.1 — Implement `edit-buffer.ts` with `load`, `apply`, `reset`, `delta`, `isDirty`.
- [ ] T2.2 — Implement `acl-editor.ts` with row add/remove and 300 ms debounced `/acl/preview` call.
- [ ] T2.3 — Wire `save()` performing `PATCH` with delta + reason; refresh metadata; emit `pyc-secret-editor-saved`.
- [ ] T2.4 — Implement `danger-zone.ts` for rotate and revoke flows with typed-label confirmation.
- [ ] T2.5 — Enforce RBAC-driven affordance visibility using capability flags from metadata.
- [ ] T2.6 — Require non-empty reason (4..512) for every mutation; block submit until provided.
- [ ] T2.7 — Attach idempotency-key header (UUIDv4) to every mutation request.
- [ ] T2.8 — Implement keyboard handler (Ctrl+Enter save, Esc revert, Ctrl+R rotate, Ctrl+Shift+Backspace revoke).

### M3 — Hardening

- [ ] T3.1 — Beacon client metrics per design.md Observability.
- [ ] T3.2 — Benchmark NFR-1: TTI p95 < 250 ms, preview p95 < 400 ms, submit p95 < 800 ms. Fail CI on regression.
- [ ] T3.3 — Axe audit: labels associated to inputs, focus ring honored, danger-zone confirm has `role="dialog"`; fail CI on violations.
- [ ] T3.4 — Handle 409 Conflict (stale `revision`) with merge banner and explicit discard.
- [ ] T3.5 — Handle 403 with read-only banner and missing-permissions messaging.
- [ ] T3.6 — Sphinx authoring doc: tag contract, attributes, properties, events, slots, tokens, security guarantees, a11y.
- [ ] T3.7 — Static lint: no `localStorage` / `sessionStorage` reads or writes anywhere in the component; fail CI on violation.
- [ ] T3.8 — Verify no hard-coded colors / hex / absolute font sizes in `styles.css`.

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement in requirements.md (Requirements 1–4).
- [ ] TT-2 — Property-based tests implementing Property 1 (no plaintext in any mutation body), Property 2 (reversible buffered edits), Property 3 (ACL preview / post-submit consistency) at 1000 cases each.
- [ ] TT-3 — Integration test: Phase 10 scenario — load a secret, change label + add an ACL entry, preview shows new grant, confirm, submit, assert `pyc-secret-editor-saved` fires and metadata refreshes.
- [ ] TT-4 — Plaintext-leak regression test: stub server returns metadata with a `plaintext` field; element refuses to render and emits `pyc-secret-editor-policy-violation`; metric counter increments.
- [ ] TT-5 — Browser E2E (Playwright-style): open a secret in the admin UI, rotate flow requires reason, revoke flow requires typed label; verify UI disables controls during in-flight mutations.
- [ ] TT-6 — RBAC affordance test: load as a user lacking `secrets.acl.edit`; ACL controls hidden and attempting to submit is a no-op.
- [ ] TT-7 — Idempotency-key test: simulate a retry scenario where the first PATCH was accepted but response dropped; element's retry with the same idempotency key does not double-apply.

## Definition of Done

- [ ] All EARS requirements have passing acceptance tests
- [ ] Property-based tests pass across 1000+ generated cases each
- [ ] Extension surface (if any) has at least one in-tree reference
      implementation and one test-only override using a different `PRECEDENCE`
- [ ] Metrics / logs / traces emitted per requirements.md NFR-3
- [ ] Sphinx docs generated for public and internal APIs
- [ ] Code conforms to AGENTS.md coding standards (no mutable defaults,
      explicit returns, named parameter passing, type hints on every param,
      no behavior-modifying decorators)
- [ ] No TODO / FIXME left in shipped code
- [ ] Feature listed in the Definition of Done for its owning phase in
      specs/implementation-plan.md
