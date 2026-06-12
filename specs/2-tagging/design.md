# 2-tagging — Design

## Architecture

`2-tagging` is a Layer 2 shared service owned by
`ccai.pychestrate.webservice.model.tagging`. It exposes one unified
`TagAssignment` table and one taxonomy registry; every other feature that
needs tagging calls the service rather than implementing its own. The
taxonomy registry is populated at startup by `TagTaxonomyExtension`
subclasses discovered by the `E-extension-host`. An expression parser
compiles user-supplied boolean tag expressions to SQL `EXISTS` subqueries
against `tag_assignments`. Ships in **Phase 1**.

## Data Model

```python
@dataclass
class Taxonomy:
    taxonomy_name: str           # lowercase, matches ^[a-z][a-z0-9_]{0,31}$
    case_sensitive_value: bool
    allowed_values: frozenset[str] | None
    color_hex: str               # "#RRGGBB"
    description: str
    source_extension: str        # ext pack name for audit/UX
    precedence: int

@dataclass
class TagAssignment:
    assignment_id: UUID          # PK
    entity_kind: str             # project | resource | pod | job | artifact | ext-registered
    entity_id: UUID
    taxonomy_name: str
    value: str                   # canonical form; case per taxonomy flag
    assigned_by_user_id: UUID
    assigned_at: datetime
```

Indexes:
- `UNIQUE (entity_kind, entity_id, taxonomy_name, value)` — enforces
  set semantics.
- `INDEX (taxonomy_name, value)` — tag search reverse lookup.
- `INDEX (entity_kind, entity_id)` — list-all-tags-for-entity.

## Interfaces

### Public API

- `POST /api/v1/tags/{entity_kind}/{entity_id}` — body `{tag}`;
  returns `200` / `201`.
- `DELETE /api/v1/tags/{entity_kind}/{entity_id}/{tag}` — returns `204`.
- `GET /api/v1/tags/{entity_kind}/{entity_id}` — list all tags on an
  entity.
- `GET /api/v1/tags/search?kind=<k>&expr=<e>&limit=&offset=` — returns
  `{items: [entity_id,...], total}`.
