# E-resource-extensions — Tasks

## Milestones

- **M1 — Skeleton:** `ResourceExtensionCatalog` exists, a single declared
  base registers at import time, and `collect_kinds` returns an empty
  list.
- **M2 — Core Behavior:** Snapshot-driven rebuild, declared kinds
  discovered from the host snapshot, duplicate detection, CLI listing,
  per-phase base declarations populated.
- **M3 — Hardening:** Rescan integration, attribute-schema validation,
  metrics/logs/traces, Sphinx doc integration, stability tagging.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Create the package tree under
  `source/site/ccai/pychestrate/webservice/extension/resources/`.
- [ ] T1.2 — Implement `ResourceExtensionBaseEntry` and
  `ResourceExtensionKindEntry` dataclasses in `entry.py`.
- [ ] T1.3 — Implement `ResourceExtensionCatalog` with `register_base`,
  `list_bases`, `collect_kinds` (returning empty initially); duplicate
  base names raise `ConfigurationError`.
- [ ] T1.4 — Implement `get_resource_extension_catalog()` singleton
  accessor and wire bootstrap into the app factory.
- [ ] T1.5 — Add a single sample base declaration
  `_declarations/pod_member_kind.py` under the resources package.

### M2 — Core Behavior

- [ ] T2.1 — Implement `rebuild_from_host_snapshot` that walks the host
  snapshot's module list and extracts direct subclasses per registered
  base.
- [ ] T2.2 — Add indirect-subclass support gated by
  `allow_indirect_subclasses` flag.
- [ ] T2.3 — Add `kind_name` derivation with warning when
  `resource_kind_name` is missing.
- [ ] T2.4 — Enforce duplicate `kind_name` fail-closed with multiline
  error message.
- [ ] T2.5 — Populate `_declarations/` with a base per Phase 0.5 /
  Phase 1 `resource:` surface from implementation-plan.md
  (`EntityMigrationExtension`, `SystemHealthProbeExtension`,
  `MFAMethodExtension`, `PermissionExtension`, `RoleExtension`,
  `AuditEventTypeExtension`, `ProjectMetadataFieldExtension`,
  `TagTaxonomyExtension`, `NotificationTemplateExtension`,
  `ProjectTemplateExtension`).
- [ ] T2.6 — Add `pychestrate-admin resources list|show` CLI
  subcommands.
- [ ] T2.7 — Add `GET /admin/extensions/resources` REST route under
  `extensions.read`.
- [ ] T2.8 — Subscribe to `extension.loaded` and
  `extension.rescan_completed` to trigger `rebuild_from_host_snapshot`.

### M3 — Hardening

- [ ] T3.1 — Implement attribute-schema validation for bases marked
  `attribute_schema_required = True`.
- [ ] T3.2 — Emit metrics, log events, trace spans per design.md.
- [ ] T3.3 — Emit `extension.resource_base_registered`,
  `extension.resource_kind_registered`,
  `extension.resource_kinds_changed` bus events.
- [ ] T3.4 — Generate Sphinx docs per base and per kind; wire into
  `E-extension-docs`.
- [ ] T3.5 — Tag bases with `stability`; filter in `E-plugin-api`.
- [ ] T3.6 — Remove all TODO/FIXME and pass lint + type checks.

## Test Tasks

- [ ] TT-1 — Unit tests for every EARS requirement.
- [ ] TT-2 — Property-based tests for Property 1 (determinism), 2
  (base isolation), 3 (fail-closed) at 1000 cases each.
- [ ] TT-3 — Integration test: service boots with a synthetic pack
  declaring two bases and three kinds each, catalog returns the correct
  collection, a rescan adds a fourth kind under one base, the diff
  event fires with the correct addition list.
- [ ] TT-4 — Extension-point test: out-of-tree
  `pychestrate-ext-sample-resource` contributes a new kind to an
  existing base, it appears in `collect_kinds`, and a duplicate-name
  pack fails registration cleanly.

## Definition of Done

- [ ] All EARS requirements have passing acceptance tests.
- [ ] Property-based tests pass across 1000+ generated cases each.
- [ ] Every Phase 0.5/Phase 1 `resource:` surface from
      implementation-plan.md has a base declaration shipped with a
      reference in-tree implementation and a test-only second kind under
      the same base.
- [ ] Metrics / logs / traces emitted per requirements.md NFR-3.
- [ ] Sphinx docs generated for every declared base.
- [ ] Code conforms to AGENTS.md coding standards.
- [ ] No TODO / FIXME left in shipped code.
- [ ] Feature listed in the Phase 0.5 exit criterion in
      specs/implementation-plan.md.
