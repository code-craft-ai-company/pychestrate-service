# E-extension-pack-template — Requirements

## Introduction

E-extension-pack-template is the canonical cookiecutter-style starter
repository for a `pychestrate-ext-<name>` package. It produces a
working, conforming source tree with `pychestrate_ext.yaml`,
`pyproject.toml`, an example `FactoryExtension` implementation, an
example `ResourceExtension` kind, a CI pipeline, test harness, and
README. It ships in Phase 10 after the Layer E surface has stabilized.

## Requirements

### Requirement 1: Deterministic scaffold generation

**User Story:** As a new extension author, I want to run a single
command to generate a fresh, passing `pychestrate-ext-<name>` package,
so that I can start contributing without reverse-engineering the repo
conventions.

**Acceptance Criteria (EARS):**

1. WHEN `pychestrate-admin pack-template new --name=<name>` is run
   THEN the system SHALL materialize a directory `pychestrate-ext-<name>/`
   containing: `pychestrate_ext.yaml`, `pyproject.toml`,
   `source/packages/automojo/factories/pychestrate/<name>/...`,
   `source/packages/automojo/extensions/pychestrate/<name>/...`,
   `tests/`, `.github/workflows/ci.yaml`, `README.rst`, `AGENTS.md`.
2. IF the target directory already exists and is non-empty THEN the
   system SHALL refuse to overwrite and exit non-zero with a readable
   message.
3. WHERE the caller passes `--protocol=<name>` THEN the system SHALL
   seed a `FactoryExtension` implementation for that protocol using
   the catalog's classmethod signature as a starting stub.

### Requirement 2: Conforming default content

**User Story:** As a service reviewer, I want generated packs to pass
lint, type checks, and the Layer E manifest validator on first try,
so that submitted packs start from a known-good baseline.

**Acceptance Criteria (EARS):**

1. WHEN the generated pack is installed into a fresh Pychestrate dev
   environment THEN the system SHALL load the pack's manifest
   without warnings, register its sample factory and resource kind,
   and pass `pychestrate-admin manifest validate`.
2. WHEN `make test` is run inside the generated pack THEN the pack's
   unit, property, and contract tests SHALL pass.
3. WHERE the pack is built with `poetry build` THEN the system SHALL
   produce a wheel with the `pychestrate_ext.yaml` file included as
   a distribution resource.

### Requirement 3: Self-test that exercises Layer E gates

**User Story:** As a service operator, I want every generated pack to
ship with a contract test that loads it against a test fixture of
the running service, so that regressions in Layer E surfaces are
caught upstream of merge.

**Acceptance Criteria (EARS):**

1. WHEN the template includes `tests/contract/test_layer_e.py` THEN
   the system SHALL exercise manifest parse, host load, compat
   check, and (if applicable) sandbox capability grant via a
   reusable fixture from `pychestrate-service`'s test harness.
2. WHERE the pack declares at least one subscription THEN the
   template SHALL include a hook-delivery contract test that
   publishes the topic and asserts receipt under a per-delivery
   timeout.
3. WHEN the contract tests run THEN the system SHALL emit a
   machine-readable summary compatible with `testbase`'s
   `testrun_summary.json` shape.

### Requirement 4: Template versioning and regeneration

**User Story:** As a platform maintainer, I want to bump the template
version over time and provide a regenerate-in-place helper, so that
existing extension authors can migrate their packs to new conventions
without manual diffing.

**Acceptance Criteria (EARS):**

1. WHEN `pychestrate-admin pack-template upgrade` is run inside an
   existing pack THEN the system SHALL print a diff of files the
   current template would change, with a `--apply` flag to write
   them.
2. IF the pack's `TEMPLATE_VERSION` marker is absent THEN the
   command SHALL refuse to apply and ask the user to specify the
   baseline version explicitly.

## Property-Based Test Requirements

### Property 1: Name-normalization idempotence

- **Invariant:** For any input name string, the generated pack's
  `name` field in `pychestrate_ext.yaml` is the normalized (lowercase,
  hyphen-separated, matches `^[a-z][a-z0-9-]*$`) form; normalization
  is idempotent.
- **Generator:** hypothesis text strategy with mixed-case, underscores,
  non-ASCII seeds.
- **Assertion:** `normalize(normalize(x)) == normalize(x)`; generated
  manifest passes the manifest parser.
- **Sample size:** 1000 generated cases.

### Property 2: Regenerate-without-drift

- **Invariant:** For any freshly-generated pack, running
  `pack-template upgrade --apply` against an unchanged template
  version produces a zero-size diff.
- **Generator:** permutations of generated pack inputs.
- **Assertion:** `git diff` over the pack produces no hunks.
- **Sample size:** 1000 generated cases.

### Property 3: Layer E gate satisfaction

- **Invariant:** For any name + protocol combination accepted by the
  generator, loading the resulting pack into a fresh service
  instance yields zero `extension.load_failed`,
  `extension.compat_rejected`, or
  `extension.manifest_rejected` events.
- **Generator:** random (name, protocol) pairs drawn from the
  catalog's published protocols.
- **Assertion:** The fresh service's Layer E failure counters stay
  at zero.
- **Sample size:** 1000 generated cases.

## Non-Functional Requirements

- **NFR-1 (Performance):** Template generation completes in under
  3 s on the reference machine; regenerate diff completes in under
  2 s.
- **NFR-2 (Security):** Template input validation refuses names
  outside `^[a-z][a-z0-9-]*$`; generated CI workflow pins action
  versions to SHAs.
- **NFR-3 (Observability):** Template CLI emits structured log lines
  `pychestrate_extension_pack_template_generated`,
  `pychestrate_extension_pack_template_upgrade_diff`,
  `pychestrate_extension_pack_template_upgrade_applied`; metrics
  `pychestrate_extension_pack_template_generations_total{result}`.
- **NFR-4 (Reliability):** Generation is atomic: either the target
  directory is fully written or not created at all. No half-written
  state on failure.

## Out of Scope

- Published docs site (`E-extension-docs`).
- Stable-API surface definition (`E-plugin-api`).
- Sandbox vocabulary authoring (`E-extension-sandbox`).

## Dependencies

- **Depends on:** `E-extension-manifest`, `E-factory-protocols`,
  `E-resource-extensions`, `E-extension-compat-check`.
- **Depended on by:** extension authors (external).
- **Extension points exposed:** none.
