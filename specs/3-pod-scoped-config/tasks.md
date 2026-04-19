# 3-pod-scoped-config — Tasks

## Milestones

- **M1 — Skeleton:** `pod_run` scope resolver decorator, basic variable
  set/get/delete, purge on release, REST CRUD.
- **M2 — Core Behavior:** Secret grants, ACL enforcement, bearer mint +
  dereference, envelope rendering hook for dispatcher.
- **M3 — Hardening:** Rotation handling, metrics, audit integration,
  perf target, docs.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Migration pack: `pod_run_variable`, `pod_run_secret_grant`,
  `pod_scoped_secret_access_log`, `pod_scoped_bearer` tables.
- [ ] T1.2 — DTOs: `ResolvedVariable`, `DereferencedSecret`,
  `SecretPolicy`, `BearerReference`.
- [ ] T1.3 — Repositories for the four tables.
- [ ] T1.4 — `resolver_decorator.py`: wraps every registered
  `variable_resolver` factory with a `pod_run`-first lookup path.
- [ ] T1.5 — REST routes for variable CRUD under
  `/projects/{pid}/runs/{rid}/variables/{name}`.
- [ ] T1.6 — Purge subscriber on
  `entity.pod.state_changed{to=released}` calling
  `purge_run_scope`.
- [ ] T1.7 — Publish `entity.pod.scoped_variable_set|deleted` and
  `entity.pod.scoped_purged`.

### M2 — Core Behavior

- [ ] T2.1 — `secret_decorator.py`: wraps every registered
  `secret_ref_dereferencer` with `pod_run` ACL check and audit row
  write.
- [ ] T2.2 — `service.grant_pod_run_secret` + REST
  `POST /runs/{rid}/secret-grants`.
- [ ] T2.3 — `bearer.py`: mint (256-bit random), dereference (mTLS
  client match), expire/consume.
- [ ] T2.4 — REST `POST /clients/bearer/dereference` accepting only
  mTLS-authenticated sessions.
- [ ] T2.5 — Envelope-render hook: `render_env(run_id)` used by
  `5-job-dispatch` to bake values + bearers into the envelope.
- [ ] T2.6 — Audit-log writes on every secret access (`denied` and
  `allowed`).
- [ ] T2.7 — Locked-variable enforcement: writes against higher scopes
  that would shadow a locked `pod_run` value rejected with
  `VariableLocked`.

### M3 — Hardening

- [ ] T3.1 — Subscriber on `entity.secrets_backend.rotated` invalidates
  cached dereferences for the affected `secret_ref`.
- [ ] T3.2 — Purge completion under 5 s for bearer revocation,
  <= 500 ms for variable rows.
- [ ] T3.3 — Emit all metrics in design.md Observability.
- [ ] T3.4 — Trace spans as listed in design.md.
- [ ] T3.5 — Log-redaction filter ensures rendered envelopes never log
  secret values; test with deliberately-spoof payloads.
- [ ] T3.6 — Sphinx docs: REST routes, internal API, scope semantics
  contract document for `variable_resolver` /
  `secret_ref_dereferencer` implementers.

## Test Tasks

- [ ] TT-1 — Unit tests for each EARS clause in Requirements 1-3.
- [ ] TT-2 — Hypothesis tests for Property 1 (scope precedence totality),
  Property 2 (purge totality), Property 3 (bearer unforgeability).
- [ ] TT-3 — Integration test: start a run on a dynamic pod -> set
  pod-run variables and grants -> dispatch -> client dereferences
  bearer -> pod releases -> subsequent dereference raises `ScopeEnded`.
- [ ] TT-4 — Extension-point test: a test-only `variable_resolver`
  subclass at `PRECEDENCE=40` participates in the `pod_run`-first
  resolver chain without special-casing.
- [ ] TT-5 — ACL test: a bearer issued for run A cannot be dereferenced
  by a client whose binding is run B's pod.
- [ ] TT-6 — Rotation test: secret rotated mid-run; next dereference
  returns the new value; audit records both accesses.

## Definition of Done

- [ ] All EARS requirements have passing acceptance tests.
- [ ] Property-based tests pass across 1000+ generated cases each.
- [ ] Existing `variable_resolver` and `secret_ref_dereferencer`
  in-tree references (from `2-global-variables` and `1-secrets-vault`)
  honor `pod_run` scope and are covered by end-to-end tests.
- [ ] Metrics / logs / traces emitted per requirements.md NFR-3.
- [ ] Sphinx docs generated.
- [ ] Code conforms to AGENTS.md coding standards.
- [ ] No TODO / FIXME left in shipped code.
- [ ] Feature listed in the Definition of Done for Phase 8 in
  specs/implementation-plan.md.
