"""
.. module:: test_flag_m2
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for 1-feature-flags M2 (lifecycle, cache, router, prober).

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, List

from automojo import testbase

from automojo.errors.exceptions import ConfigurationError, SemanticError

from automojo.pychestrate.webservice.extensions.registry import (
    register_factory_implementation,
    unregister_factory_implementation,
)
from automojo.pychestrate.webservice.identity.flags import (
    backend_router,
    cache as flag_cache,
    flag_evaluator,
    flag_service,
    health_prober,
)
from automojo.pychestrate.webservice.identity.flags.events import FlagEventTopics
from automojo.pychestrate.webservice.identity.flags.exceptions import FlagNotFoundError
from automojo.pychestrate.webservice.identity.flags.factories.feature_flag_backend import (
    BackendEvaluation,
    BackendHealth,
    FeatureFlagBackendProtocol,
    FlagDescriptor,
)
from automojo.pychestrate.webservice.identity.flags.models import (
    FlagContext,
    FlagKind,
    FlagState,
)
from automojo.pychestrate.webservice.messaging.event_bus import EntityEvent, publish, subscribe

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
    reset_phase1_runtime,
)


# ---------------------------------------------------------------------------
# T2.1 — ENUM / STRING kinds + immutable kind/key
# ---------------------------------------------------------------------------

def test_string_flag_returns_default_value():
    """
    **Feature: 1-feature-flags M2 (T2.1)**
    **Property: STRING flag returns the persisted default value.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()

    flag_service.create_flag(
        db_session=session,
        flag_key="ui.theme",
        flag_kind=FlagKind.STRING,
        default_value="dark",
        rules=None,
        actor_user_id=None,
    )

    ctx = FlagContext(bucketing_key="user-1", user_id=None, project_id=None, attributes=())
    value = flag_evaluator.evaluate_flag(
        db_session=session, flag_key="ui.theme", context=ctx, default="light"
    )
    testbase.assert_equal(value, "dark")
    return


def test_enum_flag_returns_default_when_in_choices():
    """
    **Feature: 1-feature-flags M2 (T2.1)**
    **Property: ENUM flag returns the persisted default when in enum_choices.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()

    flag_service.create_flag(
        db_session=session,
        flag_key="ui.density",
        flag_kind=FlagKind.ENUM,
        default_value="comfortable",
        rules={"enum_choices": ["compact", "comfortable", "spacious"]},
        actor_user_id=None,
    )

    ctx = FlagContext(bucketing_key="user-1", user_id=None, project_id=None, attributes=())
    value = flag_evaluator.evaluate_flag(
        db_session=session, flag_key="ui.density", context=ctx, default=None
    )
    testbase.assert_equal(value, "comfortable")
    return


def test_enum_flag_default_must_match_choices_at_create():
    """
    **Feature: 1-feature-flags M2 (T2.1)**
    **Property: ENUM default_value not present in enum_choices raises SemanticError.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()

    raised = False
    try:
        flag_service.create_flag(
            db_session=session,
            flag_key="ui.density",
            flag_kind=FlagKind.ENUM,
            default_value="extra-large",
            rules={"enum_choices": ["compact", "comfortable"]},
            actor_user_id=None,
        )
    except SemanticError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_attribute_match_routes_string_value():
    """
    **Feature: 1-feature-flags M2 (T2.1)**
    **Property: attribute_matches return value overrides the default for STRING.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()

    flag_service.create_flag(
        db_session=session,
        flag_key="ui.theme",
        flag_kind=FlagKind.STRING,
        default_value="dark",
        rules={
            "attribute_matches": [
                {"attr": "project_id", "equals": "alpha", "return": "high-contrast"}
            ]
        },
        actor_user_id=None,
    )

    ctx_match = FlagContext(
        bucketing_key="user-in-alpha", user_id=None, project_id="alpha", attributes=()
    )
    ctx_miss = FlagContext(
        bucketing_key="user-in-beta", user_id=None, project_id="beta", attributes=()
    )

    matched = flag_evaluator.evaluate_flag(
        db_session=session, flag_key="ui.theme", context=ctx_match, default=""
    )
    fallback = flag_evaluator.evaluate_flag(
        db_session=session, flag_key="ui.theme", context=ctx_miss, default=""
    )
    testbase.assert_equal(matched, "high-contrast")
    testbase.assert_equal(fallback, "dark")
    return


# ---------------------------------------------------------------------------
# T2.2 — update_flag_rules
# ---------------------------------------------------------------------------

def test_update_flag_rules_bumps_version():
    """
    **Feature: 1-feature-flags M2 (T2.2)**
    **Property: update_flag_rules increments current_version and inserts a new version row.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()

    flag = flag_service.create_flag(
        db_session=session,
        flag_key="experiment.alpha",
        flag_kind=FlagKind.PERCENTAGE,
        default_value=False,
        rules={"rollout_percentage_bp": 1000},
        actor_user_id=None,
    )
    testbase.assert_equal(int(flag.current_version), 1)

    updated = flag_service.update_flag_rules(
        db_session=session,
        flag_key="experiment.alpha",
        flag_kind=None,
        default_value=False,
        rules={"rollout_percentage_bp": 5000},
        actor_user_id=None,
    )
    testbase.assert_equal(int(updated.current_version), 2)

    versions = flag_service.list_flag_versions(db_session=session, flag_key="experiment.alpha")
    testbase.assert_equal(len(versions), 2)
    testbase.assert_equal(int(versions[0].version), 1)
    testbase.assert_equal(int(versions[1].version), 2)
    testbase.assert_equal(int(versions[1].rules_json.get("rollout_percentage_bp")), 5000)
    return


