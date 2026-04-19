# 2-tagging — Requirements

## Introduction

`2-tagging` is the shared taxonomy and tag-assignment model for Layer 2. A
single tag store serves every taggable entity in the system — projects,
resources, jobs, pods, and artifacts — so searches, dashboards, and policies
can operate against one consistent vocabulary. Tags are organized by
**taxonomy**: a named, optionally validated, optionally color-coded category
(e.g., `environment`, `platform`, `compliance`). Taxonomies can be contributed
by extensions via `TagTaxonomyExtension`. This feature ships in
**Phase 1 — Identity & Projects** and sits alongside `2-projects`,
`2-global-variables`, and `2-notification-hub` as the core Layer 2 services
that every later feature depends on.

## Requirements

### Requirement 1: Tag assignment and removal on any taggable entity

**User Story:** As a user, I want to attach a tag to a project, resource,
pod, job, or artifact, so that searches and dashboards can filter by the
same vocabulary across every domain.

**Acceptance Criteria (EARS):**

1. WHEN `POST /api/v1/tags/{entity_kind}/{entity_id}` is received with
   body `{tag}` (canonical form `taxonomy:value`) THEN the system SHALL
   upsert a `TagAssignment` row and return `200 OK`; if no such row
   existed THEN the response SHALL use status `201 Created`.
2. IF `entity_kind` is not in the registered set (`project`,
   `resource`, `pod`, `job`, `artifact`, or anything registered by
   extension) THEN the system SHALL respond `400 Bad Request`.
3. IF the `taxonomy:value` pair fails the taxonomy's validator THEN the
   system SHALL respond `422 Unprocessable Entity` with the
   taxonomy-supplied error message.
4. WHEN `DELETE /api/v1/tags/{entity_kind}/{entity_id}/{tag}` is received
   THEN the system SHALL remove the assignment and return `204`.

### Requirement 2: Canonical tag form and case normalization

**User Story:** As a platform admin, I want incoming tag strings normalized
to one canonical form, so that `ENV:Prod`, `env:prod`, and
` env : prod ` all resolve to the same stored tag.

**Acceptance Criteria (EARS):**

1. WHEN a tag string is submitted THEN the system SHALL canonicalize by
   lowercasing the taxonomy and value, stripping whitespace, and
   verifying the shape `^[a-z][a-z0-9_]{0,31}:[a-z0-9][a-z0-9_-]{0,63}$`.
2. IF a taxonomy declares `case_sensitive_value = True` THEN the system
   SHALL preserve the value's original case while still stripping
   whitespace and validating length.
3. IF canonicalization fails THEN the system SHALL respond
   `400 Bad Request` with a message naming the offending input and the
   expected pattern.

### Requirement 3: Search entities by tag expression

**User Story:** As a user, I want to filter entities by
`AND`/`OR`/`NOT` combinations of tags, so that dashboards and pickers can
surface, for example, all `environment:prod AND compliance:soc2` jobs.

**Acceptance Criteria (EARS):**

1. WHEN `GET /api/v1/tags/search?kind=<k>&expr=<e>` is received with a
   valid boolean expression `e` THEN the system SHALL return the
   matching entity ids paginated by `?limit=&offset=`.
2. IF the expression fails the grammar
   `tag-expr := tag | "(" expr ")" | expr ("AND"|"OR") expr | "NOT" expr`
   THEN the system SHALL respond `400 Bad Request` with a parse-error
   location.
3. WHILE the expression references taxonomies the caller cannot read
   THEN the system SHALL filter those terms to an empty set rather
   than leak existence — an expression like
   `secret-taxonomy:foo OR environment:prod` resolves as if the
   unreadable taxonomy contributed no matches.

### Requirement 4: TagTaxonomyExtension registration

**User Story:** As an extension author, I want to register a new taxonomy
with a validator, allowed values list, and color, so that my extension's
domain concepts (e.g., `deployment-ring`) are first-class tags.

