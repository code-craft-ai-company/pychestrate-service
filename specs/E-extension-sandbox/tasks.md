# E-extension-sandbox — Tasks

## Milestones

- **M1 — Skeleton:** `CapabilityAuthority` singleton with closed
  vocabulary; manifest-sourced grants populate `active`; pass-through
  authorize methods return True for the existing zero-capability
  default.
- **M2 — Core Behavior:** Factory-call gate raises `PermissionError`
  on denial; hook-delivery gate drops on denial; grant/revoke REST
  endpoints; persistence layer; event emission; audit log
  integration.
- **M3 — Hardening:** Runtime revocation with lifecycle drain of the
  affected extension, metrics/logs/traces, Sphinx docs, integration
  tests against a full Layer 5 dispatch flow.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Create the package tree under
  `source/site/ccai/pychestrate/webservice/extension/sandbox/`.
- [ ] T1.2 — Implement `VOCABULARY` constant and `CapabilityAuthority`
  skeleton with `reload_from_manifests`, `granted_for`.
- [ ] T1.3 — Implement `CapabilityGrantRepo` with list + upsert + mark
  operations against a new `extension_capability_grant` table.
- [ ] T1.4 — Add migration for the table under
  `0-persistence` migration pack.
- [ ] T1.5 — Wire bootstrap so manifests' declared capabilities flow
  into the authority.

### M2 — Core Behavior

- [ ] T2.1 — Implement `authorize_factory_call` raising
  `PermissionError` with `missing_capabilities` attribute.
- [ ] T2.2 — Implement `authorize_hook_delivery` returning bool; wire
  into `SubscriptionRouter._deliver`.
- [ ] T2.3 — Hook the factory authorization into
  `ExtensionHost.create_instance_by_order`,
  `create_instance_for_each`, and override-type paths.
- [ ] T2.4 — Populate `protocol_requirements` by reading
  `required_capabilities` off declared `FactoryProtocolBase`
  subclasses (E-factory-protocols).
- [ ] T2.5 — Implement grant / revoke REST endpoints with
  `extensions.grant` permission gating and audit log entries.
- [ ] T2.6 — Emit `extension.capability_granted`,
  `extension.capability_revoked`, `extension.call_denied`,
  `extension.hook_denied` bus events.
- [ ] T2.7 — Add unknown-capability refusal at manifest parse time
  (feedback loop with `E-extension-manifest`).

### M3 — Hardening

- [ ] T3.1 — Implement active-lease drain: on revoke of a capability
  tied to a long-running lease, signal
  `LifecycleCoordinator.run_on_service_draining` for the affected
  ext.
- [ ] T3.2 — Emit metrics and log events per design.md
  Observability.
- [ ] T3.3 — Integration with `E-extension-registry-ui` to surface
  grant state per extension.
- [ ] T3.4 — Update `E-extension-docs` to publish the vocabulary.
- [ ] T3.5 — End-to-end scenario: a deliberately malicious in-tree
  test extension attempts to dispatch a job without
  `dispatch:jobs`; confirm denial + audit + no dispatch.
- [ ] T3.6 — Remove all TODO/FIXME; pass lint + type checks.

## Test Tasks

- [ ] TT-1 — Unit tests covering every EARS requirement, including
  unknown-capability manifest refusal.
- [ ] TT-2 — Property-based tests for Property 1 (subset invariance),
  2 (delivery-time re-check), 3 (zero-capability safety) at 1000
  cases each.
- [ ] TT-3 — Integration test: grant capability live, ext calls
  succeed; revoke, next call denies within 10 ms; restart preserves
  the revocation.
- [ ] TT-4 — Extension-point test: out-of-tree
  `pychestrate-ext-sample-sandbox` declares capabilities
  `{dispatch:jobs}`; a second pack lacking the capability is
  denied; grant via admin API enables; revoke disables.

## Definition of Done

- [ ] All EARS requirements have passing acceptance tests.
- [ ] Property-based tests pass across 1000+ generated cases each.
- [ ] Reference in-tree extension exercises at least three of the
      five vocabulary entries across factories and hooks; test-only
      override pack demonstrates deny-by-default behavior.
- [ ] Metrics / logs / traces emitted per requirements.md NFR-3.
- [ ] Sphinx docs generated for capability vocabulary and admin
      endpoints.
- [ ] Code conforms to AGENTS.md coding standards.
- [ ] No TODO / FIXME left in shipped code.
- [ ] Feature listed in the Phase 8 exit criterion in
      specs/implementation-plan.md.