def test_update_flag_rules_rejects_kind_change():
    """
    **Feature: 1-feature-flags M2 (T2.1 / Requirement 2.4)**
    **Property: Passing a different flag_kind into update raises SemanticError.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()

    flag_service.create_flag(
        db_session=session,
        flag_key="experiment.alpha",
        flag_kind=FlagKind.BOOLEAN,
        default_value=True,
        rules=None,
        actor_user_id=None,
    )

    raised = False
    try:
        flag_service.update_flag_rules(
            db_session=session,
            flag_key="experiment.alpha",
            flag_kind=FlagKind.STRING,
            default_value="hello",
            rules=None,
            actor_user_id=None,
        )
    except SemanticError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_update_unknown_flag_raises_not_found():
    """
    **Feature: 1-feature-flags M2 (T2.2)**
    **Property: Updating an unknown flag raises FlagNotFoundError.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()

    raised = False
    try:
        flag_service.update_flag_rules(
            db_session=session,
            flag_key="does.not.exist",
            flag_kind=None,
            default_value=True,
            rules=None,
            actor_user_id=None,
        )
    except FlagNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return


# ---------------------------------------------------------------------------
# T2.3 — retire / grace removal
# ---------------------------------------------------------------------------

def test_retire_flag_marks_state_and_emits_event():
    """
    **Feature: 1-feature-flags M2 (T2.3)**
    **Property: retire_flag marks state RETIRED and publishes entity.flag.retired.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()

    flag_service.create_flag(
        db_session=session,
        flag_key="experiment.alpha",
        flag_kind=FlagKind.BOOLEAN,
        default_value=True,
        rules=None,
        actor_user_id=None,
    )

    received: List[EntityEvent] = []

    def _record(evt: EntityEvent) -> None:
        received.append(evt)
        return

    subscribe(topic=FlagEventTopics.FLAG_RETIRED, subscriber=_record)

    retired = flag_service.retire_flag(
        db_session=session,
        flag_key="experiment.alpha",
        grace_seconds=0,
        actor_user_id=None,
    )
    testbase.assert_equal(retired.state, FlagState.RETIRED)
    testbase.assert_equal(len(received), 1)
    testbase.assert_equal(received[0].topic, FlagEventTopics.FLAG_RETIRED)
    return


def test_remove_expired_retired_flags_publishes_removed_event():
    """
    **Feature: 1-feature-flags M2 (T2.3)**
    **Property: After grace expires, the sweep publishes entity.flag.removed and deletes rows.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()

    flag_service.create_flag(
        db_session=session,
        flag_key="experiment.alpha",
        flag_kind=FlagKind.BOOLEAN,
        default_value=True,
        rules=None,
        actor_user_id=None,
    )
    flag_service.retire_flag(
        db_session=session,
        flag_key="experiment.alpha",
        grace_seconds=0,
        actor_user_id=None,
    )

    removed_events: List[EntityEvent] = []

    def _record(evt: EntityEvent) -> None:
        removed_events.append(evt)
        return

    subscribe(topic=FlagEventTopics.FLAG_REMOVED, subscriber=_record)

    removed_keys = flag_service.remove_expired_retired_flags(db_session=session)
    testbase.assert_equal(removed_keys, ["experiment.alpha"])
    testbase.assert_equal(len(removed_events), 1)

    remaining = flag_service.list_flags(db_session=session)
    testbase.assert_equal(len(remaining), 0)
    return