**Acceptance Criteria (EARS):**

1. WHEN the host loads a `TagTaxonomyExtension` subclass THEN the system
   SHALL register the taxonomy in the tag registry with its
   `taxonomy_name`, `case_sensitive_value`, `allowed_values` (or
   `None` for open), `validator` classmethod, `color_hex`, and
   `description`.
2. IF two `TagTaxonomyExtension` subclasses declare the same
   `taxonomy_name` AND have different `PRECEDENCE` THEN the lower
   `PRECEDENCE` wins and the loser SHALL be logged at level WARNING;
   IF they have equal `PRECEDENCE` THEN the service SHALL raise
   `ConfigurationError` on startup.
3. WHEN an assignment is attempted against an unregistered taxonomy
   THEN the system SHALL respond `400 Bad Request` listing the
   known taxonomies (redacted per the caller's read permissions).

## Property-Based Test Requirements

### Property 1: Canonicalization is idempotent

- **Invariant:** For any input string `s`,
  `canonicalize_tag(canonicalize_tag(s)) == canonicalize_tag(s)` or
  both raise `TagValidationError` with identical message text.
- **Generator:** `hypothesis.strategies.text(alphabet=st.characters(), min_size=0, max_size=128)`
  plus a strategy that injects `:` randomly to exercise the split.
- **Assertion:** For 1000 cases, double-apply equals single-apply or
  both raise equally.
- **Sample size:** 1000 generated cases.

### Property 2: Tag-set equality under reorder and duplication

- **Invariant:** For any list of tag strings `L` applied to the same
  entity, the resulting stored set `S(L)` satisfies
  `S(L) == S(shuffle(L))` and `S(L) == S(L + L)`.
- **Generator:** `hypothesis.strategies.lists` of valid canonicalized
  tags with size 0–20, composed with a shuffler and a duplicator.
- **Assertion:** The set of `(taxonomy, value)` pairs stored on the
  entity is identical across all three variants.
- **Sample size:** 1000 generated cases.

## Non-Functional Requirements

- **NFR-1 (Performance):** Tag assign p95 ≤ 50 ms; tag search with a
  3-term expression p95 ≤ 150 ms over 1M assignments.
- **NFR-2 (Security):** Writes gated by the per-entity-kind permission
  owned by that entity's feature (e.g., assigning to a project
  requires `project.tag.write`). Reads are filtered by the entity's
  own read permission.
- **NFR-3 (Observability):** Counters
  `pychestrate_tag_assigned_total{taxonomy,entity_kind}`,
  `pychestrate_tag_removed_total{taxonomy,entity_kind}`,
  `pychestrate_tag_search_total{result_count_bucket}`,
  `pychestrate_tag_validator_reject_total{taxonomy}`;
  histogram `pychestrate_tag_search_duration_seconds`;
  log events `tag.assigned`, `tag.removed`, `tag.search`;
  trace spans `tag.assign`, `tag.search`.
- **NFR-4 (Reliability):** Assignments are idempotent; identical
  repeated calls produce a single stored row. Orphaned
  `TagAssignment` rows are cleaned up by subscribers to
  `entity.*.deleted` events.

## Out of Scope

- Tag-based access control — permissions remain keyed by role, not
  tag. (Attribute-based access control may be considered in a
  future phase.)
- Auto-tagging via rules — explicitly deferred; extensions can
  subscribe to events if they want to implement their own auto-tagger.

## Dependencies

- **Depends on:** `0-persistence`, `0-message-bus`,
  `1-authentication`, `1-rbac`, `2-projects`.
- **Depended on by:** `2-retention-policies` (policies key on tags),
  `4-resource-inventory`, `5-job-dispatch`, `5-artifact-store`,
  `6-test-catalog`, `7-project-dashboards`.
- **Extension points exposed:** `resource: TagTaxonomyExtension`.
