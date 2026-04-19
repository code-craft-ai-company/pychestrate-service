# 4-conflict-deconfliction — Design

## Architecture

Deconfliction is a pure evaluator with no state of its own — rule
decisions depend on the current contents of `core.reservations` and
`core.resources` plus the caller-supplied `CheckoutRequest` and the
chosen `Resource` candidate. It exposes a single `evaluate(request,
candidate)` entry point consumed by `4-checkout-checkin` between the
validator pipeline and the DB commit. Rules are `ConflictRuleExtension`
subclasses discovered by the extension host; the evaluator sorts them by
their declared `priority` (lower first) and short-circuits on first
violation. A crashing rule is treated as a violation, never as an
implicit allow. The evaluator runs inside the same DB transaction as
checkout so rule queries see a consistent snapshot; rule extensions
receive a *read-only* repository handle that rejects mutations. The
subnet-overlap rule relies on PostgreSQL's `cidr` type and a GiST index
on `inet_ops` for O(log n) overlap queries. Ships in Phase 4.

## Data Model

No owned tables. Schema additions in `4-resource-inventory` needed here:

- `core.resources.attrs->>'cidr'` projected as a column for subnet kinds
  via generated column `network cidr GENERATED ALWAYS AS
  ((attrs->>'cidr')::cidr) STORED WHERE kind='ip_subnet'`.
- GiST index `idx_resources_subnet_gist` on
  `(network inet_ops) WHERE kind='ip_subnet' AND state='available'`.
- Similar generated column `address inet` for `ip_address` kind.

A secondary view `core.active_reservations_with_network` joins
`core.reservations` (granted only) with the generated network columns to
let the overlap rule run a single indexed query.

## Interfaces

### Public API

N/A — internal feature.

### Internal API

```python
def evaluate(
    request: CheckoutRequest,
    candidate: Resource,
    db: ReadOnlyRepositoryHandle
) -> ConflictEvaluation:
    """
        Run every applicable rule for the candidate resource.

        :param request: The full checkout request.
        :param candidate: The pool-selected resource.
        :param db: A read-only repository handle for rule queries.

        :returns: A ConflictEvaluation naming violating rule or compatible.
    """
    ...


def rebuild_rule_registry() -> None:
    """
        Re-scan the extension host for ConflictRuleExtension subclasses;
        rebuild the per-kind routing table. Raises on duplicate rule_name.

        :raises: ConfigurationError
    """
    ...


def active_reservations_for_kind(
    kind: str,
    project_id: UUID,
    db: ReadOnlyRepositoryHandle
) -> list[ActiveReservationSnapshot]:
    """
        Return the active reservations a rule may need to inspect.

        :param kind: The resource kind.
        :param project_id: The caller's project; cross-project entries
                           are included only when globally_scoped=True.
        :param db: The read-only handle.

        :returns: Snapshot rows; rule must not mutate them.
    """
    ...
```

### Extension Surface

Resource extension:

```python
class ConflictRuleExtension(ResourceExtension):
    """
        Site-level compatibility rule.

        Subclasses declare:
          - rule_name: str — globally unique
          - applies_to_kinds: tuple[str, ...] — or ("*",) for all
          - priority: int — lower runs first (0..1000)
          - requires_db_view: bool
    """
    rule_name: str
    applies_to_kinds: tuple
    priority: int
    requires_db_view: bool

    @classmethod
    def check(
        cls,
        request: CheckoutRequest,
        candidate: Resource,
        db: ReadOnlyRepositoryHandle | None
    ) -> RuleDecision:
        """
            Return RuleDecision.compatible() or .violated(reason=..).

            :param request: The checkout request.
            :param candidate: The chosen candidate resource.
            :param db: Read-only repository handle, or None when the rule
                       declared requires_db_view=False.

            :returns: The rule decision.
        """
        ...
```

In-tree implementations under
`source/site/automojo/extensions/pychestrate/resources/conflict_rules/`:

- `ExclusiveModeRule` — priority 10, `applies_to_kinds=("*",)`,
  `requires_db_view=True`. Enforces Requirement 2.1 and 2.2.
- `SharedModeRule` — priority 20, `applies_to_kinds=("*",)`. Handles
  `supports_shared=false` downgrade per 2.4.
- `SubnetOverlapRule` — priority 30,
  `applies_to_kinds=("ip_subnet","ip_address")`, `requires_db_view=True`.
- `LicenseSeatCountRule` — priority 30,
  `applies_to_kinds=("license",)`, `requires_db_view=True`.
- `PodMemberCrossLockRule` — priority 40,
  `applies_to_kinds=("*",)`, `requires_db_view=True`. Re-asserts that a
  `pod_locked_by` resource may not be independently reserved.

Test-only `AlwaysViolateRule` at priority 0 for extension-point coverage.

### Events Emitted

- `pychestrate.resource.conflict.violated` — `{rule_name, candidate_id,
  reason, request_id}`
- `pychestrate.resource.conflict.rule_error` — `{rule_name, candidate_id,
  error}`
- `pychestrate.resource.conflict.shared_downgraded` — `{candidate_id,
  kind}`

### Events Consumed

- `extension.reloaded` — rebuild rule registry.

## Component Breakdown

Under `source/site/automojo/pychestrate/webservice/resources/conflict/`:

- `models.py` — `RuleDecision`, `ConflictEvaluation`,
  `ActiveReservationSnapshot`, `ReadOnlyRepositoryHandle`.
