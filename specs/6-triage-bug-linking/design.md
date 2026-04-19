# 6-triage-bug-linking — Design

## Architecture

`6-triage-bug-linking` is a post-run classification stage that produces
a `TriageCase` per failing test and optionally opens/comments on
external tickets through a registered `bug_tracker_driver`. It
subscribes to `entity.run.completed`, gathers signals from
`6-flake-tracking`, `6-compare-runs`, and testbase diagnostics, and
persists the classification + any ticket link. Ships in Phase 5 beside
the rest of the test-polish features. Authoritative source of truth for
triage state is the `triage_case` + `triage_case_ledger` tables here;
tracker tickets are linked references, not mirrors.

## Data Model

Tables in `0-persistence`:

- `triage_case`:
  - `case_id: UUID` PK
  - `project_id: UUID`
  - `run_id: UUID`
  - `catalog_entry_id: UUID`
  - `test_case_identity_sha256: bytes(32)`
  - `stack_signature_sha256: bytes(32)` — hash of normalized stack trace
  - `classification: TriageClass` — `{known_issue, new_bug, infra_flake, other}`
  - `confidence: float`
  - `rationale: str`
  - `tracker: str | None`
  - `ticket_key: str | None`
  - `created_at: datetime`
  - `updated_at: datetime`
- `triage_case_ledger`:
  - `ledger_id: BIGSERIAL`
  - `case_id: UUID`
  - `actor_id: UUID`
  - `from_class: TriageClass | None`
  - `to_class: TriageClass`
  - `rationale: str`
  - `at: datetime`
- `triage_signature_cache`:
  - `project_id: UUID`
  - `tracker: str`
  - `stack_signature_sha256: bytes(32)`
  - `ticket_key: str`
  - `ticket_status: str`
  - `cached_at: datetime`
  - TTL 10 minutes.
- `triage_project_tracker_config`:
  - `project_id: UUID` PK
  - `tracker: str`
  - `auto_open_new_bug: bool`
  - `updated_by: UUID`
  - `updated_at: datetime`

Indices: `(project_id, classification)`, `(run_id)`, `(stack_signature_sha256)`, unique `(project_id, stack_signature_sha256)` on triage_signature_cache.

Value types:

- `TriageInputs` — `{stack_signature_sha256, flake_state, baseline_state, infra_tags, catalog_entry}`.
- `TriageDecision` — `{classification, confidence, rationale, tracker, ticket_key}`.

## Interfaces

### Public API

REST under `8-rest-api-v1`:

- `GET /api/v1/projects/{id}/triage/cases?run_id=&class=&limit=&cursor=` → paginated.
- `GET /api/v1/projects/{id}/triage/cases/{case_id}` → `TriageCaseView`.
- `POST /api/v1/projects/{id}/triage/cases/{case_id}:reclassify` body `{to_class, rationale}` → updated view.
- `POST /api/v1/projects/{id}/triage/config/tracker` body `{tracker, auto_open_new_bug}` → new config.

### Internal API

```python
class TriageService:
    def __init__(
        self,
        repo: TriageRepository,
        flake_tracker: FlakeTracker,
        compare_service: CompareRunsService,
        tracker_registry: BugTrackerRegistry,
        rbac: RbacService,
        audit: AuditLog,
        bus: MessageBus,
        clock: Clock,
        config: TriageConfig
    ) -> None:
        self._repo = repo
        self._flake_tracker = flake_tracker
        self._compare_service = compare_service
        self._tracker_registry = tracker_registry
        self._rbac = rbac
        self._audit = audit
        self._bus = bus
        self._clock = clock
        self._config = config
        return

    def classify_run(
        self,
        run_id: UUID
    ) -> list[TriageDecision]:
        """
            Classify every failure in a completed run.

            :param run_id: Completed run.

            :returns: Per-failure decisions.
            :raises: RunNotFoundError, ConfigurationError
        """
        ...

    def reclassify(
        self,
        actor_id: UUID,
        case_id: UUID,
        to_class: TriageClass,
        rationale: str
    ) -> TriageDecision:
        """
            Manually re-classify a case; ledgered.

            :returns: New TriageDecision.
            :raises: AuthorizationError, SemanticError
        """
        ...

    def set_project_tracker(
        self,
        actor_id: UUID,
        project_id: UUID,
        tracker: str,
        auto_open_new_bug: bool
    ) -> None:
        """
            Select the bug tracker for a project.

            :returns: None.
            :raises: AuthorizationError, ConfigurationError
        """
        ...
```

### Extension Surface

Factory protocol declared here:

```python
class BugTrackerDriverProtocol(FactoryProtocolBase):
    """
        Contract for bug_tracker_driver implementations.
    """
    factory_protocol_name: str = "bug_tracker_driver"

    @classmethod
    def tracker_name(cls) -> str:
        ...

    @classmethod
    def open(
        cls,
        config: BugTrackerConfig,
        secrets: SecretsAccessor
    ) -> BugTrackerDriver:
        ...

    @classmethod
    def search_open_by_signature(
        cls,
        driver: BugTrackerDriver,
        project_key: str,
        signature_sha256: bytes
    ) -> TicketMatch | None:
        ...

    @classmethod
    def open_ticket(
        cls,
        driver: BugTrackerDriver,
        request: OpenTicketRequest
    ) -> TicketRef:
        ...

    @classmethod
    def comment_on_ticket(
        cls,
        driver: BugTrackerDriver,
        ticket_key: str,
        body: str
    ) -> None:
        ...

    @classmethod
    def get_ticket(
        cls,
        driver: BugTrackerDriver,
        ticket_key: str
    ) -> TicketStatus:
        ...
```

