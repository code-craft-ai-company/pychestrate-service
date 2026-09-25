# 0-config-formats — Requirements

## Introduction

The `0-config-formats` feature owns how Pychestrate reads the
externally-authored documents that describe the world it orchestrates:
**resource specifications**, **landscapes**, **topologies**, and
**credentials**. These documents are authored outside the service — by a
lab owner, a provisioning run, a network team, or an enterprise CMDB —
and Pychestrate is their consumer, not their author.

Today Pychestrate has no such reader. Machines reach the database only
through hand-entry against the `4-resource-inventory` REST surface, whose
`device` resource kind carries eight flat string attributes, and pods are
described by a `spec_json.members[]` list with three member kinds. The
surrounding `codecraftai` ecosystem already models all of this far more
completely — `codecraftai-landscaping` (`Landscape`, `AutomationPod`,
`LandscapeDevice`, `DeviceAddressSet`, coordinator couplings, clusters and
services), `codecraftai-credentials` (`CredentialManager`), and
`codecraftai-provisioning`, which emits a `landscape.yaml` explicitly
specified as directly consumable by landscaping. Pychestrate sits outside
that pipeline and duplicates a thinner version of its model.

This feature closes that gap without hard-coding the ecosystem's file
formats into the service. It defines:

1. A **canonical in-memory document model** per domain, which is the only
   thing the rest of Pychestrate ever sees.
2. A **`config_document_format` factory protocol** that parses a concrete
   file format into that canonical model.
3. **The `codecraftai` formats as the shipped default** for every domain.
4. A **one-file-per-domain layout** under the presence directory, so no
   domain's document is ever merged into another's or into
   `settings.config`.
5. A **per-domain format selection knob** so an enterprise deployment can
   register its own implementation and read its own formats without
   forking the service.

The feature sits in Phase 0.5 beside `E-extension-host` and
`E-factory-protocols`, because the document readers must exist before
Layer 3 and Layer 4 can be populated from anything but hand-entry. It is
consumed by `4-resource-inventory`, `3-pod-definitions`,
`3-static-pods`, and `1-secrets-vault`.

## Requirements

### Requirement 1: Canonical Document Model per Domain

**User Story:** As a Pychestrate feature author, I want to consume a
single typed model per document domain regardless of the file format on
disk, so that adding a new format never touches my code.

**Acceptance Criteria (EARS):**

1. THE SYSTEM SHALL declare exactly four document domains:
   `resource_spec`, `landscape`, `topology`, and `credentials`.
2. THE SYSTEM SHALL define one frozen canonical dataclass per domain —
   `ResourceSpecDocument`, `LandscapeDocument`, `TopologyDocument`,
   `CredentialsDocument` — each carrying `schema_version`,
   `source_path`, `source_format`, and its domain payload.
3. WHEN any Pychestrate module consumes a configuration document THE
   SYSTEM SHALL hand it the canonical dataclass and SHALL NOT expose the
   parsed raw document, the file text, or a format-specific type.
4. WHERE a format carries information the canonical model has no field
   for THE SYSTEM SHALL preserve it under the document's
   `extra_attributes` mapping rather than discarding it silently.
5. THE SYSTEM SHALL make every canonical model serialisable back to a
   plain mapping so that a document can be round-tripped and diffed.

### Requirement 2: `config_document_format` Factory Protocol

**User Story:** As an enterprise integrator, I want to teach Pychestrate
to read my company's inventory format by registering a class, so that I
do not have to convert my files or fork the service.

**Acceptance Criteria (EARS):**

1. THE SYSTEM SHALL declare a `FactoryProtocolBase` subclass with
   `factory_protocol_name = "config_document_format"` and
   `protocol_schema_version = 1`.
2. THE SYSTEM SHALL require every implementation to declare
   `document_domain() -> str` (one of the four domains) and
   `format_name() -> str` (a stable slug, e.g. `"codecraftai"`).
