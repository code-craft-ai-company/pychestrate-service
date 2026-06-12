# E-extension-precedence — Requirements

## Introduction

E-extension-precedence preserves the upstream `codecraftai-extension`
PRECEDENCE semantics (lower numeric value = higher priority) and adds a
per-site override file — `etc/pychestrate/extension_precedence.yaml` —
that re-pins PRECEDENCE for a specific extension without editing its
source. The override file is read at bootstrap and on rescan; it is
authoritative over in-source PRECEDENCE values. This feature ships in
Phase 0.5 and is the mechanism operators use to shim local overrides
into the factory chain when an upstream pack ships with an undesirable
default.

## Requirements

### Requirement 1: Source-precedence preservation

**User Story:** As an extension author, I want Pychestrate to honor my
declared `PRECEDENCE` exactly as-is when no site override exists, so
that my extension behaves identically in a default deployment.

**Acceptance Criteria (EARS):**

1. WHEN no override file is present THEN the system SHALL sort the
   factory chain solely by each class's declared `PRECEDENCE` in
   ascending order.
2. IF two classes share the same `PRECEDENCE` in the default sort THEN
   the system SHALL tie-break by fully qualified class name.

### Requirement 2: Site override file semantics

**User Story:** As a service operator, I want to re-pin PRECEDENCE for a
specific factory class via a single YAML file, so that I can change
resolution order without forking extension source code.

**Acceptance Criteria (EARS):**

1. WHEN the file `etc/pychestrate/extension_precedence.yaml` (or the
   path named by `PYCHESTRATE_PRECEDENCE_FILE`) is present THEN the
   system SHALL read it at bootstrap and on every rescan.
2. WHEN the file declares a pin entry `{qualname: <str>, precedence:
   <int>}` THEN the system SHALL override the class's declared
   `PRECEDENCE` with the pinned value.
3. IF the file references a `qualname` that does not match any loaded
   factory THEN the system SHALL emit a
   `pychestrate_extension_precedence_pin_unresolved` warning and
   continue.
4. IF two pin entries share a `qualname` THEN the system SHALL raise
   `ConfigurationError` naming the conflicting entries.

### Requirement 3: Deterministic reproducibility

**User Story:** As a platform maintainer, I want the effective
precedence order to be deterministic and reproducible across identical
inputs, so that node-to-node drift is detectable.

**Acceptance Criteria (EARS):**

1. WHEN `snapshot_digest()` is computed THEN the system SHALL include
   the effective precedence values (post-override) for every loaded
   factory.
2. WHERE two service instances load identical extension packs and
   identical override files THEN their `snapshot_digest()` values
   SHALL be equal.
3. IF an override file is modified between bootstrap and rescan THEN
   the system SHALL emit `extension.precedence_override_changed` with
   the diff (added/removed/changed pins).

### Requirement 4: Priority band discipline

**User Story:** As a platform maintainer, I want a documented set of
priority bands so that authors and operators pick numeric PRECEDENCE
values from a coherent scheme.

**Acceptance Criteria (EARS):**

1. WHEN an extension sets PRECEDENCE in the reserved `[0, 99]` band
   THEN the system SHALL refuse to load unless the manifest declares
   `capabilities: [pychestrate.platform.precedence_low]`.
2. WHERE the pin file sets a precedence in the reserved band for a
   class whose manifest lacks the capability THEN the system SHALL
   reject the pin at bootstrap.

## Property-Based Test Requirements

### Property 1: Override-by-order determinism

- **Invariant:** For any N extensions with distinct declared
  PRECEDENCE values and an override file that re-pins a subset, the
  effective sort is deterministic and reproducible across repeated
  loads and across shuffles of discovery order.
- **Generator:** permutations of
  `(qualname, declared_precedence, optional_pin)` tuples.
- **Assertion:** Effective chain is byte-identical across 10 shuffles
  and across two independent host instances.
- **Sample size:** 1000 generated cases.

### Property 2: Pin monotonicity

- **Invariant:** For any factory class, raising its pinned PRECEDENCE
  number (less priority) never increases its resolution preference;
  lowering it (more priority) never decreases its preference.
- **Generator:** baseline chain plus a delta over one factory's pinned
  value.
- **Assertion:** Relative rank of the class in the post-override chain
  respects the direction of the delta.
- **Sample size:** 1000 generated cases.

### Property 3: Unresolved-pin no-op

- **Invariant:** For any pin entry whose qualname does not match any
  loaded class, the effective chain is identical to the no-override
  case for all loaded classes.
- **Generator:** pin file with random fake qualnames.
- **Assertion:** Loaded-class chain equality with and without the
  fake pins; warnings emitted match the count of fake pins.
- **Sample size:** 1000 generated cases.

## Non-Functional Requirements

- **NFR-1 (Performance):** Override parse + chain re-sort completes in
  under 5 ms for 500 loaded factories and 100 pin entries.
- **NFR-2 (Security):** Override file read under the service account
  only; path resolves to an allow-listed directory
  (`/etc/pychestrate/` or the explicit env path).
- **NFR-3 (Observability):** Metrics
  `pychestrate_extension_precedence_pins_active{qualname}`,
  `pychestrate_extension_precedence_override_file_reads_total`;
  log events `pychestrate_extension_precedence_loaded`,
  `pychestrate_extension_precedence_pin_unresolved`,
  `pychestrate_extension_precedence_override_changed`; trace span
  `pychestrate_extension.precedence.apply`.
- **NFR-4 (Reliability):** Fail-closed on duplicate pin entries and on
  reserved-band violations; warn-only on unresolved pins.

## Out of Scope

- Per-project precedence overrides (deferred to Phase 10 pending demand).
- Capability enforcement (`E-extension-sandbox`).
- Precedence UI (`E-extension-registry-ui`).

## Dependencies

- **Depends on:** `E-extension-host`, `E-extension-manifest`.
- **Depended on by:** `E-extension-registry-ui`,
  `E-extension-sandbox`, `E-plugin-api`.
- **Extension points exposed:** none; this feature constrains the
  semantics of the existing PRECEDENCE attribute.