# ---------------------------------------------------------------------------
# T2.4 — staleness window cache
# ---------------------------------------------------------------------------

def test_cache_returns_stored_value_within_window():
    """
    **Feature: 1-feature-flags M2 (T2.4)**
    **Property: A second evaluation hits the cache and returns the stored value.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()

    fake_clock_value = [0.0]

    def _clock() -> float:
        rtnval = fake_clock_value[0]
        return rtnval

    flag_cache.configure(staleness_window_seconds=60.0, clock=_clock)

    flag_service.create_flag(
        db_session=session,
        flag_key="experiment.alpha",
        flag_kind=FlagKind.BOOLEAN,
        default_value=True,
        rules=None,
        actor_user_id=None,
    )

    ctx = FlagContext(bucketing_key="user-1", user_id=None, project_id=None, attributes=())

    first = flag_evaluator.evaluate_flag(
        db_session=session, flag_key="experiment.alpha", context=ctx, default=False
    )
    testbase.assert_equal(first, True)

    cached_lookup = flag_cache.lookup(
        flag_key="experiment.alpha", flag_version=1, bucketing_key="user-1"
    )
    testbase.assert_equal(cached_lookup, True)

    fake_clock_value[0] = 30.0
    still_fresh = flag_cache.lookup(
        flag_key="experiment.alpha", flag_version=1, bucketing_key="user-1"
    )
    testbase.assert_equal(still_fresh, True)
    return


def test_cache_expires_after_window():
    """
    **Feature: 1-feature-flags M2 (T2.4)**
    **Property: Cache entries are dropped once the staleness window passes.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()

    fake_clock_value = [0.0]

    def _clock() -> float:
        rtnval = fake_clock_value[0]
        return rtnval

    flag_cache.configure(staleness_window_seconds=10.0, clock=_clock)

    flag_service.create_flag(
        db_session=session,
        flag_key="experiment.alpha",
        flag_kind=FlagKind.BOOLEAN,
        default_value=True,
        rules=None,
        actor_user_id=None,
    )

    ctx = FlagContext(bucketing_key="user-1", user_id=None, project_id=None, attributes=())
    flag_evaluator.evaluate_flag(
        db_session=session, flag_key="experiment.alpha", context=ctx, default=False
    )

    fake_clock_value[0] = 11.0
    expired = flag_cache.lookup(
        flag_key="experiment.alpha", flag_version=1, bucketing_key="user-1"
    )
    testbase.assert_equal(expired, None)
    return


