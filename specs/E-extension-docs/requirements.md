# E-extension-docs — Requirements

## Introduction

E-extension-docs is the generated documentation site that enumerates
every declared factory protocol and every declared resource extension
base class, with contracts, shipped reference implementations, and
schema/capability metadata. It is produced from source (Sphinx + a
small catalog-walker extension) and published per
`10-release-channels`. It ships in Phase 10 alongside `E-plugin-api`
and `E-extension-pack-template`.

## Requirements

### Requirement 1: Source-driven catalog pages

**User Story:** As an extension author, I want a published page for
every factory protocol and resource extension base, with its
classmethod signatures, schema version, capability requirements, and
the in-tree reference implementation, so that I can write a
conforming implementation without reading core source.

**Acceptance Criteria (EARS):**

1. WHEN the docs build runs THEN the system SHALL walk the
   `FactoryProtocolCatalog` and `ResourceExtensionCatalog` and emit
   one page per entry under `extensions/protocols/<name>.rst` and
   `extensions/resources/<base>.rst`.
2. IF a catalog entry has no reference implementation THEN the page
   SHALL note this explicitly and SHALL include a "contribute a
   reference" link to the relevant feature spec.
3. WHERE a protocol requires capabilities THEN the page SHALL list
   them with links to the vocabulary definition in
   `E-extension-sandbox`.

### Requirement 2: Stability and deprecation visibility

**User Story:** As an external plugin author, I want to filter the
docs to only published (external-stable) protocols and see
deprecation status, so that I do not build against internal-only
APIs.

**Acceptance Criteria (EARS):**

1. WHEN a page is emitted THEN the system SHALL stamp the page with
   `stability` (internal / published) and any deprecation window
   from `E-plugin-api`.
2. WHERE the caller browses with the `Published only` toggle THEN
   the sidebar SHALL hide internal-only entries and keep anchors
   stable for linked published pages.

### Requirement 3: Schema version and compat table

**User Story:** As a service operator reading docs while planning a
service upgrade, I want to see the protocol schema version for each
shipped reference implementation and a cross-check table against the
running service's declared catalog versions, so that I can plan
schema bumps and deprecations.

**Acceptance Criteria (EARS):**

1. WHEN the docs build runs in the service repo THEN the system
   SHALL include a table of
   `(protocol, declared_schema_version, reference_impl_version,
   external_published_yes_no)`.
2. WHERE the service is built from a tagged release THEN the table
   SHALL include the release tag so users can correlate with their
   installed service.

### Requirement 4: Live examples from reference implementations

**User Story:** As a new extension author, I want the reference
implementation's code embedded in the protocol page, so that I can
copy a known-good baseline.

**Acceptance Criteria (EARS):**

1. WHEN rendering a protocol page THEN the system SHALL embed the
   reference factory's class body (or the first classmethod if it is
   long) using Sphinx's `literalinclude` directive.
2. IF the reference file has moved THEN the build SHALL fail closed
   with a readable error rather than silently omit the example.

## Property-Based Test Requirements

### Property 1: Exhaustive page coverage

- **Invariant:** For any set of declared protocols and resource
  bases, the docs build emits exactly one page per entry — no
  duplicates, no omissions.
- **Generator:** random catalog snapshots.
- **Assertion:** Output file set equals catalog entry set by name.
- **Sample size:** 1000 generated cases.

### Property 2: Link integrity

- **Invariant:** For any generated docs tree, every internal
  `:ref:` and `:doc:` target resolves and no page is orphaned from
  the toctree.
- **Generator:** random catalog snapshots.
- **Assertion:** Sphinx `make linkcheck -W` passes with zero broken
  or orphaned pages.
- **Sample size:** 1000 generated cases.

### Property 3: Stability filter closure

- **Invariant:** For any filter toggle state, published-only and
  all-entries navigation produce prefix-consistent URL sets
  (published ⊂ all).
- **Generator:** random catalogs with mixed stability.
- **Assertion:** Every URL in the published set also appears in the
  all set, and internal-only entries never appear in the published
  set.
- **Sample size:** 1000 generated cases.

## Non-Functional Requirements

- **NFR-1 (Performance):** Full docs build completes in under 90 s
  on the reference machine for up to 500 catalog entries.
- **NFR-2 (Security):** Docs build does not execute extension code;
  only introspects class signatures and attributes. External links
  validated via `linkcheck` only, not embedded.
- **NFR-3 (Observability):** Metrics
  `pychestrate_extension_docs_pages_emitted_total{kind}`,
  `pychestrate_extension_docs_broken_links_total`; log events
  `pychestrate_extension_docs_build_started`,
  `pychestrate_extension_docs_build_completed`,
  `pychestrate_extension_docs_build_failed`; trace span
  `pychestrate_extension.docs.build`.
- **NFR-4 (Reliability):** Fail-closed on missing reference files;
  fail-closed on broken `:ref:` targets; never publish partial
  content.

## Out of Scope

- User-facing service feature docs (owned per-feature).
- External stability contract (`E-plugin-api`).
- Pack scaffolding (`E-extension-pack-template`).

## Dependencies

- **Depends on:** `E-factory-protocols`, `E-resource-extensions`,
  `E-extension-sandbox`, `E-plugin-api`, `10-release-channels`.
- **Depended on by:** extension authors, auditors.
- **Extension points exposed:** none.
