"""
.. module:: test_p14a_retention_legal_hold_retry_m3
    :synopsis: Tests for P14a — 2-retention-policies M3
               (legal_hold gating + retry budget).
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, ClassVar, Mapping

from automojo import testbase

from automojo.pychestrate.webservice.extensions.registry import (
    register_factory_implementation,
    reset_registry_for_testing,
    unregister_factory_implementation,
)
from automojo.pychestrate.webservice.messaging.event_bus import (
    reset_for_testing as reset_event_bus,
)
from automojo.pychestrate.webservice.retention import legal_hold as legal_hold_service
from automojo.pychestrate.webservice.retention.dispatcher import (
    dispatch_action_chain,
)
from automojo.pychestrate.webservice.retention.factories.action import (
    ActionApplication,
    RetentionActionProtocol,
)
from automojo.pychestrate.webservice.retention.models import ActionStep

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
)


def _prepare_runtime() -> None:
    reset_registry_for_testing()
    reset_event_bus()
    return


# -------------------------------------
# Test fixtures
# -------------------------------------

class _DeleteAction(RetentionActionProtocol):
    """
        Stand-in destructive action — its presence in the
        legal_hold-blocked set is what makes the dispatcher
        skip the step under hold.
    """
    factory_protocol_name: ClassVar[str] = "retention_action"
    action_name: ClassVar[str] = "delete"
    terminal: ClassVar[bool] = True
    PRECEDENCE: ClassVar[int] = 100

    @classmethod
    def apply(cls, *, entity_kind, entity_id, parameters, dry_run):
        return ActionApplication(
            outcome="applied",
            reason="deleted",
            terminal=True,
        )


class _NondestructiveAction(RetentionActionProtocol):
    factory_protocol_name: ClassVar[str] = "retention_action"
    action_name: ClassVar[str] = "tier_move"
    terminal: ClassVar[bool] = False
    PRECEDENCE: ClassVar[int] = 100

    @classmethod
    def apply(cls, *, entity_kind, entity_id, parameters, dry_run):
        return ActionApplication(
            outcome="applied",
            reason="tier_moved",
            terminal=False,
        )


class _FlakyActionState:
    fail_attempts: int = 1
    seen_attempts: int = 0


class _FlakyAction(RetentionActionProtocol):
    factory_protocol_name: ClassVar[str] = "retention_action"
    action_name: ClassVar[str] = "p14a_flaky"
    terminal: ClassVar[bool] = False
    PRECEDENCE: ClassVar[int] = 100

    @classmethod
    def apply(cls, *, entity_kind, entity_id, parameters, dry_run):
        _FlakyActionState.seen_attempts = (
            _FlakyActionState.seen_attempts + 1
        )
        if _FlakyActionState.seen_attempts <= _FlakyActionState.fail_attempts:
            raise RuntimeError(
                "transient_failure_attempt_{}".format(
                    _FlakyActionState.seen_attempts,
                ),
            )
        return ActionApplication(
            outcome="applied",
            reason="recovered",
            terminal=False,
        )


class _AlwaysFailedAction(RetentionActionProtocol):
    factory_protocol_name: ClassVar[str] = "retention_action"
    action_name: ClassVar[str] = "p14a_always_failed"
    terminal: ClassVar[bool] = False
    PRECEDENCE: ClassVar[int] = 100

    @classmethod
    def apply(cls, *, entity_kind, entity_id, parameters, dry_run):
        return ActionApplication(
            outcome="failed",
            reason="downstream_unavailable",
            terminal=False,
        )


def _setup_actions() -> None:
    register_factory_implementation(implementation=_DeleteAction)
    register_factory_implementation(implementation=_NondestructiveAction)
    register_factory_implementation(implementation=_FlakyAction)
    register_factory_implementation(implementation=_AlwaysFailedAction)
    return


def _teardown_actions() -> None:
    for impl in (
        _DeleteAction, _NondestructiveAction,
        _FlakyAction, _AlwaysFailedAction,
    ):
        try:
            unregister_factory_implementation(implementation=impl)
        except Exception:
            pass
    return


# -------------------------------------
# Legal-hold gating
# -------------------------------------

def test_legal_hold_skips_destructive_action():
    """
    **Feature: 2-retention-policies (M3)**
    **Property: a destructive action against a held entity
    is recorded as outcome='skipped' / reason='legal_hold'
    and the chain continues past it.**
    """
    _prepare_runtime()
    _setup_actions()
    try:
        _engine, session = build_in_memory_session()
        legal_hold_service.place_hold(
            db_session=session,
            entity_kind="artifact",
            entity_id="art-1",
            reason="compliance",
            actor_user_id=None,
        )
        result = dispatch_action_chain(
            entity_kind="artifact",
            entity_id="art-1",
            steps=[
                ActionStep(action_name="delete", parameters={}),
            ],
            dry_run=False,
            db_session=session,
        )
        testbase.assert_equal(len(result.steps), 1)
        testbase.assert_equal(result.steps[0].outcome, "skipped")
        testbase.assert_equal(result.steps[0].reason, "legal_hold")
        testbase.assert_equal(result.final_outcome, "skipped")
    finally:
        _teardown_actions()
    return


def test_legal_hold_does_not_block_nondestructive_actions():
    """
    **Feature: 2-retention-policies (M3)**
    **Property: legal_hold only blocks destructive actions
    (delete, permanent_archive); tier_move continues to apply
    so storage tier moves forward without losing data.**
    """
    _prepare_runtime()
    _setup_actions()
    try:
        _engine, session = build_in_memory_session()
        legal_hold_service.place_hold(
            db_session=session,
            entity_kind="artifact",
            entity_id="art-1",
            reason="compliance",
            actor_user_id=None,
        )
        result = dispatch_action_chain(
            entity_kind="artifact",
            entity_id="art-1",
            steps=[
                ActionStep(action_name="tier_move", parameters={}),
            ],
            dry_run=False,
            db_session=session,
        )
        testbase.assert_equal(result.steps[0].outcome, "applied")
        testbase.assert_equal(result.final_outcome, "applied")
    finally:
        _teardown_actions()
    return


def test_legal_hold_released_allows_action():
    """
    **Feature: 2-retention-policies (M3)**
    **Property: releasing the hold + replaying applies the
    destructive action normally.**
    """
    _prepare_runtime()
    _setup_actions()
    try:
        _engine, session = build_in_memory_session()
        legal_hold_service.place_hold(
            db_session=session,
            entity_kind="artifact",
            entity_id="art-1",
            reason="compliance",
            actor_user_id=None,
        )
        first = dispatch_action_chain(
            entity_kind="artifact",
            entity_id="art-1",
            steps=[ActionStep(action_name="delete", parameters={})],
            dry_run=False,
            db_session=session,
        )
        legal_hold_service.release_hold(
            db_session=session,
            entity_kind="artifact",
            entity_id="art-1",
        )
        second = dispatch_action_chain(
            entity_kind="artifact",
            entity_id="art-1",
            steps=[ActionStep(action_name="delete", parameters={})],
            dry_run=False,
            db_session=session,
        )
        testbase.assert_equal(first.steps[0].outcome, "skipped")
        testbase.assert_equal(second.steps[0].outcome, "applied")
    finally:
        _teardown_actions()
    return


def test_legal_hold_skipped_on_dry_run_path():
    """
    **Feature: 2-retention-policies (M3)**
    **Property: dry_run does not consult legal_hold so
    operators always see the full plan.**
    """
    _prepare_runtime()
    _setup_actions()
    try:
        _engine, session = build_in_memory_session()
        legal_hold_service.place_hold(
            db_session=session,
            entity_kind="artifact",
            entity_id="art-1",
            reason="compliance",
            actor_user_id=None,
        )
        result = dispatch_action_chain(
            entity_kind="artifact",
            entity_id="art-1",
            steps=[ActionStep(action_name="delete", parameters={})],
            dry_run=True,
            db_session=session,
        )
        testbase.assert_equal(result.steps[0].outcome, "applied")
    finally:
        _teardown_actions()
    return


def test_dispatcher_without_db_session_does_not_consult_legal_hold():
    """
    **Feature: 2-retention-policies (M3)**
    **Property: when the caller does not supply a db_session
    the dispatcher behaves like M2 — destructive actions
    apply regardless of any persisted hold.**
    """
    _prepare_runtime()
    _setup_actions()
    try:
        _engine, session = build_in_memory_session()
        legal_hold_service.place_hold(
            db_session=session,
            entity_kind="artifact",
            entity_id="art-1",
            reason="compliance",
            actor_user_id=None,
        )
        result = dispatch_action_chain(
            entity_kind="artifact",
            entity_id="art-1",
            steps=[ActionStep(action_name="delete", parameters={})],
            dry_run=False,
        )
        testbase.assert_equal(result.steps[0].outcome, "applied")
    finally:
        _teardown_actions()
    return


# -------------------------------------
# Retry budget
# -------------------------------------

def test_retry_budget_recovers_from_transient_failure():
    """
    **Feature: 2-retention-policies (M3)**
    **Property: a flaky action that fails once and succeeds
    on retry surfaces outcome='applied' under
    max_attempts=2.**
    """
    _prepare_runtime()
    _setup_actions()
    _FlakyActionState.fail_attempts = 1
    _FlakyActionState.seen_attempts = 0
    try:
        result = dispatch_action_chain(
            entity_kind="artifact",
            entity_id="art-1",
            steps=[ActionStep(action_name="p14a_flaky", parameters={})],
            dry_run=False,
            max_attempts=2,
        )
        testbase.assert_equal(result.steps[0].outcome, "applied")
        testbase.assert_equal(_FlakyActionState.seen_attempts, 2)
    finally:
        _teardown_actions()
    return


def test_retry_budget_records_failed_after_exhaustion():
    """
    **Feature: 2-retention-policies (M3)**
    **Property: a flaky action that fails every attempt
    surfaces outcome='failed' after max_attempts is
    exhausted, with the last error preserved in reason.**
    """
    _prepare_runtime()
    _setup_actions()
    _FlakyActionState.fail_attempts = 5
    _FlakyActionState.seen_attempts = 0
    try:
        result = dispatch_action_chain(
            entity_kind="artifact",
            entity_id="art-1",
            steps=[ActionStep(action_name="p14a_flaky", parameters={})],
            dry_run=False,
            max_attempts=3,
        )
        testbase.assert_equal(result.steps[0].outcome, "failed")
        testbase.assert_equal(_FlakyActionState.seen_attempts, 3)
        testbase.assert_equal(
            "transient_failure_attempt_3" in result.steps[0].reason,
            True,
        )
    finally:
        _teardown_actions()
    return


def test_retry_budget_default_one_preserves_m2_semantics():
    """
    **Feature: 2-retention-policies (M3)**
    **Property: max_attempts defaults to 1 — the M2 caller
    semantics are unchanged unless an explicit retry budget
    is supplied.**
    """
    _prepare_runtime()
    _setup_actions()
    _FlakyActionState.fail_attempts = 5
    _FlakyActionState.seen_attempts = 0
    try:
        result = dispatch_action_chain(
            entity_kind="artifact",
            entity_id="art-1",
            steps=[ActionStep(action_name="p14a_flaky", parameters={})],
            dry_run=False,
        )
        testbase.assert_equal(result.steps[0].outcome, "failed")
        testbase.assert_equal(_FlakyActionState.seen_attempts, 1)
    finally:
        _teardown_actions()
    return


def test_retry_budget_invalid_max_attempts_raises():
    """
    **Feature: 2-retention-policies (M3)**
    **Property: max_attempts <= 0 raises ValueError so the
    caller misuse surfaces loudly.**
    """
    _prepare_runtime()
    _setup_actions()
    try:
        raised = False
        try:
            dispatch_action_chain(
                entity_kind="artifact",
                entity_id="art-1",
                steps=[ActionStep(action_name="delete", parameters={})],
                dry_run=False,
                max_attempts=0,
            )
        except ValueError:
            raised = True
        testbase.assert_equal(raised, True)
    finally:
        _teardown_actions()
    return


def test_retry_budget_failed_action_is_retried():
    """
    **Feature: 2-retention-policies (M3)**
    **Property: an action that returns outcome='failed'
    (without raising) is retried up to max_attempts before
    the final failure is recorded.**
    """
    _prepare_runtime()
    _setup_actions()
    try:
        result = dispatch_action_chain(
            entity_kind="artifact",
            entity_id="art-1",
            steps=[
                ActionStep(action_name="p14a_always_failed", parameters={}),
            ],
            dry_run=False,
            max_attempts=3,
        )
        testbase.assert_equal(result.steps[0].outcome, "failed")
        testbase.assert_equal(
            "downstream_unavailable" in result.steps[0].reason,
            True,
        )
    finally:
        _teardown_actions()
    return
