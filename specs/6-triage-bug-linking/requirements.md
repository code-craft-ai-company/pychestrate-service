# 6-triage-bug-linking — Requirements

## Introduction

The `6-triage-bug-linking` feature classifies each failure observed in a
completed run into one of `known_issue`, `new_bug`, `infra_flake`, or
`other`, and links it to an external tracker (Jira, Linear, GitHub
Issues, custom) through the `bug_tracker_driver` factory protocol. It
draws signals from `6-flake-tracking` (is this a known flake?),
`6-compare-runs` (is the failure new vs the baseline?), and
`5-result-ingest-watcher` (stack traces and diagnostics). Ships in
**Phase 5** with the other test-orchestration polish features. Sits
between `6-test-orchestration` (result producer) and
`2-notification-hub` (alert routing). Authoritative source of truth for
triage state is the `triage_case` table; external tickets are mirrors
linked via the driver.

## Requirements

### Requirement 1: Classify Failures Into Buckets

**User Story:** As an on-call engineer, I want the service to classify
failures so that I can focus on real regressions instead of flakes or
infra noise.

**Acceptance Criteria (EARS):**

1. WHEN `entity.run.completed` is observed AND the run has at least one failure THEN the system SHALL produce a `TriageCase` per failing test case with one of `{known_issue, new_bug, infra_flake, other}` and a `confidence: float in [0.0, 1.0]`.
2. WHEN the failing test is currently `flaky` or `quarantined` per `6-flake-tracking` THEN the system SHALL classify it as `infra_flake` with `rationale = "flake_history"`.
3. WHEN a failure's stack-trace signature matches an open ticket key via the active `bug_tracker_driver` THEN the system SHALL classify as `known_issue` and attach `{tracker: str, ticket_key: str}`.
4. IF neither flake history nor a known-issue match exists THEN the system SHALL classify as `new_bug` AND SHALL emit `entity.triage.new_bug_detected` on the bus.
5. WHERE the triggering run is tagged `infra_health_check` THEN failures SHALL default to `infra_flake` regardless of other signals.

### Requirement 2: Bug Tracker Factory Protocol

**User Story:** As a site operator using Linear, I want to plug in a
Linear driver so that `known_issue` links resolve correctly against our
tracker.

**Acceptance Criteria (EARS):**

1. WHEN the extension host discovers a `BugTrackerDriverProtocol` implementation THEN the system SHALL verify `tracker_name`, `search_open_by_signature`, `open_ticket`, `comment_on_ticket`, `get_ticket` classmethods AND raise `ConfigurationError` naming missing methods.
2. IF two drivers share `tracker_name` and `PRECEDENCE` THEN the system SHALL raise `ConfigurationError` at load time.
3. WHEN a project selects a `tracker_name` via `triage.set_project_tracker(...)` THEN the system SHALL persist the selection AND route all subsequent `open_ticket` / `search_open_by_signature` calls through the chosen driver.
4. WHERE a driver's `search_open_by_signature` raises `TrackerTransientError` THEN the system SHALL honor the `Aspects.retry_policy` before bubbling.

### Requirement 3: Auto-Open Tickets With Audit Trail

**User Story:** As an owner of a new-bug class, I want Pychestrate to
auto-open a ticket with enough context to triage, so that I do not
re-type the failure by hand.

**Acceptance Criteria (EARS):**

1. WHEN classification is `new_bug` AND project config `auto_open_new_bug == True` THEN the system SHALL call `driver.open_ticket(...)` with title, description (stack trace digest, test identity, first occurrence, run URL), and tracker-specific labels derived from `2-tagging`.
2. WHEN an auto-open succeeds THEN the system SHALL persist the `ticket_key` on the `TriageCase` AND emit `entity.triage.ticket_opened`.
3. IF the driver returns a duplicate-ticket error THEN the system SHALL link to the existing ticket AND re-classify the case as `known_issue` WITHOUT raising an exception.
4. WHEN a case is manually re-classified by an actor THEN the system SHALL append to `triage_case_ledger` WITH `{actor_id, from_class, to_class, rationale, at}`.

## Property-Based Test Requirements

### Property 1: Classification Is A Pure Function Of Inputs

- **Invariant:** For any `(stack_signature, flake_state, baseline_state, infra_tags)`, two calls to `classify(...)` produce the same class, the same confidence (within float tolerance 1e-12), and the same rationale string.
- **Generator:** `hypothesis.strategies.tuples(text(min_size=0, max_size=64), sampled_from(FlakeClass), sampled_from(BaselineState), sets(text(), max_size=5))`.
- **Assertion:** `classify(inputs) == classify(copy(inputs))`.
- **Sample size:** 1000 generated cases

### Property 2: Known-Issue Match Is Idempotent Across Re-Classification

- **Invariant:** For any case that matched `ticket_key = K` at time `t`, subsequent classifications in the same run window continue to return the same `ticket_key` unless the ticket is closed at the tracker and the ledger shows the closure.
- **Generator:** `hypothesis.strategies.lists(booleans(), min_size=0, max_size=10)` representing the sequence of classify-cycle invocations.
- **Assertion:** All classifications in a run window yield the same `ticket_key`; when the tracker flips to `closed`, the next classification drops the `ticket_key` and reclassifies as `new_bug`.
- **Sample size:** 1000 generated cases

## Non-Functional Requirements

- **NFR-1 (Performance):** Classification per failing case p99 < 60 ms (excluding tracker network I/O). `search_open_by_signature` cached per-signature 10 min; cache hit p99 < 5 ms. Auto-open throughput >= 10 tickets/min per project, rate-limited to avoid tracker API bans.
- **NFR-2 (Security):** Tracker credentials stored in `1-secrets-vault` under `ext.bug_tracker.<name>.*`; never logged. Auto-open gated by `triage.auto_open` permission on the project; manual re-classify gated by `triage.reclassify`. Comments/tickets never contain variable values that look like secrets (mask `/password|token|secret/i` patterns).
- **NFR-3 (Observability):** Metrics `pychestrate_test_triage_classifications_total{project,class}` (counter), `pychestrate_test_triage_classify_duration_seconds{project}` (histogram), `pychestrate_test_triage_tickets_opened_total{project,tracker}` (counter), `pychestrate_test_triage_tracker_errors_total{project,tracker,error_kind}` (counter). Log events `pychestrate.test.triage.classified`, `pychestrate.test.triage.ticket_opened`, `pychestrate.test.triage.duplicate_merged`, `pychestrate.test.triage.reclassified`. Trace spans `pychestrate.test.triage.classify`, `pychestrate.test.triage.search_open`, `pychestrate.test.triage.open_ticket`.
- **NFR-4 (Reliability):** A tracker outage SHALL NOT block classification: cases are classified as `new_bug` but `ticket_key` is deferred until the tracker recovers. An auto-open scheduled while the tracker is down is queued with bounded backoff and replays without duplicate tickets (idempotency key derived from `(project, stack_signature_sha256)`).

## Out of Scope

- Flake classification (see `6-flake-tracking`).
- Cross-run diff (see `6-compare-runs`).
- Notification routing beyond bug tracker (see `2-notification-hub`).

## Dependencies

- **Depends on:** `6-test-orchestration`, `6-flake-tracking`, `6-compare-runs`, `5-result-ingest-watcher`, `0-persistence`, `0-message-bus`, `1-secrets-vault`, `1-rbac`, `1-audit-log`, `2-tagging`, `E-extension-host`.
- **Depended on by:** `7-test-metrics`, `9-run-detail-ui`.
- **Extension points exposed:** `factory: bug_tracker_driver` — Jira, Linear, GitHub Issues, custom.
