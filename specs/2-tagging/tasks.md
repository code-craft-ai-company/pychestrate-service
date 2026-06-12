# 2-tagging — Tasks

## Milestones

- **M1 — Skeleton:** `TagAssignment` table lands, `canonicalize_tag` +
  taxonomy registry wired to `E-resource-extensions`, assign/remove/list
  endpoints work for `project` entity kind.
- **M2 — Core Behavior:** All registered entity kinds supported; boolean
  expression search complete; in-tree reference taxonomies shipped.
- **M3 — Hardening:** Orphan cleanup subscribers, rate limits, metrics,
  expression filter-to-empty safety, extension collision detection.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Migration for `tag_assignments` with unique and lookup
      indexes from design.md.
- [ ] T1.2 — Implement `entities.py` (`Taxonomy`, `TagAssignment`).
- [ ] T1.3 — Implement `TagTaxonomyExtension` base and
      `TaxonomyRegistry` that loads on `on_service_ready`.
- [ ] T1.4 — Implement `canonicalize_tag` in `canonical.py`, including
      the case-sensitive-value branch.
- [ ] T1.5 — Implement `repository.upsert_assignment`,
      `delete_assignment`, `list_assignments_for_entity`.
- [ ] T1.6 — Implement `service.assign_tag`, `service.remove_tag`,
      `service.list_tags`.
- [ ] T1.7 — Wire REST endpoints for assign/remove/list under
      `restapi/versions/v1/tags.py` for `project` entity kind.

### M2 — Core Behavior

- [ ] T2.1 — Extend entity-kind registry to cover `resource`, `pod`,
      `job`, `artifact` and allow extensions to register new kinds.
- [ ] T2.2 — Implement `expression.parse` (recursive-descent parser
      for the grammar in requirement 3).
- [ ] T2.3 — Implement `expression.to_sql` emitting `EXISTS` joins.
- [ ] T2.4 — Implement `service.search_entities` calling the parser
      and SQL compiler, honoring `limit/offset`.
- [ ] T2.5 — Ship reference taxonomies (`EnvironmentTaxonomy`,
      `PlatformTaxonomy`, `ComplianceTaxonomy`) under
      `ccai/extensions/pychestrate/tagging/`.
- [ ] T2.6 — `GET /api/v1/taxonomies` endpoint (filtered by caller
      read perms).
- [ ] T2.7 — Wire the search endpoint
      `GET /api/v1/tags/search?kind=&expr=&limit=&offset=`.

### M3 — Hardening

- [ ] T3.1 — Subscribe to `entity.*.deleted` topics and purge orphan
      assignments; one subscriber per owning entity kind.
- [ ] T3.2 — Add rate-limiter rules (200/min assign, 300/min search).
- [ ] T3.3 — Emit all metrics listed in design.md Observability.
- [ ] T3.4 — Structured logs + trace spans
      (`tag.assign|remove|search|canonicalize`).
- [ ] T3.5 — Taxonomy collision detection: two extensions with the
      same `taxonomy_name` and equal `PRECEDENCE` make the service
      refuse to start with a readable multiline
      `ConfigurationError`.
- [ ] T3.6 — Expression filter-to-empty safety test — a caller
      without read access on a referenced taxonomy gets zero
      matches from that term rather than an error.

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement in
      requirements.md (Requirements 1–4).
- [ ] TT-2 — Property-based tests for Property 1 (canonicalization
      idempotence) and Property 2 (set equality under reorder /
      duplication) using `hypothesis`.
- [ ] TT-3 — Integration test: tag a project with three taxonomies,
      search by a 2-term AND expression, remove one tag, re-search and
      verify the updated result set.
- [ ] TT-4 — Extension-point test: out-of-tree
      `DeploymentRingTaxonomy` registers, accepts
      `deployment-ring:ring0|ring1|ring2`, and rejects
      `deployment-ring:ring9`.

## Definition of Done

- [ ] All EARS requirements have passing acceptance tests
- [ ] Property-based tests pass across 1000+ generated cases each
- [ ] Extension surface (`TagTaxonomyExtension`) has in-tree
      references and a test-only override at a different `PRECEDENCE`
- [ ] Metrics / logs / traces emitted per requirements.md NFR-3
- [ ] Sphinx docs generated for public and internal APIs
- [ ] Code conforms to AGENTS.md coding standards (no mutable defaults,
      explicit returns, named parameter passing, type hints on every
      param, no behavior-modifying decorators)
- [ ] No TODO / FIXME left in shipped code
- [ ] Feature listed in the Definition of Done for Phase 1 in
      specs/implementation-plan.md