3. THE SYSTEM SHALL require every implementation to provide
   `file_basenames() -> Tuple[str, ...]`, `parse(*, path, text) -> <canonical
   document>`, and `validate(*, document) -> ValidationReport`.
4. WHEN an implementation is registered whose `document_domain()` is not a
   declared domain THE SYSTEM SHALL raise `ConfigurationError` naming the
   class and the accepted domains.
5. WHEN two implementations declare the same `(document_domain,
   format_name)` pair THE SYSTEM SHALL resolve by `PRECEDENCE` (lower
   wins) and SHALL emit a `pychestrate_config_format_shadowed` warning
   naming both qualified class names.
6. WHERE an implementation raises during `parse` THE SYSTEM SHALL wrap
   the cause in `ConfigDocumentParseError` carrying the domain, format
   name, source path, and — when the format can supply one — the line
   number, and SHALL NOT fall back to another format.

### Requirement 3: `codecraftai` Formats Ship as the Default

**User Story:** As a Pychestrate operator using the standard toolchain, I
want the ecosystem formats to work with no configuration at all.

**Acceptance Criteria (EARS):**

1. THE SYSTEM SHALL ship an in-tree implementation with
   `format_name() == "codecraftai"` for each of the four domains, each
   registered at `PRECEDENCE = 1000`.
2. THE SYSTEM SHALL parse the `codecraftai-landscaping` landscape schema
   — top-level `environment`, `apod`, and the `clients`,
   `infrastructure`, and `services` sub-sections — into
   `LandscapeDocument`.
3. WHEN a landscape device entry carries an `addresses` mapping THE
   SYSTEM SHALL map it onto the canonical address-plane model preserving
   `public`, `private`, and per-provider `overlay` planes, matching
   `codecraftai-landscaping/specs/device-address-set`.
4. WHEN a landscape device entry carries only the legacy single `host`
   string THE SYSTEM SHALL populate the private plane from it and record
   a `legacy_host_field` deprecation warning on the validation report.
5. WHEN a device entry declares `skip: true` THE SYSTEM SHALL retain the
   entry in the canonical document marked `skipped` rather than dropping
   it, so that a later inventory sync does not read the omission as a
   removal.
6. THE SYSTEM SHALL parse a landscape emitted by
   `codecraftai-provisioning`'s `EMIT_LANDSCAPE_INVENTORY` stage without
   translation, including its `vpn:` block.
7. IF no format is configured for a domain THEN THE SYSTEM SHALL use
   `codecraftai`.

### Requirement 4: One File per Domain, Always Separate

**User Story:** As an operator, I want each kind of document in its own
file so I can source-control, review, and rotate them independently.

**Acceptance Criteria (EARS):**

1. THE SYSTEM SHALL resolve configuration documents from
   `<presence_dir>/config/`, where `presence_dir` is resolved by
   :mod:`ccai.pychestrate.webservice.pychestrate_presence`.
2. THE SYSTEM SHALL read each domain from its own file and SHALL NOT
   accept two domains in one file, even when a format could express both.
3. IF a document file contains a top-level key belonging to another
   domain THEN THE SYSTEM SHALL fail validation with
   `ConfigDocumentDomainBleedError` naming the offending key, rather than
   parsing it.
4. THE SYSTEM SHALL NOT merge any configuration document into
   `settings.config`, and `settings.config` SHALL NOT be a fallback
   source for any of the four domains.
5. WHERE a domain's file is absent THE SYSTEM SHALL treat that domain as
   empty and SHALL NOT fail service startup; the corresponding admin
   surface SHALL report the domain as `not configured`.
6. WHERE a domain names a directory rather than a file THE SYSTEM SHALL
   load every matching file in lexical order and concatenate their
   entries, failing on duplicate identities across files.
7. THE SYSTEM SHALL support a per-domain absolute-path override through
   the environment variables `PYCHESTRATE_CONFIG_<DOMAIN>_PATH`.

### Requirement 5: Per-Domain Format Selection

**User Story:** As an enterprise operator, I want to switch one domain to
my own format while leaving the others on the defaults.

