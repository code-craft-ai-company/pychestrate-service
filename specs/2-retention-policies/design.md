# 2-retention-policies — Design

## Architecture

`2-retention-policies` lives in Layer 2 and is owned by
`ccai.pychestrate.webservice.retention`. It contains three pieces: a
policy model (persisted in `0-persistence`), an evaluator that selects
matching rows per data class, and a dispatcher that invokes the
registered `retention_action` factory chain. A scheduler loop — backed by
an advisory-lock-based leader election — runs published policies on
their configured intervals. Artifact-class policies cooperate with
`0-object-store` tier APIs for cold / cold-archive tier transitions.
Ships in **Phase 10 — Public Surface & Extensibility Completion**.

## Data Model

```python
class PolicyState(str, enum.Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    PAUSED = "paused"
    ARCHIVED = "archived"

class TerminalAction(str, enum.Enum):
    TIER_MOVE = "tier_move"           # non-terminal
    ARCHIVE = "archive"                # non-terminal
    DELETE = "delete"                  # terminal
    PERMANENT_ARCHIVE = "permanent_archive"  # terminal

@dataclass
class SelectorClause:
    tag_expression: str | None      # forwarded to 2-tagging
    age_days: int | None            # match when entity_age >= age_days
    size_bytes_over: int | None
    project_ids: list[UUID] | None  # None == any (scope-permitting)

@dataclass
class ActionStep:
    action_name: str                # looked up in retention_action registry
    parameters: dict[str, Any]
    wait_days_after_previous: int = 0

@dataclass
class RetentionPolicy:
    policy_id: UUID
    name: str                       # unique within scope
    data_class: str                 # run_result|artifact|log_stream|audit_record|metric_sample|<ext>
    scope_level: Literal["system", "project"]
    scope_id: UUID | None
    selector: SelectorClause
    action_chain: list[ActionStep]
    interval_minutes: int
    batch_size: int
    max_attempts: int
    state: PolicyState
    created_by_user_id: UUID
    created_at: datetime
    last_run_at: datetime | None

@dataclass
class RetentionRunRecord:
    run_id: UUID
    policy_id: UUID
    started_at: datetime
    finished_at: datetime | None
    matched_count: int
    actioned_count: int
    skipped_count: int
    failed_count: int
    error_summary: str | None

@dataclass
class RetentionActionResult:
    entity_id: UUID
    action_name: str
    outcome: Literal["applied", "skipped", "failed"]
    reason: str                      # e.g., tier_already_matching, legal_hold
    terminal: bool                   # True ends the chain for this entity
```

Indexes: `UNIQUE (scope_level, scope_id, name)`;
`(state, last_run_at)`; `(data_class, state)`.

## Interfaces

### Public API

- `POST /api/v1/retention/policies` — create (state=`DRAFT`).
- `GET /api/v1/retention/policies` — list filtered by scope + state.
- `PATCH /api/v1/retention/policies/{id}` — edit while `DRAFT`
  or `PAUSED`.
- `POST /api/v1/retention/policies/{id}/publish` — publish.
- `POST /api/v1/retention/policies/{id}/pause` — pause.
- `POST /api/v1/retention/policies/{id}/dry-run` — returns ids +
  per-step simulated outcome; no side effects.
- `GET /api/v1/retention/policies/{id}/runs` — history of
  `RetentionRunRecord`.
- `GET /api/v1/retention/data-classes` — list registered data
  classes (built-in + extension-contributed).
- `GET /api/v1/retention/actions` — list registered
  `retention_action` impls and their param schemas.

### Internal API

```python
# source/site/ccai/pychestrate/webservice/retention/service.py

def create_policy(
    *,
    name: str,
    data_class: str,
    scope_level: Literal["system", "project"],
    scope_id: UUID | None,
    selector: SelectorClause,
    action_chain: list[ActionStep],
    interval_minutes: int,
    batch_size: int,
    max_attempts: int,
    actor_user_id: UUID,
) -> RetentionPolicy:
    ...


def publish_policy(
    *,
    policy_id: UUID,
    actor_user_id: UUID,
) -> RetentionPolicy:
    ...


def dry_run_policy(
    *,
    policy_id: UUID,
    actor_user_id: UUID,
    limit: int = 500,
) -> list[RetentionActionResult]:
    """
        Evaluate the selector and simulate the action chain.

        :param policy_id: Target policy
        :param actor_user_id: Caller
        :param limit: Cap on entities returned

        :returns: Per-entity simulated result list (no side effects)
        :raises: PolicyNotFoundError, SelectorCompileError
    """
    ...


# source/site/ccai/pychestrate/webservice/retention/evaluator.py

def evaluate_policy(
    *,
    policy: RetentionPolicy,
    dry_run: bool = False,
) -> RetentionRunRecord:
    ...


# source/site/ccai/pychestrate/webservice/retention/dispatcher.py

def dispatch_action_chain(
    *,
    entity_kind: str,
    entity_id: UUID,
    chain: list[ActionStep],
    dry_run: bool,
) -> list[RetentionActionResult]:
    ...
```

### Extension Surface

- `factory: retention_action`
  (`source/site/ccai/pychestrate/webservice/retention/factories.py`)