- `GET /api/v1/taxonomies` — list registered taxonomies (filtered
  by caller's read permissions).

### Internal API

```python
# source/site/ccai/pychestrate/webservice/model/tagging/service.py

def assign_tag(
    *,
    entity_kind: str,
    entity_id: UUID,
    tag: str,
    actor_user_id: UUID,
) -> TagAssignment:
    """
        Canonicalize and assign a tag to an entity; idempotent.

        :param entity_kind: Registered entity kind
        :param entity_id: Target entity id
        :param tag: Raw tag string (canonicalized internally)
        :param actor_user_id: Caller for audit

        :returns: Existing or newly-created assignment
        :raises: TagValidationError, UnknownTaxonomyError, EntityKindError
    """
    ...


def remove_tag(
    *,
    entity_kind: str,
    entity_id: UUID,
    tag: str,
    actor_user_id: UUID,
) -> None:
    ...


def list_tags(
    *,
    entity_kind: str,
    entity_id: UUID,
) -> list[TagAssignment]:
    ...


def search_entities(
    *,
    entity_kind: str,
    expression: str,
    actor_user_id: UUID,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[UUID], int]:
    """
        Evaluate a boolean tag expression and return matching entity ids.

        :param entity_kind: Target entity kind
        :param expression: Boolean tag expression (see grammar)
        :param actor_user_id: Caller for per-taxonomy read filtering
        :param limit: Page size
        :param offset: Page offset

        :returns: (ids, total_count)
        :raises: TagExpressionParseError, EntityKindError
    """
    ...


# source/site/ccai/pychestrate/webservice/model/tagging/canonical.py

def canonicalize_tag(
    *,
    raw: str,
    registry: TaxonomyRegistry,
) -> tuple[str, str]:
    """
        Return (taxonomy_name, canonical_value).

        :param raw: Raw tag string
        :param registry: Loaded taxonomy registry

        :returns: Canonicalized (taxonomy, value)
        :raises: TagValidationError, UnknownTaxonomyError
    """
    ...
```

### Extension Surface

- `resource: TagTaxonomyExtension`
  (`source/site/ccai/pychestrate/webservice/model/tagging/extensions.py`)

```python
class TagTaxonomyExtension(ResourceExtension):
    taxonomy_name: ClassVar[str]
    case_sensitive_value: ClassVar[bool] = False
    allowed_values: ClassVar[frozenset[str] | None] = None
    color_hex: ClassVar[str] = "#808080"
    description: ClassVar[str] = ""
    PRECEDENCE: ClassVar[int] = 1000

    @classmethod
    def validate_value(cls, *, value: str) -> None:
        """Raise TagValidationError on failure."""
        ...
```

Reference impls shipped in-tree under
`ccai/extensions/pychestrate/tagging/`: `EnvironmentTaxonomy`
(values `dev|stage|prod`), `PlatformTaxonomy`,
`ComplianceTaxonomy`.

### Events Emitted

Tag assign/remove are high-volume and do not themselves emit bus events in
Phase 1 to avoid backpressure against `0-message-bus`. The feature instead
emits counters. If downstream features require eventing, they can
subscribe to the owner entity's events and join on the tag table.

### Events Consumed

- `entity.project.deleted` — purge all
  `(entity_kind='project', entity_id=X)` assignments.
- `entity.resource.deregistered`, `entity.pod.deregistered`,
  `entity.run.completed|failed|cancelled` — optional TTL-based cleanup.

## Component Breakdown

```
source/site/ccai/pychestrate/webservice/model/tagging/
    __init__.py
    entities.py         # TagAssignment, Taxonomy dataclasses + ORM
    repository.py       # DB access, search_by_expression SQL compiler
    service.py          # assign_tag/remove_tag/list_tags/search_entities
    canonical.py        # canonicalize_tag
    registry.py         # TaxonomyRegistry loaded from TagTaxonomyExtension
    extensions.py       # TagTaxonomyExtension base
    expression.py       # Parser + SQL compiler for boolean tag expressions
    errors.py
source/site/ccai/pychestrate/webservice/restapi/versions/v1/tags.py
```

## Key Flows

**Assign tag**
1. REST resource calls `canonicalize_tag(raw=..., registry=registry)`.
2. Registry looks up taxonomy; runs `validate_value`.
3. `repository.upsert_assignment` executes `INSERT ... ON CONFLICT
   DO NOTHING` and returns whether a row was inserted.
4. Service increments counters; logs `tag.assigned`.

**Search entities**
1. Expression parser (hand-rolled recursive descent) produces an AST.
2. `expression.to_sql` walks the AST, emitting `EXISTS` clauses per
   term and filtering terms referencing taxonomies the caller cannot
   read down to `FALSE`.
3. `repository` executes the compiled query and returns ids + count.

## Error Handling

- `TagValidationError`, `UnknownTaxonomyError`, `EntityKindError` →
  REST `400`/`422`.
- `TagExpressionParseError` → REST `400` with the parse-error
  location in the multiline error body.
- `ConfigurationError` raised at startup on taxonomy name collision
  with equal `PRECEDENCE`.
- `SemanticError` never caught.
- Idempotent-assignment fast path: duplicate inserts return the
  existing row without bubbling a constraint-violation error.

## Security Considerations

- Writes delegate to the owning entity's permission check:
  `project.tag.write`, `resource.tag.write`, `pod.tag.write`,
  `job.tag.write`, `artifact.tag.write`.
- Taxonomy visibility: any taxonomy whose `description` begins with
  `[internal]` is hidden from non-admin listings.
- Search-expression filter-to-empty for unreadable taxonomies prevents
  existence leaks.
- Rate limit: 200 assign/min/session; 300 search/min/session.

## Observability

- Counters: `pychestrate_tag_assigned_total{taxonomy,entity_kind}`,
  `pychestrate_tag_removed_total{taxonomy,entity_kind}`,
  `pychestrate_tag_search_total{result_count_bucket}`,
  `pychestrate_tag_validator_reject_total{taxonomy}`.
- Histogram: `pychestrate_tag_search_duration_seconds{kind}`.
- Structured logs: `tag.assigned`, `tag.removed`,
  `tag.validator_rejected`, `tag.search`.
- Trace spans: `tag.assign`, `tag.remove`, `tag.search`,
  `tag.canonicalize`.

## Open Questions

- Phase-1 blocker: should the expression parser support `IN` set
  syntax (`environment IN (dev, stage)`) or only equality? Decision:
  equality only in Phase 1 — defer until search UX review.
- Should taxonomies be per-project or global? Decision: global in
  Phase 1 to keep semantics simple; revisit in Phase 10 if multi-tenant
  isolation is needed.
