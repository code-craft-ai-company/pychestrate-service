# E-extension-manifest — Tasks

## Milestones

- **M1 — Skeleton:** `ExtensionManifest` dataclass, YAML parser for
  required fields only, `ManifestRegistry` singleton, strict-mode
  missing-manifest refusal.
- **M2 — Core Behavior:** Full v1 schema (all optional fields),
  PEP 440 version-window enforcement, declared-vs-delivered inventory
  cross-check, CLI validate subcommand, rescan refresh integration.
- **M3 — Hardening:** Metrics/logs/traces, unknown-key warnings,
  mtime-based parse caching, admin REST surface, Sphinx schema docs.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Create the package tree under
  `source/site/ccai/pychestrate/webservice/extension/manifest/`.
- [ ] T1.2 — Implement `ExtensionManifest` dataclass in `schema.py`
  with the required fields only (`name`, `version`, `schema_version`).
- [ ] T1.3 — Implement `find_manifest_for_distribution` via
  `importlib.metadata.Distribution.files`.
- [ ] T1.4 — Implement `parse_manifest` reading the file with
  `yaml.safe_load`, validating required fields, and returning the
  dataclass.
- [ ] T1.5 — Implement `ManifestRegistry` singleton with `register`,
  `record_refusal`, `get`, `list_all`, `list_refusals`.
- [ ] T1.6 — Wire the manifest pass into `E-extension-host`'s bootstrap
  between module discovery and class registration.

### M2 — Core Behavior

- [ ] T2.1 — Extend `ExtensionManifest` with every optional field from
  design.md and implement their YAML → dataclass mapping.
- [ ] T2.2 — Implement `validate_version_window` using
  `packaging.version.Version`.
- [ ] T2.3 — Implement `validate_declared_inventory` reconciling
  manifest `protocols`/`resources` against the post-import delivered
  sets.
- [ ] T2.4 — Implement strict-mode refusal paths with
  `ConfigurationError` messages built via `os.linesep.join`.
- [ ] T2.5 — Implement `pychestrate-admin manifest validate` CLI.
- [ ] T2.6 — Wire rescan refresh: re-resolve manifests for newly-seen
  distributions and skip unchanged ones by `(mtime, sha256)`.
- [ ] T2.7 — Add the permissive-mode default manifest synthesis and
  `pychestrate_extension_manifest_synthesized` warning.

### M3 — Hardening

- [ ] T3.1 — Emit every metric, log event, and trace span per design.md
  Observability.
- [ ] T3.2 — Emit `extension.manifest_parsed`,
  `extension.manifest_rejected`, `extension.manifest_missing` bus
  events.
- [ ] T3.3 — Implement unknown-key warnings with
  `pychestrate_extension_manifest_unknown_key`.
- [ ] T3.4 — Add `GET /admin/extensions/{name}/manifest` REST route
  with permission `extensions.read`.
- [ ] T3.5 — Generate Sphinx docs for the v1 manifest schema; wire into
  `E-extension-docs`.
- [ ] T3.6 — Remove all TODO/FIXME; pass lint + type checks.

## Test Tasks

- [ ] TT-1 — Unit tests covering every EARS requirement, including
  every error path.
- [ ] TT-2 — Property-based tests for Property 1 (fail-closed outside
  window), 2 (round-trip), 3 (inventory consistency) at 1000 cases
  each.
- [ ] TT-3 — Integration test: service boots with (a) a valid
  manifest, (b) a malformed YAML manifest, (c) an out-of-window
  manifest; outcomes match requirements (load, fail with readable
  error, refuse with bus event).
- [ ] TT-4 — Extension-point test: out-of-tree
  `pychestrate-ext-sample-manifest` package ships with a v1 manifest,
  host consumes it, operator sees the manifest via REST; a second
  package with missing manifest is refused in strict and synthesized
  in permissive.

## Definition of Done

- [ ] All EARS requirements have passing acceptance tests.
- [ ] Property-based tests pass across 1000+ generated cases each.
- [ ] Schema v1 documented in `E-extension-docs`.
- [ ] Metrics / logs / traces emitted per requirements.md NFR-3.
- [ ] Code conforms to AGENTS.md coding standards.
- [ ] No TODO / FIXME left in shipped code.
- [ ] Feature listed in the Phase 0.5 exit criterion in
      specs/implementation-plan.md.
