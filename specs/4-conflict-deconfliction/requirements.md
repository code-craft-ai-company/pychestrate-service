# 4-conflict-deconfliction — Requirements

## Introduction

The `4-conflict-deconfliction` feature encodes the rules that decide whether
two reservations may coexist against the same or overlapping resources.
Exclusive-vs-shared mode is the most common example, but not the only one:
two jobs cannot simultaneously hold subnets whose CIDRs overlap; two jobs
cannot both hold a license seat when the license has `seat_count=1`;
certain device pairs cannot be held simultaneously because they share a
physical cable the site catalog flags as mutually exclusive; some kinds
have site-specific compatibility constraints (firmware level, driver
version) that only the site knows. Rules are expressed as
`ConflictRuleExtension` subclasses — the resource surface that Layer 4
exposes for compatibility. The feature is invoked by
`4-checkout-checkin.reserve` between the `CheckoutValidatorExtension`
pipeline and the DB commit, so a rule violation rejects the reservation
with `409` rather than letting the conflict land.
Pod reservations hold the whole pod as a single lock unit; deconfliction
rules across pods (e.g. two pods sharing a power circuit) are still
evaluated here. Ships in Phase 4.

## Requirements

### Requirement 1: Evaluate Rules Before Granting a Reservation

**User Story:** As the checkout service, I want a single
`evaluate(request, candidate)` entry point that runs every loaded
`ConflictRuleExtension`, so that I don't have to know about individual
rules.

**Acceptance Criteria (EARS):**

1. WHEN `conflict.evaluate(request, candidate)` is called THEN the system
   SHALL invoke `ConflictRuleExtension.check(...)` on every rule whose
   `applies_to_kinds` contains `candidate.kind` OR contains `"*"`.
2. IF any rule returns `RuleDecision.violated(reason)` THEN the system
   SHALL stop evaluation and return a `ConflictViolation` naming the rule
   and reason; the caller (checkout) raises `ReservationConflictError`.
3. WHERE multiple rules pass THEN the system SHALL return
   `RuleDecision.compatible()` and the caller proceeds.
4. WHEN the rule set changes via `extension.reloaded` THEN the in-process
   rule registry SHALL rebuild before the next evaluate call.

### Requirement 2: Exclusive vs Shared Mode Is Enforced

**User Story:** As an operator, I want `mode=exclusive` to mean "no other
holder" and `mode=shared` to mean "multiple shared holders may coexist",
so that my test jobs and monitoring jobs can share a device while
stress tests hold it exclusively.

**Acceptance Criteria (EARS):**

1. IF an incoming `mode=exclusive` request targets a resource that is
   currently held in any state THEN the system SHALL return
   `RuleDecision.violated("resource already held")`.
2. IF an incoming `mode=shared` request targets a resource that is
   currently held in `mode=exclusive` THEN the system SHALL return
   `RuleDecision.violated("exclusive holder present")`.
3. IF an incoming `mode=shared` request targets a resource held only by
   other `shared` holders AND no other rule objects THEN the system
   SHALL return `RuleDecision.compatible()`.
4. WHERE a kind declares `supports_shared: false` THEN the system SHALL
   treat every reservation against that kind as `mode=exclusive`
   regardless of the caller's request and record a log event
   `pychestrate.resource.conflict.shared_downgraded`.

### Requirement 3: Subnet Overlap Rule

**User Story:** As a network admin, I want two jobs never to hold
subnets whose CIDR ranges overlap, so that my lab's routing doesn't blow
up mid-run.

**Acceptance Criteria (EARS):**

1. WHEN evaluating a reservation for a resource of kind
   `ip_subnet` THEN the system SHALL compute the network intersection of
   the candidate and every currently-granted `ip_subnet` reservation in
   the same project (plus any cross-project subnets marked
   `globally_scoped: true`).
2. IF the intersection is non-empty THEN the system SHALL return
   `RuleDecision.violated(...)` naming the overlapping `reservation_id`
   and the overlapping CIDR block.
3. WHERE the candidate is an `ip_address` AND its address falls inside
   a subnet currently held by a different owner THEN the system SHALL
   treat this as a violation (unless the subnet reservation is held by
   the same owner, in which case the address is a sub-reservation and
   is allowed).

### Requirement 4: Site-Specific Compatibility Rules