- `rule_registry.py` — in-process registry keyed by kind; rebuilds on
  extension reload.
- `evaluator.py` — the `evaluate` entry point; short-circuits on first
  violation; catches-and-reclassifies rule exceptions as violations.
- `repository_views.py` — `ReadOnlyRepositoryHandle` implementation
  wrapping `0-persistence` with every write method raising
  `SemanticError`.
- `errors.py` — `ConfigurationError` on duplicate `rule_name`.

Rule implementations at
`source/site/automojo/extensions/pychestrate/resources/conflict_rules/`.

## Key Flows

### Flow 1 — Evaluate an exclusive checkout

1. `4-checkout-checkin` calls
   `evaluate(request, candidate, db=read_only_handle)`.
2. Evaluator looks up rules for `candidate.kind` plus wildcard rules.
3. Rules are sorted ascending by `priority`.
4. First rule runs: `ExclusiveModeRule.check(...)` queries
   `core.reservations` for any granted row against `candidate.resource_id`.
   Holder present → returns `RuleDecision.violated("resource already
   held")`.
5. Evaluator emits `pychestrate.resource.conflict.violated` and returns
   `ConflictEvaluation(violated=True, rule_name=..., reason=...)`.
6. Checkout raises `ReservationConflictError` → `409`.

### Flow 2 — Subnet overlap check

1. Incoming candidate kind `ip_subnet` with CIDR `10.1.0.0/20`.
2. `SubnetOverlapRule.check` runs:
   `SELECT reservation_id, network FROM
   core.active_reservations_with_network WHERE kind='ip_subnet' AND
   (project_id = :p OR globally_scoped) AND network && :candidate_cidr`
   (`&&` is PostgreSQL's overlap operator; hits the GiST index).
3. Any row → violated with `reason="overlaps with reservation X on
   10.1.8.0/22"`.

### Flow 3 — Crashing rule fails closed

1. A buggy rule raises inside `check`.
2. Evaluator catches the exception at *exactly one* boundary; emits
   `pychestrate.resource.conflict.rule_error` and returns
   `RuleDecision.violated("internal rule error: <rule_name>")`.
3. `pychestrate_resource_conflict_rule_error_total{rule_name}` is
   incremented; operator sees the alerting gauge in `7-resource-metrics`.

## Error Handling

- `ConfigurationError` at startup on duplicate `rule_name` — service
  refuses to start.
- `SemanticError` raised by `ReadOnlyRepositoryHandle` on any write
  attempt — bubbles per AGENTS.md.
- Rule exceptions: caught-and-reclassified once at the evaluator boundary
  to `RuleDecision.violated(...)`; never swallowed silently.
- Any DB error during rule evaluation bubbles as
  `DatabaseUnavailableError` → checkout returns `503` (distinct from a
  rule violation, which is `409`).
- Multiline errors via `os.linesep.join([...])`:

```python
err_msg_lines = ["Duplicate conflict rule name at startup."]
err_msg_lines.append("RULE_NAME: {}".format(rule_name))
err_msg_lines.append("TYPE A: {}".format(existing_type.__module__))
err_msg_lines.append("TYPE B: {}".format(new_type.__module__))

err_msg = os.linesep.join(err_msg_lines)
raise ConfigurationError(err_msg) from None
```

## Security Considerations

- Rule extensions receive only a `ReadOnlyRepositoryHandle`; attempting
  any write raises `SemanticError`.
- Rule execution is bounded by a per-rule soft timeout of 200 ms; a rule
  that exceeds the budget is treated as a violation and recorded.
- Rules have no direct network access unless their
  `E-extension-sandbox` capability grants `net:outbound`; the in-tree
  rules need no external calls.
- Startup refuses to run with an empty rule set (no
  `ExclusiveModeRule`) — this would silently open concurrent exclusive
  holds and is flagged as `ConfigurationError`.

## Observability

Metrics:

- `pychestrate_resource_conflict_evaluated_total{kind,outcome}` — counter
- `pychestrate_resource_conflict_rule_evaluated_total{rule_name,outcome}` — counter
- `pychestrate_resource_conflict_evaluation_duration_seconds{kind}` — histogram
- `pychestrate_resource_conflict_rule_error_total{rule_name}` — counter
- `pychestrate_resource_conflict_rule_timeout_total{rule_name}` — counter

Log events:

- `pychestrate.resource.conflict.violated`
- `pychestrate.resource.conflict.rule_error`
- `pychestrate.resource.conflict.shared_downgraded`
- `pychestrate.resource.conflict.rule_timeout`

Trace spans:

- `pychestrate.resource.conflict.evaluate` — `rules_run`, `violator_rule`,
  `candidate_kind`, `duration_ms`.
- `pychestrate.resource.conflict.rule` — one child per rule; attributes
  `rule_name`, `outcome`.

Dashboards: "Conflict Rules" panel on `7-resource-metrics` — violations
per rule, rule error rate, p95 evaluation time.

## Open Questions

- Should the GiST index cover `cidr` on *all* resources or only
  `ip_subnet`? Current plan: subnet only; revisit if `ip_address` queries
  hit the index slowly.
- Do we want to support "rule groups" that short-circuit at the group
  level (e.g. all network rules, all device-topology rules)? Defer to
  Phase 5.
- Rule timeout: 200 ms may be too tight for rules that query external
  topology services. `ConflictRuleExtension` may need an async variant —
  timebox before Phase 4 exit.
