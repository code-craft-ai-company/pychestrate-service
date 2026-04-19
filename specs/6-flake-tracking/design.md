# 6-flake-tracking — Design

## Architecture

`6-flake-tracking` ingests per-test outcomes from completed runs,
stores a durable per-test history, and classifies each test's
stability using a registered `flake_classifier` factory protocol. It
lives in Phase 5 and is consumed by `6-pipeline-definition` (blocking
gate skip for quarantined tests), `6-test-orchestration` (retry policy
for flaky tests), `6-triage-bug-linking` (flake signal), and
`6-matrix-sharding` (weighted-by-history). The feature runs its
ingest on a dedicated worker subscribing to `entity.run.completed`
so that classification latency does not push back on the run-completion
path. Authoritative source of truth is the testbase
`testrun_results.json` tree + the ingested per-test rows owned here.

## Data Model

Tables in `0-persistence`:

- `test_outcome`:
  - `outcome_id: BIGSERIAL`
  - `project_id: UUID`
  - `catalog_entry_id: UUID`
  - `test_case_identity_sha256: bytes(32)` — primary hash
  - `run_id: UUID`
  - `pod_id: UUID`
  - `runtime_env_digest: str` — fingerprint of pod capabilities/toolchain
  - `outcome: Outcome` — `{pass, fail, error, skip, xfail, xpass}`
  - `duration_ms: int`
  - `started_at: datetime`
  - PK `(outcome_id)`; unique `(run_id, test_case_identity_sha256)`.
- `test_case_identity`:
  - `test_case_identity_sha256: bytes(32)` PK
  - `raw_identity: text` — original identity string
  - `catalog_entry_id: UUID`
- `flake_classification`:
  - `project_id: UUID`
  - `catalog_entry_id: UUID`
  - `test_case_identity_sha256: bytes(32)`
  - `runtime_env_digest: str | None`
  - `classification: FlakeClass` — `{stable, intermittent, flaky, quarantined, broken, insufficient_data}`
  - `classifier_name: str`
  - `classifier_version: str`
  - `sample_count: int`
  - `last_computed_at: datetime`
  - PK `(project_id, catalog_entry_id, test_case_identity_sha256, runtime_env_digest)`.
- `flake_quarantine_ledger`:
  - `ledger_id: BIGSERIAL`
  - `project_id, catalog_entry_id, test_case_identity_sha256`
  - `action: QuarantineAction` — `{quarantine, clear}`
  - `actor_id: UUID`
  - `reason: str`
  - `at: datetime`

Indices: `(project_id, catalog_entry_id, started_at DESC)` on `test_outcome`, `(catalog_entry_id, classification)` on `flake_classification`, GIN-on-`runtime_env_digest`.

Value types:

- `TestHistoryWindow` — `{project_id, catalog_entry_id, test_case_identity_sha256, runtime_env_digest, outcomes: list[OutcomeSample], window_config}`.
- `FlakeClassification` — `{class, confidence, rationale_tag}`.

## Interfaces

### Public API

REST under `8-rest-api-v1`:

- `GET /api/v1/projects/{project_id}/flake/catalog-entry/{entry_id}` → classification + history summary.
- `POST /api/v1/projects/{project_id}/flake/catalog-entry/{entry_id}/quarantine` → mark quarantined.
- `POST /api/v1/projects/{project_id}/flake/catalog-entry/{entry_id}/clear-quarantine` → clear.
- `GET /api/v1/projects/{project_id}/flake/history?catalog_entry_id=&test_case_identity=&env=&limit=&cursor=` → paginated outcomes.

### Internal API

```python
class FlakeTracker:
    def __init__(
        self,
        repo: FlakeRepository,
        catalog: TestCatalog,
        classifier_registry: FlakeClassifierRegistry,
        notifier: NotificationHub,
        rbac: RbacService,
        audit: AuditLog,
        bus: MessageBus,
        clock: Clock,
        config: FlakeConfig
    ) -> None:
        self._repo = repo
        self._catalog = catalog
        self._classifier_registry = classifier_registry
        self._notifier = notifier
        self._rbac = rbac
        self._audit = audit
        self._bus = bus
        self._clock = clock
        self._config = config
        return

    def ingest_run(
        self,
        run_id: UUID
    ) -> IngestResult:
        """
            Pull per-test outcomes for a completed run and append to history.

            :param run_id: Completed run to ingest.

            :returns: IngestResult with counts.
            :raises: RunNotFoundError, ConfigurationError
        """
        ...

    def classify_for_entry(
        self,
        project_id: UUID,
        catalog_entry_id: UUID
    ) -> list[FlakeClassification]:
        """
            Recompute classification for every test case under an entry.

            :returns: Per-(test_case, runtime_env) classifications.
            :raises: ConfigurationError
        """
        ...

    def set_quarantine(
        self,
        actor_id: UUID,
        project_id: UUID,
        catalog_entry_id: UUID,
        test_case_identity_sha256: bytes,
        runtime_env_digest: str | None,
        reason: str
    ) -> None:
        """
            Manually mark a test (optionally per-env) as quarantined.

            :returns: None.
            :raises: AuthorizationError, SemanticError
        """
        ...

    def clear_quarantine(
        self,
        actor_id: UUID,
        project_id: UUID,
        catalog_entry_id: UUID,
        test_case_identity_sha256: bytes,
        runtime_env_digest: str | None,
        reason: str
    ) -> None:
        """
            Clear a quarantine entry; classification recomputed.

            :returns: None.
            :raises: AuthorizationError, SemanticError
        """
        ...
```

### Extension Surface

Factory protocol declared here:

```python
class FlakeClassifierProtocol(FactoryProtocolBase):
    """
        Contract for flake_classifier implementations.
    """
    factory_protocol_name: str = "flake_classifier"

    @classmethod
    def classifier_name(cls) -> str:
        """
            :returns: Stable identifier.
        """
        ...

    @classmethod
    def classifier_version(cls) -> str:
        """
            :returns: Semver string; stored alongside classification.
        """
        ...

    @classmethod
    def window_config(cls) -> FlakeWindowConfig:
        """
            :returns: Max lookback window and min samples.
        """
        ...

    @classmethod
    def classify(
        cls,
        history: TestHistoryWindow
    ) -> FlakeClassification:
        """
            Pure function over history → classification.

            :returns: FlakeClassification.
            :raises: None (return `insufficient_data` on too few samples).
        """
        ...

    @classmethod
    def explain(
        cls,
        history: TestHistoryWindow
    ) -> str:
        """
            Human-readable rationale used in UI and alerts.
        """
        ...
```

Reference implementation in `source/site/automojo/factories/pychestrate/flake_classifier/window_ratio.py`:

- `WindowRatioClassifier` — `PRECEDENCE = 1000`; `stable` if last 20 runs pass; `flaky` if 2+ transitions in last 20; `broken` if 0 passes in last 5; `intermittent` otherwise.

### Events Emitted

- `entity.flake.classified` — `{project_id, catalog_entry_id, test_case_identity_sha256, runtime_env_digest, classification, classifier_name}`
- `entity.flake.quarantined` — `{…, actor_id, reason}`
- `entity.flake.quarantine_cleared` — `{…, actor_id, reason}`
- `entity.flake.broken_alerted` — `{…, owner_principal_id}`

### Events Consumed

- `entity.run.completed` (from `5-run-state-machine`) — triggers ingest.
- `entity.test.catalog.entry_retired` — halts classification updates for the entry.
- `extension.reloaded` — refresh classifier registry.

## Component Breakdown

All paths rooted at `source/site/automojo/pychestrate/webservice/orchestration/test/flake/`:

- `__init__.py`
- `tracker.py` — `FlakeTracker`.
- `repository.py` — `FlakeRepository`.
- `ingest_worker.py` — subscriber for `entity.run.completed`.
- `classifier_protocol.py` — `FlakeClassifierProtocol`.
- `classifier_registry.py` — extension-host accessor.
- `window.py` — `TestHistoryWindow` builder.
- `quarantine_ledger.py` — write/read of the ledger.
- `config.py` — `FlakeConfig`.
- `errors.py` — `RunNotFoundError`.
- `rest/v1_routes.py` — REST endpoints.

Factories under `source/site/automojo/factories/pychestrate/flake_classifier/`.

## Key Flows

### Flow 1 — Ingest after run completion

1. `ingest_worker.py` subscribes to `entity.run.completed`.
2. Pulls `testrun_results.json` via `5-result-ingest-watcher`.
3. For each test case, computes `test_case_identity_sha256 = sha256(raw_identity)`.
4. Inserts into `test_outcome` (unique constraint makes re-ingest idempotent).
5. Enqueues a classification task for each affected `(catalog_entry_id, runtime_env_digest)`.

### Flow 2 — Classification

1. Worker picks up classification task.
2. Builds `TestHistoryWindow` over the configured lookback (default 30 days, 200 samples).
3. Calls `registry.get_top_classifier().classify(window)`.
4. If the classification changes or the ledger was touched, updates `flake_classification` and emits `entity.flake.classified`.
5. On transition to `broken`, `NotificationHub.send_to_owner(...)` fires using `6-test-catalog`'s `owner_principal_id`.

### Flow 3 — Manual quarantine

1. User calls `POST /.../quarantine` with `reason`.
2. RBAC `flake.write` checked; ledger row appended; classification forced to `quarantined`.
3. `entity.flake.quarantined` emitted.
4. `6-pipeline-definition` consumes the event to update cached gate exclusions.

## Error Handling

- `SemanticError` for empty reason, oversized identity, invalid `runtime_env_digest` format: bubble.
- `AuthorizationError`: 403 for `flake.write` / `quarantine.clear`.
- `RunNotFoundError`: 404.
- Classifier raising an exception is caught at the registry boundary, reclassified as `ConfigurationError`, and the classifier is demoted by the host; classification falls back to the next classifier in order.
- Multiline errors via `os.linesep.join([...])`.

## Security Considerations

- Test-case identities may contain PII; raw identities stored under a scoped table with `flake.read:raw_identity` gating retrieval.
- Notification routing uses owner principal only; classifier output never includes run-provided strings.
- Retention sweeps run with a scoped service principal; sweeps append to `1-audit-log`.
- Rate-limit manual quarantine `max_quarantine_ops_per_hour_per_actor` (default 120).

## Observability

Metrics:

- `pychestrate_flake_classifications_total{project,class,classifier}` — counter
- `pychestrate_flake_classify_duration_seconds{project,classifier}` — histogram
- `pychestrate_flake_quarantined_count{project}` — gauge
- `pychestrate_flake_retries_total{project,outcome}` — counter
- `pychestrate_flake_ingest_lag_seconds{project}` — histogram

Log events: `pychestrate.flake.classified`, `pychestrate.flake.quarantined`, `pychestrate.flake.quarantine_cleared`, `pychestrate.flake.broken_alerted`.

Trace spans: `pychestrate.flake.ingest`, `pychestrate.flake.classify`, `pychestrate.flake.quarantine_decide`.

## Open Questions

- Do we store per-env and cross-env classifications as rows, or derive cross-env on-the-fly? Timebox: Phase 5 exit.
- Lookback window — 30 days vs 14 days for Pychestrate's test load. Timebox: Phase 5 midpoint.
- Should `runtime_env_digest` be supplied by `3-client-capability-advertisement` directly or composed here? Timebox: Phase 5 midpoint.
