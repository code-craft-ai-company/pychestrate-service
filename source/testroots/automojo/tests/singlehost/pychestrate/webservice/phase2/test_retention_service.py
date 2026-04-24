"""
.. module:: test_retention_service
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for 2-retention-policies M1 service surface.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo import testbase

from automojo.pychestrate.webservice.messaging.event_bus import subscribe
from automojo.pychestrate.webservice.retention import service as retention_service
from automojo.pychestrate.webservice.retention.exceptions import (
    PolicyAlreadyExistsError,
    PolicyStateTransitionError,
    UnsupportedRetentionActionError,
)
from automojo.pychestrate.webservice.retention.factories.delete_action import DeleteAction
from automojo.pychestrate.webservice.retention.models import (
    ActionStep,
    PolicyScopeLevel,
    PolicyState,
    SelectorClause,
)

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
)
from automojo.tests.singlehost.pychestrate.webservice.phase2.fixtures import (
    reset_phase2_runtime,
)


def _build_delete_chain():
    """
        Return an :class:`ActionStep` list containing just the Delete action.
    """
    rtnval = [
        ActionStep(
            action_name="delete",
            parameters={},
            wait_days_after_previous=0,
        ),
    ]
    return rtnval


def test_create_policy_round_trip():
    """
    **Feature: 2-retention-policies (M1)**
    **Property: create_policy persists a DRAFT row and emits
    entity.retention.policy_created.**
    """
    reset_phase2_runtime()
    _engine, session = build_in_memory_session()

    received = []
    subscribe(
        topic="entity.retention.policy_created",
        subscriber=lambda e: received.append(e),
    )

    policy = retention_service.create_policy(
        db_session=session,
        name="test-run-results-90d",
        data_class="run_result",
        scope_level=PolicyScopeLevel.SYSTEM,
        project_id=None,
        selector=SelectorClause(age_days=90),
        action_chain=_build_delete_chain(),
        interval_minutes=1440,
        batch_size=500,
        max_attempts=3,
        actor_user_id=None,
    )

    testbase.assert_equal(policy.state, PolicyState.DRAFT)
    testbase.assert_equal(policy.name, "test-run-results-90d")
    testbase.assert_equal(len(received), 1)
    return


def test_create_policy_duplicate_name_conflict():
    """
    **Feature: 2-retention-policies (M1)**
    **Property: A second create_policy with the same scope+name raises
    PolicyAlreadyExistsError.**
    """
    reset_phase2_runtime()
    _engine, session = build_in_memory_session()

    retention_service.create_policy(
        db_session=session,
        name="dup-policy",
        data_class="run_result",
        scope_level=PolicyScopeLevel.SYSTEM,
        project_id=None,
        selector=SelectorClause(age_days=30),
        action_chain=_build_delete_chain(),
        interval_minutes=1440,
        batch_size=500,
        max_attempts=3,
        actor_user_id=None,
    )

    raised = False
    try:
        retention_service.create_policy(
            db_session=session,
            name="dup-policy",
            data_class="run_result",
            scope_level=PolicyScopeLevel.SYSTEM,
            project_id=None,
            selector=SelectorClause(age_days=30),
            action_chain=_build_delete_chain(),
            interval_minutes=1440,
            batch_size=500,
            max_attempts=3,
            actor_user_id=None,
        )
    except PolicyAlreadyExistsError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_create_policy_unknown_action_raises():
    """
    **Feature: 2-retention-policies (M1)**
    **Property: Referencing an action_name with no registered
    implementation raises UnsupportedRetentionActionError.**
    """
    reset_phase2_runtime()
    _engine, session = build_in_memory_session()

    raised = False
    try:
        retention_service.create_policy(
            db_session=session,
            name="bogus-policy",
            data_class="run_result",
            scope_level=PolicyScopeLevel.SYSTEM,
            project_id=None,
            selector=SelectorClause(),
            action_chain=[
                ActionStep(
                    action_name="teleport",
                    parameters={},
                    wait_days_after_previous=0,
                ),
            ],
            interval_minutes=1440,
            batch_size=500,
            max_attempts=3,
            actor_user_id=None,
        )
    except UnsupportedRetentionActionError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_publish_policy_transitions_and_emits():
    """
    **Feature: 2-retention-policies (M1)**
    **Property: publish_policy moves DRAFT → PUBLISHED and publishes
    entity.retention.policy_published.**
    """
    reset_phase2_runtime()
    _engine, session = build_in_memory_session()

    received = []
    subscribe(
        topic="entity.retention.policy_published",
        subscriber=lambda e: received.append(e),
    )

    policy = retention_service.create_policy(
        db_session=session,
        name="publish-me",
        data_class="run_result",
        scope_level=PolicyScopeLevel.SYSTEM,
        project_id=None,
        selector=SelectorClause(age_days=7),
        action_chain=_build_delete_chain(),
        interval_minutes=1440,
        batch_size=500,
        max_attempts=3,
        actor_user_id=None,
    )

    updated = retention_service.publish_policy(
        db_session=session,
        policy_id=str(policy.policy_id),
        actor_user_id=None,
    )
    testbase.assert_equal(updated.state, PolicyState.PUBLISHED)
    testbase.assert_equal(len(received), 1)
    return


def test_delete_action_stub_applies():
    """
    **Feature: 2-retention-policies (M1)**
    **Property: DeleteAction.apply returns an ``applied`` outcome with
    ``terminal=True``.**
    """
    outcome = DeleteAction.apply(
        entity_kind="run_result",
        entity_id="run-42",
        parameters={"dry_run_ok": True},
        dry_run=False,
    )
    testbase.assert_equal(outcome.outcome, "applied")
    testbase.assert_equal(outcome.terminal, True)
    return