**User Story:** As a site operator, I want to add site-specific
compatibility rules (e.g. "these two switches share a power supply and
cannot be held concurrently") without forking the service, so that I
can model my lab reality.

**Acceptance Criteria (EARS):**

1. WHEN a `ConflictRuleExtension` declares `rule_name="power_circuit"` and
   `applies_to_kinds=("device",)` THEN the system SHALL include it in the
   evaluation pipeline for every device checkout.
2. IF the rule raises any exception THEN the system SHALL log
   `pychestrate.resource.conflict.rule_error` and treat the rule as
   *violated* with reason `internal rule error` — a crashing rule fails
   closed, never opens access.
3. WHERE a rule declares `requires_db_view: true` THEN the system SHALL
   pass an isolated, read-only repository handle into
   `ConflictRuleExtension.check` so the rule can query sibling
   reservations without holding its own transaction.

## Property-Based Test Requirements

### Property 1: Exclusive-Never-Coexists

- **Invariant:** For any pair of overlapping reservations on the same
  `resource_id` where at least one has `mode=exclusive`, exactly one of
  the two transitions to `state=granted` (the other is rejected with
  `ReservationConflictError` or queued).
- **Generator:** Hypothesis strategy producing random pairs of
  `(mode, owner, request_ts)` against a single resource, fanned out
  across 2–16 threads.
- **Assertion:** For every pair of granted windows on the same resource,
  if either was exclusive, the windows are disjoint in time.
- **Sample size:** 1000 generated cases.

### Property 2: Subnet Overlap Rule Is Symmetric and Transitive-Safe

- **Invariant:** For any set of subnet reservations R, if the rule would
  reject adding `R_new` because of overlap with `R_i`, then swapping the
  arrival order (trying `R_new` first, then `R_i`) MUST reject the
  second arrival with a matching overlap reason. Additionally: no three
  subnets can all be mutually granted if any pair overlaps.
- **Generator:** Hypothesis strategy producing random IPv4 and IPv6
  networks across bit-lengths `[8, 32]` and `[16, 64]` respectively,
  with duplicates, containments, and edge-adjacent networks.
- **Assertion:** Rule results are symmetric under arrival-order swap;
  mutual grant only occurs over pairwise-disjoint sets.
- **Sample size:** 1000 generated cases.

## Non-Functional Requirements

- **NFR-1 (Performance):** `conflict.evaluate` p99 < 5 ms on a set of
  100 active reservations and 20 rules. Subnet-overlap rule p99 < 3 ms
  on 500 active subnet reservations (uses a GiST range index). Rule
  registry lookup is O(1) per kind.
- **NFR-2 (Security):** Rule extensions receive a sandboxed read-only
  repository; they MUST NOT be able to mutate state. Any attempt to
  write through the handle SHALL raise `SemanticError` which bubbles
  per AGENTS.md. Rule `rule_name` values are unique; collision on
  extension load SHALL raise `ConfigurationError` and block startup.
- **NFR-3 (Observability):** Emit metrics
  `pychestrate_resource_conflict_evaluated_total{kind,outcome}`,
  `pychestrate_resource_conflict_rule_evaluated_total{rule_name,outcome}`,
  `pychestrate_resource_conflict_evaluation_duration_seconds{kind}`
  (histogram),
  `pychestrate_resource_conflict_rule_error_total{rule_name}`. Log
  events `pychestrate.resource.conflict.violated`,
  `pychestrate.resource.conflict.rule_error`,
  `pychestrate.resource.conflict.shared_downgraded`. Trace span
  `pychestrate.resource.conflict.evaluate` with attributes
  `rules_run`, `violator_rule`, `candidate_kind`.
- **NFR-4 (Reliability):** A crashing rule fails *closed* (treated as
  violated), never *open*. An empty rule registry is treated as a
  `ConfigurationError` at startup — the system never runs with
  zero-rules because that would silently disable exclusivity.

## Out of Scope

- Reservation persistence and mode-flag storage (see
  `4-checkout-checkin`).
- Pool membership computation (see `4-resource-pools`).
- Deciding which queued waiter gets the freed slot (see
  `4-reservation-scheduler`).
- Resource health and quarantine — quarantined resources are rejected
  upstream; deconfliction assumes candidates are live.

## Dependencies

- **Depends on:** `4-resource-inventory`, `0-persistence`,
  `E-resource-extensions`.
- **Depended on by:** `4-checkout-checkin`, `4-reservation-scheduler`
  (consults on queued-grant re-evaluation).
- **Extension points exposed:** `resource: ConflictRuleExtension` —
  declares `rule_name`, `applies_to_kinds`, `priority`,
  `requires_db_view`, and `check(request, candidate, db) -> RuleDecision`.
  In-tree: `ExclusiveModeRule`, `SharedModeRule`, `SubnetOverlapRule`,
  `LicenseSeatCountRule`, `PodMemberCrossLockRule`.
