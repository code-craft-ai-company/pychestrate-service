"""
.. module:: test_retention_m2
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for 2-retention-policies M2 evaluator and actions.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo import testbase

from automojo.pychestrate.webservice.messaging.event_bus import subscribe
from automojo.pychestrate.webservice.retention import service as retention_service
from automojo.pychestrate.webservice.retention.factories.additional_actions import (
    ArchiveAction,
    PermanentArchiveAction,
    TierMoveAction,
)
from automojo.pychestrate.webservice.retention.models import (
    ActionStep,
    PolicyScopeLevel,
    SelectorClause,
)

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
)
from automojo.tests.singlehost.pychestrate.webservice.phase2.fixtures import (
    reset_phase2_runtime,
)


def test_additional_actions_apply():
    """
    **Feature: 2-retention-policies (M2)**
    **Property: TierMove / Archive / PermanentArchive apply stubs record
    ``applied`` with the correct terminal flag.**
    """
    tm = TierMoveAction.apply(
        entity_kind="artifact", entity_id="a-1", parameters={"target_tier": "cold"}, dry_run=False,
    )
    testbase.assert_equal(tm.outcome, "applied")
    testbase.assert_equal(tm.terminal, False)

    ar = ArchiveAction.apply(
        entity_kind="artifact", entity_id="a-2", parameters={}, dry_run=True,
    )
    testbase.assert_equal(ar.outcome, "applied")
    testbase.assert_equal(ar.terminal, False)

    pa = PermanentArchiveAction.apply(
        entity_kind="artifact", entity_id="a-3", parameters={}, dry_run=False,
    )
    testbase.assert_equal(pa.outcome, "applied")
    testbase.assert_equal(pa.terminal, True)
    return


def test_evaluate_policy_publishes_applied_event():
    """
    **Feature: 2-retention-policies (M2)**
    **Property: evaluate_policy on a published policy records a run and
    publishes entity.retention.applied.**
    """
    reset_phase2_runtime()
    _engine, session = build_in_memory_session()

    received = []
    subscribe(topic="entity.retention.applied", subscriber=lambda e: received.append(e))

    policy = retention_service.create_policy(
        db_session=session,
        name="evaluate-me",
        data_class="run_result",
        scope_level=PolicyScopeLevel.SYSTEM,
        project_id=None,
        selector=SelectorClause(age_days=30),
        action_chain=[
            ActionStep(action_name="delete", parameters={}, wait_days_after_previous=0),
        ],
        interval_minutes=1440,
        batch_size=500,
        max_attempts=3,
        actor_user_id=None,
    )
    retention_service.publish_policy(
        db_session=session, policy_id=str(policy.policy_id), actor_user_id=None,
    )

    run = retention_service.evaluate_policy(
        db_session=session,
        policy_id=str(policy.policy_id),
        candidate_entity_ids=["run-1", "run-2", "run-3"],
        dry_run=False,
        actor_user_id=None,
    )
    testbase.assert_equal(run.matched_count, 3)
    testbase.assert_equal(run.actioned_count, 3)
    testbase.assert_equal(len(received), 1)
    testbase.assert_equal(received[0].payload["matched_count"], 3)
    return