**Acceptance Criteria (EARS):**

1. THE SYSTEM SHALL read the selected format for each domain from the
   global variable `config.format.<domain>`, defaulting to `codecraftai`.
2. WHEN a domain's configured format names no registered implementation
   THE SYSTEM SHALL fail startup with `ConfigurationError` listing the
   registered format names for that domain, and SHALL NOT silently fall
   back to `codecraftai`.
3. THE SYSTEM SHALL allow each domain's format to be selected
   independently; selecting a non-default format for one domain SHALL NOT
   affect the others.
4. THE SYSTEM SHALL expose the resolved per-domain format on the admin
   surface `GET /api/v1/admin/config-formats`, listing for each domain the
   selected format, the resolving class, the source path, and the
   last-loaded timestamp.
5. WHEN an operator changes a domain's format THE SYSTEM SHALL record an
   audit entry of kind `config.format.changed` carrying the domain and
   both format names.

### Requirement 6: Credentials Documents Carry References, Never Secrets

**User Story:** As a security reviewer, I want the credentials document to
be safe to commit, so that a lab inventory checked into git leaks nothing.

**Acceptance Criteria (EARS):**

1. THE SYSTEM SHALL model a credentials document as a set of named
   *references* resolved through `codecraftai-credentials`'
   `CredentialManager` or the `1-secrets-vault` backend.
2. IF a credentials document contains an inline secret value — a private
   key body, password, or bearer token — THEN THE SYSTEM SHALL reject the
   document with `InlineSecretRejectedError` naming the credential and
   the offending key, and SHALL NOT log the value.
3. WHEN a landscape device references a credential by name THE SYSTEM
   SHALL validate at load time that the name resolves, and SHALL report
   every unresolved reference in one validation report rather than
   failing on the first.
4. THE SYSTEM SHALL redact credential material from every validation
   report, audit entry, log line, and admin API response produced by this
   feature.

### Requirement 7: Stable Identity Across Formats

**User Story:** As an operator, I want the same machine to be one row no
matter which format described it, so that switching formats or importing
twice does not fork my inventory.

**Acceptance Criteria (EARS):**

1. THE SYSTEM SHALL derive a canonical device identity from the
   landscaping identity model — `friendly_id` / `moniker` / `identity`
   plus `role` — rather than from `4-resource-inventory`'s current
   `(hostname, mac_address)` hash.
2. WHEN a canonical document is projected onto `4-resource-inventory` THE
   SYSTEM SHALL record the canonical identity on the resource row so that
   re-import of the same device updates rather than duplicates.
3. WHERE an existing resource row predates this feature and carries only
   the legacy identity hash THE SYSTEM SHALL match it on
   `(hostname, mac_address)` once, adopt the canonical identity, and
   record an `identity_adopted` audit entry.
4. WHEN two entries in one document resolve to the same canonical
   identity THE SYSTEM SHALL fail validation naming both source
   locations.
5. THE SYSTEM SHALL NOT delete a resource row because a device vanished
   from a document; it SHALL mark the row `unreferenced` and leave
   removal to an explicit operator action.

### Requirement 8: Load-Time Validation and Diagnostics

**User Story:** As an operator, I want one report listing everything wrong
with my documents, so I can fix them in a single pass.

**Acceptance Criteria (EARS):**

1. WHEN a document is loaded THE SYSTEM SHALL produce a
   `ValidationReport` with an `errors` list and a `warnings` list, each
   entry carrying domain, source path, a pointer to the offending
   location, and a stable diagnostic code.
2. THE SYSTEM SHALL accumulate every diagnostic across all four domains
   before raising, rather than aborting at the first error.
3. WHEN validation produces errors THE SYSTEM SHALL refuse to project the
   document onto the database, leaving prior rows untouched.
4. THE SYSTEM SHALL expose a dry-run entry point that parses, validates,
   and reports the projection diff without writing.
5. THE SYSTEM SHALL emit the metric `pychestrate_config_document_load`
   tagged by domain, format, and outcome.
