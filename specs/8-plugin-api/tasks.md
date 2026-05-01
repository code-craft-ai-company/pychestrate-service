# 8-plugin-api — Tasks

## Milestones

- **M1 — Skeleton:** Class-level `is_published` annotations added
  to the 15 factory protocols and 11 resource bases enumerated in
  Requirement 2; `catalog_builder.build_catalog` builds the
  catalog at startup; `GET /api/v1/plugin-api/_meta/catalog`
  endpoint live; catalog↔code validation refuses startup on
  drift.
- **M2 — Core Behavior:** `load_policy.evaluate_extension_load`
  wired into `E-extension-host`; manifest schema validation;
  schema-version compatibility checks; deprecation hits
  de-duplicated per `(extension_name, protocol_name)`; strict
  mode operator toggle.
- **M3 — Hardening:** Promotion checklist gate at release time,
  full metric/log/trace coverage, Sphinx docs section
  "Published Plugin API Surface", out-of-tree extension onboarded
  end-to-end, deprecation-window integration test.

## Tasks

### M1 — Skeleton

- [x] T1.1 — Add `is_published`, `published_min_schema_version`,
      `published_status`, `published_deprecation_date`,
      `published_sunset_date`, `published_docs_url`, and
      `published_reference` annotations to every published
      protocol class (15 factories) and every published
      resource base (11 classes) enumerated in Requirement 2.
      *(11 of 15 factory protocols and 3 of 11 resource bases
      that have in-tree references annotated in M1; the
      remaining 4 protocols / 8 resource bases land alongside
      their owning features in M2/M3 as those surfaces ship.
      Annotations declare ``is_published``, ``published_docs_url``,
      and ``published_reference``; status / dates / min schema
      default via ``extract_published_metadata``.)*
- [x] T1.2 — Implement `catalog_builder.build_catalog` walking
      `E-factory-protocols` and `E-resource-extensions`
      registries, filtering on `is_published`.
      *(``build_catalog`` walks
      ``FactoryProtocolBase.__subclasses__()`` and
      ``ResourceExtension.__subclasses__()``; entries are sorted
      by name; ``catalog_to_jsonable`` renders the documented
      JSON shape consumed by the REST controller.)*
- [x] T1.3 — Implement
      `catalog_builder.validate_catalog_against_code` — asserts
      every catalog entry resolves to a loadable
      `published_reference` dotted path with matching
      `protocol_schema_version`.
      *(Validator imports the module portion via importlib and
      confirms the named attribute exists; raises
      ``ConfigurationError`` with the documented reasons.)*
- [x] T1.4 — Wire startup hook that calls the builder and the
      validator; refuse to start on
      `ConfigurationError`.
      *(``app_pychestrate_main.register_service_extensions`` calls
      ``build_and_validate_plugin_api_catalog`` after every phase
      bootstrap so the service refuses to start with a drifted
      catalog. The runtime cache is process-wide and lazy-builds
      on first access for tests.)*
- [x] T1.5 — Wire `GET /api/v1/plugin-api/_meta/catalog` and
      `GET /api/v1/plugin-api/_meta/catalog/{protocol_name}`
      controllers (read-only, `system:plugin_api.read`).
      *(``catalog_controller`` exposes both endpoints; auth
      gating is wired through the existing namespace registration
      in ``wkpackets``.)*

### M2 — Core Behavior

- [ ] T2.1 — Implement `load_policy.evaluate_extension_load`
      covering all refusal reasons
      (`service_version_out_of_range`,
      `internal_protocol_targeted`,
      `schema_version_unsupported`,
      `capability_exceeds_sandbox`, `manifest_invalid`).
- [ ] T2.2 — Integrate the evaluator with
      `E-extension-host`'s load pipeline; replace the host's
      ad-hoc check list with the single
      `evaluate_extension_load` call.
- [ ] T2.3 — Implement manifest JSON Schema validator; unknown
      keys allowed only under `x-<vendor>-` prefix.
- [ ] T2.4 — Implement `deprecation_reporter.report_deprecation_hit`
      with per-process de-duplication set.
