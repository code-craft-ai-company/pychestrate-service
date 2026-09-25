# 0-config-formats — Tasks

Milestones are ordered so that the protocol and the canonical model land
before any format implementation, and projection lands last — nothing
writes to the database until parsing and validation are proven.

## M1 — Protocol, models, loader

- [x] `domains.py`: `ConfigDocumentDomain` enum (`resource_spec`,
      `landscape`, `topology`, `credentials`) and default basenames.
      (R1.1)
- [x] `models.py`: canonical dataclasses for all four domains, plus
      `DeviceAddresses` with a total, never-raising `resolve`. (R1.2,
      R1.4, R1.5, R3.3)
- [x] `protocol.py`: `ConfigDocumentFormatProtocol`, registered in the
      `E-factory-protocols` catalog with an entry naming this feature as
      owner. (R2.1, R2.2, R2.3)
- [x] `errors.py` + `validation.py`: `ConfigDocumentParseError`,
      `ConfigDocumentDomainBleedError`, `InlineSecretRejectedError`,
      `ValidationReport` with stable diagnostic codes. (R2.6, R8.1)
- [x] `resolver.py`: presence-dir path resolution, the
      `PYCHESTRATE_CONFIG_<DOMAIN>_PATH` overrides, `.d/` directory
      support with duplicate detection, domain-bleed pre-check. (R4.1,
      R4.2, R4.3, R4.6, R4.7)
- [x] `loader.py`: resolve → parse → validate → accumulate, absent file
      is not an error. (R4.5, R8.2)
- [x] Registration guards: unknown domain rejected at registration;
      shadowed `(domain, format_name)` warns. (R2.4, R2.5)
- [x] Unit tests for the loader with a stub format; property tests for
      `DeviceAddresses.resolve`.

**Exit:** a stub format registers, loads a file, and produces a canonical
document; nothing touches the database. **Met** — 26 tests in
`source/testroots/ccai/tests/singlehost/pychestrate/webservice/phase15/`.

Added beyond the original list: `merging.py` (the `.d` concatenation of
Requirement 4.6 is canonical-model knowledge, so it does not belong on
the format protocol), and two protocol methods the domain-bleed check
needs — `claimed_top_level_keys` and `probe_top_level_keys`.

## M2 — The `codecraftai` default formats

- [ ] `codecraftai_landscape.py`: `environment` / `apod` / `clients` /
      `infrastructure` / `services`, `addresses` mapping onto the plane
      model, legacy `host` string with deprecation warning, `skip: true`
      retained as `skipped`, `vpn:` block. (R3.2, R3.3, R3.4, R3.5, R3.6)
- [ ] `codecraftai_topology.py`, `codecraftai_resource_spec.py`.
- [ ] `codecraftai_credentials.py` over `CredentialManager`, with inline
      secret rejection and batch reference resolution. (R6.1, R6.2, R6.3)
- [ ] Redaction pass across reports, audit entries, logs, and API
      responses. (R6.4)
- [ ] All four registered at `PRECEDENCE = 1000` from the package
      `__init__`. (R3.1, R3.7)
- [ ] Flip `ConfigDocumentFormatProtocol.is_published` to True once
      `configdocs/formats/codecraftai_landscape.py` exists. `8-plugin-api`'s
      catalog validator imports every `published_reference`, so it must stay
      False until that module lands or `test_validate_catalog_resolves_every_reference`
      fails.
- [ ] Contract tests against `codecraftai-landscaping/specs/` fixtures
      and the `codecraftai-provisioning` emit format.

**Exit:** a stock `landscape.yaml` — hand-written or emitted by
`provision apply` — parses and validates with no configuration.

## M3 — Format selection and admin surface

- [ ] `config.format.<domain>` through `2-global-variables`, default
      `codecraftai`, resolved once at bootstrap. (R5.1, R5.3)
- [ ] Startup failure listing registered format names when a configured
      format is unknown — no silent fallback. (R5.2)
- [ ] `GET /api/v1/admin/config-formats` + admin page: per domain the
      selected format, resolving class, source path, last-loaded
      timestamp, and `not configured` state. (R4.5, R5.4)
- [ ] Audit kind `config.format.changed`. (R5.5)
- [ ] Metric `pychestrate_config_document_load` by domain/format/outcome.
      (R8.5)
- [ ] RBAC: reads gated on `system:config.read`, format changes on
      `system:config.write`, both granted to the system-admin role.
- [ ] A fake enterprise format at `PRECEDENCE = 100` proving per-domain
      override in isolation.

**Exit:** an enterprise format can be selected for one domain from the
admin surface while the other three stay on `codecraftai`.

## M4 — Projection onto inventory and pods

- [ ] Alembic migration: `canonical_identity` (nullable, indexed) and
      `provenance` (default `manual`) on `resources_resource`.
- [ ] `projection/resources.py`: change set of `create` / `update` /
      `adopt_identity` / `mark_unreferenced`; never deletes. (R7.2,
      R7.3, R7.5)
- [ ] Canonical identity derivation from the landscaping identity model.
      (R7.1)
- [ ] Duplicate-identity-within-document failure naming both locations.
      (R7.4)
- [ ] `projection/pods.py`: canonical topology → `3-pod-definitions`
      specs, reconciled against the existing member-kind extensions.
- [ ] Dry-run entry point returning the projection diff without writing;
      errors block projection entirely. (R8.3, R8.4)
- [ ] CLI: `pychestrate-admin config import --domain <d> [--dry-run]`.
- [ ] Import-twice idempotence test; adoption test against rows created
      by the pre-existing REST path.

**Exit:** a landscape file imports into inventory, a re-import is a
no-op, and a hand-entered row for the same machine is adopted rather
than duplicated.

## M5 — Documentation

- [ ] Userguide: authoring each document, the `.d/` layout, and the
      one-file-per-domain rule.
- [ ] Plugin-API page for `config_document_format` under
      `8-plugin-api` / `E-plugin-api`, with a worked enterprise example.
- [ ] `specs/implementation-plan.md`: catalog entry, protocol listed
      under `E-factory-protocols`, and this feature added to Phase 0.5.
- [ ] ROADMAP entry and CHANGELOG.

## Open questions

- **Topology vs. pod definitions.** `3-pod-definitions` already owns pod
  membership with its own member-kind extensions. Whether the topology
  document becomes the authoring surface for those definitions or stays a
  separate overlay affects M4 and needs a decision before that milestone.
- **Reload semantics.** M1–M4 load at bootstrap. Whether a running
  service can reload a document without a restart — and what happens to
  in-flight leases when inventory shifts underneath them — is deferred.
- **`resource_spec` scope.** The other three domains have established
  ecosystem formats; the resource-specification format needs its shape
  pinned down against `4-resource-inventory`'s existing kind attributes
  before M2.
