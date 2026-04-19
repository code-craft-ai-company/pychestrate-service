# 6-blast-radius-guards — Design

## Architecture

`6-blast-radius-guards` is a pure decision engine over a registry of
rules. The engine is invoked by `6-infra-orchestration` on every
destructive action (apply, destroy) and by any caller that explicitly
wants a pre-check via `guards.explain(...)`. Rules are
`GuardRuleExtension` subclasses discovered by the extension host; each
declares its applicability and an `evaluate(ctx)` function that
produces a `GuardVerdict`. The engine never mutates infra state; it
only reads environment attributes, rbac context, and project settings.
Two-person review is modeled as a distinct ledger with approve/reject
entries. Ships in Phase 7.

## Data Model

Tables in `0-persistence`:

- `guard_attachment`:
  - `(project_id, environment_id, rule_id) PK`
  - `enabled: bool`
  - `added_by: UUID`
  - `added_at: datetime`
- `guard_review_request`:
  - `request_id: UUID` PK
  - `project_id, environment_id`
  - `action: InfraAction`
  - `requester_id: UUID`
  - `rule_ids: list[str]`
  - `created_at, expires_at`
  - `state: ReviewState` — `{pending, approved, rejected, expired}`
- `guard_review_entry`:
  - `(request_id, reviewer_id) PK`
  - `decision: "approve" | "reject"`
  - `rationale: str`
  - `reviewed_at: datetime`

Indices: `(project_id, state)` on `guard_review_request`; `(environment_id, enabled)` on `guard_attachment`.

Value types:

- `GuardContext` — `{project_id, environment_id, env_attrs, actor_role_set, action, requester_id, clock}`.
- `GuardVerdict` — `Allow | Deny(reason) | DenyPendingReview(reason)`.
- `GuardTrace` — list of `{rule_id, verdict, reason}`.

## Interfaces

### Public API

REST under `8-rest-api-v1`:

- `GET /api/v1/projects/{project_id}/guards/rules` → known rules.
- `PUT /api/v1/projects/{project_id}/environments/{env_id}/guards/{rule_id}` body `{enabled}`.
- `POST /api/v1/projects/{project_id}/guards/reviews` body `{request_id, decision, rationale}`.
- `GET /api/v1/projects/{project_id}/guards/reviews?state=&limit=&cursor=`.
- `POST /api/v1/projects/{project_id}/guards:explain` body `{environment_id, action, actor_role_set?}` (admin only).

### Internal API

```python
class BlastRadiusGuards:
    def __init__(
        self,
        repo: GuardRepository,
        env_registry: EnvironmentRegistry,
        rule_registry: GuardRuleRegistry,
        rbac: RbacService,
        audit: AuditLog,
        bus: MessageBus,
        clock: Clock,
        config: GuardsConfig
    ) -> None:
        self._repo = repo
        self._env_registry = env_registry
        self._rule_registry = rule_registry
        self._rbac = rbac
        self._audit = audit
        self._bus = bus
        self._clock = clock
        self._config = config
        return

    def allow(
        self,
        project_id: UUID,
        actor_role_set: list[str],
        environment_id: UUID,
        action: InfraAction,
        request_id: UUID | None = None
    ) -> GuardDecision:
        """
            Evaluate guards and return an allow/deny/pending-review decision.

            :returns: GuardDecision.
            :raises: None (engine is fail-closed on internal errors).
        """
        ...

    def explain(
        self,
        actor_id: UUID,
        project_id: UUID,
        environment_id: UUID,
        action: InfraAction,
        actor_role_set: list[str] | None
    ) -> GuardTrace:
        """
            Explain which rules fire for a candidate action.

            :returns: Ordered GuardTrace.
            :raises: AuthorizationError
        """
        ...

    def attach_review(
        self,
        actor_id: UUID,
        reviewer_id: UUID,
        project_id: UUID,
        request_id: UUID,
        decision: str,
        rationale: str
    ) -> ReviewRequestView:
        """
            Record an approve/reject review entry.

            :returns: Updated ReviewRequestView.
            :raises: AuthorizationError, SemanticError, ReviewExpiredError
        """
        ...

    def open_review_request(
        self,
        project_id: UUID,
        environment_id: UUID,
        action: InfraAction,
        requester_id: UUID,
        rule_ids: list[str]
    ) -> UUID:
        """
            Called by the engine when a rule requires a second review.

            :returns: request_id.
            :raises: None.
        """
        ...

    def set_attachment(
        self,
        actor_id: UUID,
        project_id: UUID,
        environment_id: UUID,
        rule_id: str,
        enabled: bool
    ) -> None:
        """
            Enable or disable a rule for an environment.

            :raises: AuthorizationError, SemanticError
        """
        ...
```

### Extension Surface

Resource extension declared here:

```python
class GuardRuleExtension(ResourceExtension):
    """
        Base class for guard rules.
    """
    rule_id: str
    description: str
    global_default: bool = False
    requires_two_person_review: bool = False
    required_reviewer_role: str | None = None

    @classmethod
    def applies_to(
        cls,
        env_attrs: dict[str, object],
        action: InfraAction
    ) -> bool:
        ...

    @classmethod
    def evaluate(
        cls,
        ctx: GuardContext
    ) -> GuardVerdict:
        ...
```

Reference rules shipped in-tree under
`source/site/automojo/extensions/pychestrate/guard_rule/`:

- `ProdDestroyRequiresTwoPersonRule` — `rule_id = "core.prod_destroy_requires_two_person"`, applies to `action == destroy` and env with tag `environment_class=prod`.
- `FrozenEnvBlockRule` — `rule_id = "core.frozen_env_block"`, applies to all apply/destroy when env is `frozen`.
- `ApplyRequiresInfraOperatorRoleRule` — `rule_id = "core.apply_requires_infra_operator_role"`; denies if `actor_role_set` lacks `infra-operator`.
- `OnCallWindowRule` — `rule_id = "core.oncall_window_only"`; applies to apply/destroy outside declared on-call windows.

### Events Emitted

- `entity.infra.guards.evaluated` — `{project_id, environment_id, action, decision, rule_id?}`
- `entity.infra.guards.review_requested` — `{request_id, rule_ids, requester_id}`
- `entity.infra.guards.review_recorded` — `{request_id, reviewer_id, decision}`
- `entity.infra.guards.review_expired` — `{request_id}`

### Events Consumed

- `entity.env.frozen|unfrozen|archived` — invalidate decision cache for the env.
- `extension.reloaded` — rebuild rule registry atomically.

## Component Breakdown

All paths rooted at `source/site/automojo/pychestrate/webservice/orchestration/infra/guards/`:

- `__init__.py`
- `engine.py` — `BlastRadiusGuards`.
- `repository.py` — `GuardRepository`.
- `rule_protocol.py` — `GuardRuleExtension`.
- `rule_registry.py` — extension-host accessor.
- `context.py` — `GuardContext` builder (loads env attrs).
- `review_ledger.py` — review-request lifecycle.
- `aspects.py` — `ExplainAspects`.
- `errors.py` — `ReviewExpiredError`.
- `rest/v1_routes.py`.

In-tree rules under `source/site/automojo/extensions/pychestrate/guard_rule/`.

## Key Flows

### Flow 1 — Evaluate allow

1. `InfraOrchestrator` calls `allow(project_id, actor_role_set, env_id, action)`.
2. `context.py` loads env attrs via `EnvironmentRegistry.get(env_id)`.
3. `rule_registry` returns rules attached + enabled for the env.
4. Each applicable rule's `evaluate(ctx)` returns a verdict.
5. If any rule returns `Deny`, engine returns `Deny(rule_id, reason)`.
6. If any returns `DenyPendingReview`, engine `open_review_request(...)` returns `DenyPendingReview(request_id)`.
7. Else `Allow`.
8. `entity.infra.guards.evaluated` emitted.

### Flow 2 — Two-person review

1. Requester sees `DenyPendingReview(request_id)`.
2. Reviewer posts `attach_review` with `approve`/`reject`.
3. Validity window re-checked; reviewer identity check (distinct from requester); RBAC `guards.review:<rule_id>`.
4. If approved and all required approvals recorded, request → `approved`.
5. Next `allow(...)` with `request_id = <id>` returns `Allow`.

### Flow 3 — Explain

1. Admin hits `POST /:explain`.
2. Engine runs the evaluation WITHOUT caching and returns the full `GuardTrace`.
3. Used by admin UI to debug why an action will deny.

## Error Handling

- `AuthorizationError`: 403 for admin actions.
- `SemanticError`: invalid rule_id, invalid decision value → bubble.
- `ReviewExpiredError`: 410.
- Rule exceptions caught inside `evaluate(...)` boundary, reclassified as `Deny(rule_id, "rule_error")` with multiline log.
- Registry rebuild exceptions: engine returns all `Deny("engine_unavailable")` — fail-closed.
- Multiline errors via `os.linesep.join([...])`.

## Security Considerations

- Decisions are pure — never surface secrets in `reason` strings; rules must describe policy, not secret state.
- `actor_role_set_digest` compared against the role set captured at trigger time to prevent mid-flight role escalation.
- Review entries audited; reviews by actors lacking `guards.review:<rule_id>` rejected.
- Rate-limit `explain` to `max_explains_per_minute_per_project` (default 60) to prevent rule-map enumeration.

## Observability

Metrics:

- `pychestrate_infra_guards_evaluations_total{project,env,action,decision}` — counter
- `pychestrate_infra_guards_denies_total{project,rule_id}` — counter
- `pychestrate_infra_guards_review_requests_total{project,rule_id,outcome}` — counter
- `pychestrate_infra_guards_rule_errors_total{project,rule_id}` — counter
- `pychestrate_infra_guards_review_expiries_total{project,rule_id}` — counter

Log events: `pychestrate.infra.guard.decided`, `pychestrate.infra.guard.review_requested`, `pychestrate.infra.guard.review_recorded`, `pychestrate.infra.guard.review_expired`, `pychestrate.infra.guard.rule_error`, `pychestrate.infra.guard.engine_unavailable`.

Trace spans: `pychestrate.infra.guard.allow`, `pychestrate.infra.guard.explain`, `pychestrate.infra.guard.attach_review`, `pychestrate.infra.guard.rule_evaluate`.

## Open Questions

- Rule ordering — lexicographic by `rule_id` vs explicit priority? Timebox: Phase 7 midpoint.
- On-call window source of truth — a dedicated resource extension or reuse notification routing calendars? Timebox: Phase 7 exit.
- Rule-pack caching TTL — 0 s (always rebuild) vs 30 s (cheaper)? Timebox: Phase 7 midpoint.