def test_cache_invalidated_on_update_event():
    """
    **Feature: 1-feature-flags M2 (T2.4)**
    **Property: The bus subscriber drops cache entries on entity.flag.updated.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()

    flag_service.create_flag(
        db_session=session,
        flag_key="experiment.alpha",
        flag_kind=FlagKind.BOOLEAN,
        default_value=True,
        rules=None,
        actor_user_id=None,
    )

    ctx = FlagContext(bucketing_key="user-1", user_id=None, project_id=None, attributes=())
    flag_evaluator.evaluate_flag(
        db_session=session, flag_key="experiment.alpha", context=ctx, default=False
    )

    cached = flag_cache.lookup(
        flag_key="experiment.alpha", flag_version=1, bucketing_key="user-1"
    )
    testbase.assert_equal(cached, True)

    flag_service.update_flag_rules(
        db_session=session,
        flag_key="experiment.alpha",
        flag_kind=None,
        default_value=False,
        rules=None,
        actor_user_id=None,
    )

    after_update_v1 = flag_cache.lookup(
        flag_key="experiment.alpha", flag_version=1, bucketing_key="user-1"
    )
    testbase.assert_equal(after_update_v1, None)
    return


# ---------------------------------------------------------------------------
# T2.5 — backend router pattern + precedence
# ---------------------------------------------------------------------------

class _ExperimentBackend(FeatureFlagBackendProtocol):
    """
        Test-only backend claiming ``experiment.*`` at higher priority.
    """

    factory_protocol_name: str = "feature_flag_backend"
    protocol_schema_version: int = 1
    PRECEDENCE: int = 500

    @classmethod
    def backend_name(cls) -> str:
        rtnval = "test-experiment-backend"
        return rtnval

    @classmethod
    def flag_key_pattern(cls) -> str:
        rtnval = "experiment.*"
        return rtnval

    @classmethod
    def evaluate(
            cls,
            *,
            flag_key: str,
            context: FlagContext,
            default: Any
        ) -> BackendEvaluation:
        rtnval = BackendEvaluation(value=default, reason="test_experiment_backend")
        return rtnval

    @classmethod
    def list_flags(cls):
        rtnval: tuple = ()
        return rtnval

    @classmethod
    def health_check(cls) -> BackendHealth:
        rtnval = BackendHealth(healthy=True, reason="")
        return rtnval


def test_router_resolves_higher_precedence_for_pattern_match():
    """
    **Feature: 1-feature-flags M2 (T2.5)**
    **Property: A backend claiming experiment.* at lower PRECEDENCE wins over local-db.**
    """
    reset_phase1_runtime()
    register_factory_implementation(implementation=_ExperimentBackend)

    try:
        winner_for_experiment = backend_router.resolve_backend(flag_key="experiment.alpha")
        winner_for_other = backend_router.resolve_backend(flag_key="auth.local_fallback_enabled")
    finally:
        unregister_factory_implementation(implementation=_ExperimentBackend)

    testbase.assert_equal(winner_for_experiment.backend_name(), "test-experiment-backend")
    testbase.assert_equal(winner_for_other.backend_name(), "local-db")
    return


def test_router_raises_when_no_backend_registered():
    """
    **Feature: 1-feature-flags M2 (T2.5)**
    **Property: With zero backends registered, resolve_backend raises ConfigurationError.**
    """
    reset_phase1_runtime()
    unregister_factory_implementation(
        implementation=_get_local_backend_class()
    )

    raised = False
    try:
        backend_router.resolve_backend(flag_key="any.key")
    except ConfigurationError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def _get_local_backend_class():
    from automojo.pychestrate.webservice.identity.flags.factories.local_backend import (
        LocalDatabaseFeatureFlagBackend,
    )
    rtnval = LocalDatabaseFeatureFlagBackend
    return rtnval


# ---------------------------------------------------------------------------
# T2.6 — health prober
# ---------------------------------------------------------------------------

class _FlakyBackend(FeatureFlagBackendProtocol):
    """
        Backend whose health flips between failure and success based on the
        class-level ``HEALTH_QUEUE`` attribute. Tests pop one entry per probe.
    """

    factory_protocol_name: str = "feature_flag_backend"
    protocol_schema_version: int = 1
    PRECEDENCE: int = 600

    HEALTH_QUEUE: List[BackendHealth] = []

    @classmethod
    def backend_name(cls) -> str:
        rtnval = "flaky-test-backend"
        return rtnval

    @classmethod
    def flag_key_pattern(cls) -> str:
        rtnval = "flaky.*"
        return rtnval

    @classmethod
    def evaluate(
            cls,
            *,
            flag_key: str,
            context: FlagContext,
            default: Any
        ) -> BackendEvaluation:
        rtnval = BackendEvaluation(value=default, reason="flaky")
        return rtnval

    @classmethod
    def list_flags(cls):
        rtnval: tuple = ()
        return rtnval

    @classmethod
    def health_check(cls) -> BackendHealth:
        if len(cls.HEALTH_QUEUE) == 0:
            rtnval = BackendHealth(healthy=True, reason="")
            return rtnval
        rtnval = cls.HEALTH_QUEUE.pop(0)
        return rtnval


def test_prober_emits_unhealthy_after_three_consecutive_failures():
    """
    **Feature: 1-feature-flags M2 (T2.6)**
    **Property: Three consecutive failed probes emit entity.flag.backend.unhealthy.**
    """
    reset_phase1_runtime()
    _FlakyBackend.HEALTH_QUEUE = [
        BackendHealth(healthy=False, reason="cnx-refused"),
        BackendHealth(healthy=False, reason="cnx-refused"),
        BackendHealth(healthy=False, reason="cnx-refused"),
        BackendHealth(healthy=True, reason=""),
    ]
    register_factory_implementation(implementation=_FlakyBackend)

    received: List[EntityEvent] = []

    def _record(evt: EntityEvent) -> None:
        received.append(evt)
        return

    subscribe(topic=FlagEventTopics.BACKEND_UNHEALTHY, subscriber=_record)
    subscribe(topic=FlagEventTopics.BACKEND_HEALTHY, subscriber=_record)

    try:
        health_prober.probe_once()
        testbase.assert_equal(len(received), 0)

        health_prober.probe_once()
        testbase.assert_equal(len(received), 0)

        health_prober.probe_once()
        unhealthy_topics = [
            evt.topic for evt in received if evt.topic == FlagEventTopics.BACKEND_UNHEALTHY
        ]
        testbase.assert_equal(len(unhealthy_topics), 1)

        health_prober.probe_once()
        healthy_topics = [
            evt.topic for evt in received if evt.topic == FlagEventTopics.BACKEND_HEALTHY
        ]
        testbase.assert_equal(len(healthy_topics), 1)
    finally:
        unregister_factory_implementation(implementation=_FlakyBackend)
        _FlakyBackend.HEALTH_QUEUE = []
    return


def test_prober_isolates_raising_backend():
    """
    **Feature: 1-feature-flags M2 (T2.6)**
    **Property: A backend whose health_check raises is treated as unhealthy.**
    """
    reset_phase1_runtime()

    class _RaisingBackend(FeatureFlagBackendProtocol):
        factory_protocol_name: str = "feature_flag_backend"
        protocol_schema_version: int = 1
        PRECEDENCE: int = 700

        @classmethod
        def backend_name(cls) -> str:
            rtnval = "raising-test-backend"
            return rtnval

        @classmethod
        def flag_key_pattern(cls) -> str:
            rtnval = "raise.*"
            return rtnval

        @classmethod
        def evaluate(
                cls,
                *,
                flag_key: str,
                context: FlagContext,
                default: Any
            ) -> BackendEvaluation:
            rtnval = BackendEvaluation(value=default, reason="raising")
            return rtnval

        @classmethod
        def list_flags(cls):
            rtnval: tuple = ()
            return rtnval

        @classmethod
        def health_check(cls) -> BackendHealth:
            raise RuntimeError("simulated probe failure")

    register_factory_implementation(implementation=_RaisingBackend)

    try:
        results = health_prober.probe_once()
    finally:
        unregister_factory_implementation(implementation=_RaisingBackend)

    matched = [name for name, _h in results if name == "raising-test-backend"]
    testbase.assert_equal(len(matched), 1)
    matched_health = [h for name, h in results if name == "raising-test-backend"][0]
    testbase.assert_equal(matched_health.healthy, False)
    return


# ---------------------------------------------------------------------------
# T2.7 — REST controller behaviors covered through service layer; full
# Flask-app wiring is exercised by the Phase-1 integration tests.
# ---------------------------------------------------------------------------

def test_list_flags_orders_by_key():
    """
    **Feature: 1-feature-flags M2 (T2.7)**
    **Property: list_flags returns rows ordered by flag_key.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()

    flag_service.create_flag(
        db_session=session,
        flag_key="zeta.flag",
        flag_kind=FlagKind.BOOLEAN,
        default_value=True,
        rules=None,
        actor_user_id=None,
    )
    flag_service.create_flag(
        db_session=session,
        flag_key="alpha.flag",
        flag_kind=FlagKind.BOOLEAN,
        default_value=False,
        rules=None,
        actor_user_id=None,
    )

    listed = flag_service.list_flags(db_session=session)
    keys = [flag.flag_key for flag in listed]
    testbase.assert_equal(keys, ["alpha.flag", "zeta.flag"])
    return