Reference implementations under
`source/site/automojo/factories/pychestrate/bug_tracker/`:

- `JiraBugTrackerDriver` — `PRECEDENCE = 500`.
- `GithubIssuesBugTrackerDriver` — `PRECEDENCE = 500`.
- `LinearBugTrackerDriver` — `PRECEDENCE = 500`.
- `NullBugTrackerDriver` — `PRECEDENCE = 1000`; no-op default when no tracker configured.

### Events Emitted

- `entity.triage.classified` — `{case_id, project_id, run_id, classification, confidence, rationale}`
- `entity.triage.new_bug_detected` — `{case_id, project_id, run_id, stack_signature}`
- `entity.triage.ticket_opened` — `{case_id, tracker, ticket_key}`
- `entity.triage.duplicate_merged` — `{case_id, tracker, ticket_key}`
- `entity.triage.reclassified` — `{case_id, actor_id, from_class, to_class}`

### Events Consumed

- `entity.run.completed` — triggers `classify_run`.
- `entity.flake.classified` — invalidates cached classifications for affected `(catalog_entry_id, test_case_identity_sha256)`.
- `entity.compare.baseline_updated` — invalidates cached baseline state.
- `extension.reloaded` — refresh tracker registry.

## Component Breakdown

All paths rooted at `source/site/automojo/pychestrate/webservice/orchestration/test/triage/`:

- `__init__.py`
- `service.py` — `TriageService`.
- `repository.py` — `TriageRepository`.
- `classifier.py` — pure classification function on `TriageInputs`.
- `signature.py` — stack-trace normalization + SHA-256.
- `tracker_protocol.py` — `BugTrackerDriverProtocol`.
- `tracker_registry.py` — extension-host accessor.
- `auto_open_queue.py` — bounded backoff queue for auto-opens.
- `errors.py` — `TrackerTransientError`.
- `config.py` — `TriageConfig`.
- `rest/v1_routes.py` — REST endpoints.

Factories under `source/site/automojo/factories/pychestrate/bug_tracker/`.

## Key Flows

### Flow 1 — Classify a completed run

1. Subscriber fires on `entity.run.completed`.
2. `TriageService.classify_run(run_id)` iterates failing test cases.
3. For each, compute `stack_signature_sha256` via `signature.normalize_trace`.
4. Query `flake_tracker` and `compare_service` for signals.
5. Check `triage_signature_cache` for existing open ticket; miss → call `driver.search_open_by_signature(...)`.
6. Classifier (pure function) emits `TriageDecision`.
7. Persist `triage_case` and append ledger row with `from_class=None, to_class=decision.classification`.
8. If `classification == new_bug` and `auto_open_new_bug == True`, enqueue `auto_open_queue`.

### Flow 2 — Auto-open flow

1. `auto_open_queue` worker dequeues; idempotency key = `(project_id, stack_signature_sha256)`.
2. Check repo for an existing `ticket_key` under that key — if present, skip open and link.
3. `driver.open_ticket(...)` returns `TicketRef`; link persisted.
4. Duplicate error → merge as `known_issue`; emit `entity.triage.duplicate_merged`.

### Flow 3 — Manual re-classify

1. User posts `:reclassify` with rationale.
2. RBAC `triage.reclassify` enforced.
3. Ledger row appended; `triage_case` updated; event emitted.

## Error Handling

- `SemanticError` for invalid `to_class`, empty rationale, oversized body: bubble.
- `AuthorizationError`: 403 per RBAC.
- `TrackerTransientError`: retried per Aspects; if exhausted, ticketing is deferred (classification still succeeds with `ticket_key = None`).
- Driver native exceptions caught once at the driver boundary and reclassified as `TrackerTransientError` with multiline context; no swallowing.
- Multiline errors via `os.linesep.join([...])`.

## Security Considerations

- Tracker creds from `1-secrets-vault` under scoped paths; never in logs.
- Ticket bodies pass through a masker stripping patterns matching `password|token|secret` (case-insensitive) before being sent to the driver.
- Manual reclassify / tracker-config writes gated by `triage.reclassify` and `triage.config.write`.
- All mutations audited via `1-audit-log`.
- Rate-limit per project `max_auto_opens_per_hour` (default 60) — protects tracker APIs.

## Observability

Metrics:

- `pychestrate_test_triage_classifications_total{project,class}` — counter
- `pychestrate_test_triage_classify_duration_seconds{project}` — histogram
- `pychestrate_test_triage_tickets_opened_total{project,tracker}` — counter
- `pychestrate_test_triage_tracker_errors_total{project,tracker,error_kind}` — counter
- `pychestrate_test_triage_auto_open_queue_depth{project}` — gauge

Log events: `pychestrate.test.triage.classified`, `pychestrate.test.triage.ticket_opened`, `pychestrate.test.triage.duplicate_merged`, `pychestrate.test.triage.reclassified`, `pychestrate.test.triage.tracker_unavailable`.

Trace spans: `pychestrate.test.triage.classify`, `pychestrate.test.triage.search_open`, `pychestrate.test.triage.open_ticket`.

## Open Questions

- Should signature normalization be language-specific (pytest vs gtest stack conventions) or unified? Timebox: Phase 5 midpoint.
- Auto-comment on every re-failure of a known issue — valuable or noisy? Timebox: Phase 5 exit.
- Tracker-side labels sourced from `2-tagging` — map one-to-one or with a site transformer? Timebox: Phase 5 exit.