```python
class RetentionActionProtocol(FactoryProtocolBase):
    factory_protocol_name = "retention_action"

    @classmethod
    def apply(
        cls,
        *,
        entity_kind: str,
        entity_id: UUID,
        parameters: dict[str, Any],
        dry_run: bool,
    ) -> RetentionActionResult:
        """Apply or simulate a lifecycle action against an entity."""
        ...

    action_name: ClassVar[str]
    terminal: ClassVar[bool]
```

Reference impls shipped in-tree under
`ccai/factories/pychestrate/retention/`:
- `TierMoveAction` (cooperates with `0-object-store` tier API;
  non-terminal).
- `ArchiveAction` (copies then marks source as cold-archive tier;
  non-terminal).
- `DeleteAction` (terminal; respects `legal_hold`).
- `PermanentArchiveAction` (terminal; object is immutable after).

### Events Emitted

```python
@dataclass
class RetentionAppliedEvent:
    policy_id: UUID
    run_id: UUID
    data_class: str
    matched: int
    actioned: int
    skipped: int
    failed: int
    occurred_at: datetime
```

Topic: `entity.retention.applied`.

### Events Consumed

- `entity.project.deleted` — archive policies scoped to the project,
  preventing action against rows that no longer have an owning
  project.
- `entity.artifact.uploaded` — update last-touch timestamp used by
  `age_days` selectors.

## Component Breakdown

```
source/site/ccai/pychestrate/webservice/retention/
    __init__.py
    entities.py         # RetentionPolicy, SelectorClause, ActionStep,
                        # RetentionRunRecord, RetentionActionResult
    repository.py       # DB access
    service.py          # create/publish/pause/dry_run/list
    evaluator.py        # data-class-specific selector compilers
    dispatcher.py       # action chain dispatch (dry-run & live)
    scheduler.py        # leader-election loop; interval cadence
    factories.py        # RetentionActionProtocol + reference impls
    selectors/          # per data_class selectors (artifact.py,
                        # run_result.py, log_stream.py, audit_record.py,
                        # metric_sample.py)
    errors.py
source/site/ccai/pychestrate/webservice/restapi/versions/v1/retention.py
```

## Key Flows

**Create + publish**
1. REST resource validates body; service persists with `DRAFT`.
2. Publish transitions to `PUBLISHED`, schedules first run at
   `now + interval_minutes`.

**Scheduled evaluation**
1. Scheduler acquires the per-policy advisory lock; one worker per
   policy per run.
2. `evaluator.evaluate_policy` compiles the `SelectorClause` into a
   data-class-specific SQL query, streams matches in batches of
   `batch_size`.
3. For each matched entity, `dispatcher.dispatch_action_chain` walks
   the chain, stopping on a terminal result or a `skipped` step whose
   prerequisite blocks further action (e.g., `legal_hold`).
4. Results aggregated into `RetentionRunRecord`; event published.

**Artifact tier cooperation**
1. `TierMoveAction` calls the `0-object-store` tier API with the
   object id and target tier.
2. Object-store driver executes the tier transition (cloud-native or
   local-copy-and-mark).
3. Action result records `applied` with `new_tier` in `parameters`.

## Error Handling

- `PolicyNotFoundError`, `SelectorCompileError`,
  `UnknownDataClassError`, `UnknownActionError` → REST
  `404`/`400`/`422`.
- Recoverable action errors (`IOError`, `TimeoutError`, cloud
  tier-transition transient errors) are reclassified to
  `RetentionActionRetryableError` with context, counter incremented,
  entity marked `retry` for next run.
- After `max_attempts` retries the entity is marked `failed` with
  the full error chain preserved via `raise ... from err`.
- `SemanticError` is never caught.
- Crash recovery: partial run is detected via `finished_at IS NULL`
  and rerun from scratch. Idempotence is load-bearing — dispatch
  records per-entity terminal status so re-runs skip already-terminal
  rows.

## Security Considerations

- Policy writes gated by `retention.policy.write` (system) and
  `project.retention.policy.write` (project).
- Dry-run gated by `retention.policy.read`.
- Action dispatch uses a service principal; every action is
  audit-logged with policy id, entity id, and outcome.
- `legal_hold` is authoritative: an entity with legal_hold is never
  deleted regardless of policy intent.
- Rate limit: policy writes 20/min/user; dry-run 5/min/user.

## Observability

- Counters: `pychestrate_retention_evaluated_total{policy_id}`,
  `pychestrate_retention_matched_total{policy_id}`,
  `pychestrate_retention_actioned_total{policy_id,action}`,
  `pychestrate_retention_skipped_total{policy_id,reason}`,
  `pychestrate_retention_failed_total{policy_id,action}`.
- Histogram: `pychestrate_retention_policy_duration_seconds{data_class}`.
- Structured logs: `retention.policy.published`,
  `retention.policy.evaluated`, `retention.action.applied`,
  `retention.action.skipped`, `retention.action.failed`.
- Trace spans: `retention.evaluate`, `retention.compile_selector`,
  `retention.dispatch_action`.

## Open Questions

- Phase-10 blocker: should the scheduler use Postgres advisory locks or
  a dedicated external lease (Redis)? Decision: advisory locks in the
  first release; revisit if multi-region active-active becomes a
  requirement.
- How should `tier_move` to cold-archive interact with in-flight reads?
  Decision: the action must acquire a short exclusive lock on the
  object row before calling the driver; design review required in
  Phase 10.