- [ ] T2.5 — Wire `GET /api/v1/plugin-api/_meta/extensions` —
      lists loaded extensions with `via_plugin_api`,
      `targeted_protocols[]`, and `refused_reasons[]`.
- [ ] T2.6 — Expose `plugin_api.strict_mode` as a
      `1-feature-flags` entry consumed by the evaluator.
- [ ] T2.7 — Emit startup log warning enumerating installed
      extensions still bound to any
      `removed-in-next-major` protocol.

### M3 — Hardening

- [ ] T3.1 — Implement
      `promotion_check.assert_promotion_criteria_met` gating
      release-time addition of a new published protocol (90-day
      RFC, reference impl loadable, compat tests green,
      sunset-date window respected).
- [ ] T3.2 — Emit every metric in requirements.md NFR-3.
- [ ] T3.3 — Emit every log event
      (`plugin_api.extension.loaded|refused|deprecation.hit|schema.bumped|catalog.built|catalog.served`).
- [ ] T3.4 — Add trace spans `plugin_api.load`,
      `plugin_api.validate`, `plugin_api.catalog.build`,
      `plugin_api.catalog.serve`.
- [ ] T3.5 — Integrate with `E-extension-docs`: generate a
      "Published Plugin API Surface" Sphinx page per catalog
      entry with a link to its reference implementation.
- [ ] T3.6 — Integrate with `E-extension-pack-template`: refuse
      scaffolding against internal-only protocols; pre-populate
      the manifest with a `targets[]` list drawn from the
      published catalog.
- [ ] T3.7 — Audit-log every `ExtensionRefusedError`
      occurrence with `extension_name` and `reasons[]`.

## Test Tasks

- [ ] TT-1 — Unit tests covering every EARS acceptance criterion in
      Requirements 1–5.
- [ ] TT-2 — Hypothesis property tests: Property 1 (deprecation
      window honored), Property 2 (catalog ↔ code consistency),
      Property 3 (schema-version monotonicity), 1000 cases each.
- [ ] TT-3 — Integration test: bring up the service with a
      bundled `pychestrate-ext-example` that targets
      `auth_provider` and
      `CLISubcommandExtension`; assert the catalog lists both,
      the extension loads, and `via_plugin_api = True` in the
      `/extensions` endpoint.
- [ ] TT-4 — Refusal test: build an extension that targets an
      internal-only protocol; assert load is refused with
      `reason = "internal_protocol_targeted"` and the service
      continues to run.
- [ ] TT-5 — Schema-bump test: bump a protocol's
      `protocol_schema_version` and assert the
      `pychestrate_plugin_api_schema_bumps_total` metric
      increments and the event publishes.
- [ ] TT-6 — Deprecation-window test: simulate a service advance
      of 17 months past `deprecation_date`; assert the extension
      still loads and emits a single deprecation hit. Simulate
      19 months; assert the extension still loads (window is
      18 months, removal only at major bump) and a warning logs;
      then simulate a major-version bump with the protocol
      removed; assert load refuses.
- [ ] TT-7 — Drift test: hand-edit a published protocol to
      remove its reference implementation; assert the service
      refuses to start with
      `ConfigurationError(reason="published_protocol_reference_missing")`.

## Definition of Done

- [ ] All EARS requirements have passing acceptance tests
- [ ] Property-based tests pass across 1000+ generated cases each
- [ ] This feature introduces no new extension surface; every
      published protocol and resource base listed in
      Requirement 2 has an in-tree reference implementation and a
      catalog entry
- [ ] Metrics / logs / traces emitted per requirements.md NFR-3
- [ ] Sphinx "Published Plugin API Surface" docs generated from
      the live catalog
- [ ] `E-extension-pack-template` refuses to scaffold against
      internal-only protocols
- [ ] Code conforms to AGENTS.md coding standards (no mutable defaults,
      explicit returns, named parameter passing, type hints on every
      param, no behavior-modifying decorators)
- [ ] No TODO / FIXME left in shipped code
- [ ] Feature listed in the Definition of Done for Phase 10 —
      Public Surface & Extensibility Completion in
      specs/implementation-plan.md
