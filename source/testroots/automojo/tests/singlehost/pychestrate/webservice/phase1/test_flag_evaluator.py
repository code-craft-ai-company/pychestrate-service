"""
.. module:: test_flag_evaluator
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for 1-feature-flags rules + evaluator + service.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo import testbase

from automojo.errors.exceptions import SemanticError

from automojo.pychestrate.webservice.identity.flags import flag_evaluator, flag_service
from automojo.pychestrate.webservice.identity.flags.exceptions import FlagAlreadyExistsError
from automojo.pychestrate.webservice.identity.flags.models import FlagContext, FlagKind
from automojo.pychestrate.webservice.identity.flags.rules import MAX_BASIS_POINTS, compute_bucket, evaluate_rollout

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
    reset_phase1_runtime,
)


def test_compute_bucket_is_deterministic():
    """
    **Feature: 1-feature-flags**
    **Property: compute_bucket is stable across calls for the same inputs.**
    """
    a = compute_bucket(flag_key="auth.local_fallback_enabled", bucketing_key="user-123")
    b = compute_bucket(flag_key="auth.local_fallback_enabled", bucketing_key="user-123")
    testbase.assert_equal(a, b)
    testbase.assert_equal(0 <= a < MAX_BASIS_POINTS, True)
    return


def test_compute_bucket_differs_for_different_keys():
    """
    **Feature: 1-feature-flags**
    **Property: The bucket varies across bucketing_keys for the same flag.**
    """
    a = compute_bucket(flag_key="experiment.foo", bucketing_key="user-1")
    b = compute_bucket(flag_key="experiment.foo", bucketing_key="user-2")
    testbase.assert_equal(a != b, True)
    return


def test_rollout_monotone_zero_and_full():
    """
    **Feature: 1-feature-flags**
    **Property: 0% rollout denies all; 10000 bp rollout allows all.**
    """
    ctx = FlagContext(bucketing_key="anything", user_id=None, project_id=None, attributes=())

    testbase.assert_equal(
        evaluate_rollout(flag_key="experiment.foo", context=ctx, rollout_percentage_bp=0),
        False,
    )
    testbase.assert_equal(
        evaluate_rollout(flag_key="experiment.foo", context=ctx, rollout_percentage_bp=10000),
        True,
    )
    return


def test_create_and_evaluate_boolean_flag():
    """
    **Feature: 1-feature-flags**
    **Property: A BOOLEAN flag with default_value=True evaluates to True.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()

    flag = flag_service.create_flag(
        db_session=session,
        flag_key="auth.local_fallback_enabled",
        flag_kind=FlagKind.BOOLEAN,
        default_value=True,
        rules=None,
        actor_user_id=None,
    )
    testbase.assert_equal(flag.flag_key, "auth.local_fallback_enabled")

    ctx = FlagContext(bucketing_key="user-1", user_id=None, project_id=None, attributes=())
    value = flag_evaluator.evaluate_boolean(
        db_session=session,
        flag_key="auth.local_fallback_enabled",
        context=ctx,
        default=False,
    )
    testbase.assert_equal(value, True)
    return


def test_evaluate_unknown_flag_returns_default():
    """
    **Feature: 1-feature-flags**
    **Property: An unknown flag_key returns the supplied default.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()

    ctx = FlagContext(bucketing_key="user-1", user_id=None, project_id=None, attributes=())
    value = flag_evaluator.evaluate_flag(
        db_session=session,
        flag_key="does.not.exist",
        context=ctx,
        default="fallback",
    )
    testbase.assert_equal(value, "fallback")
    return


def test_evaluate_missing_bucketing_key_raises_semantic_error():
    """
    **Feature: 1-feature-flags**
    **Property: Missing or empty bucketing_key raises SemanticError.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()

    ctx = FlagContext(bucketing_key="", user_id=None, project_id=None, attributes=())
    raised = False
    try:
        flag_evaluator.evaluate_flag(
            db_session=session,
            flag_key="auth.local_fallback_enabled",
            context=ctx,
            default=False,
        )
    except SemanticError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_duplicate_flag_raises_already_exists():
    """
    **Feature: 1-feature-flags**
    **Property: create_flag on an existing key raises FlagAlreadyExistsError.**
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
        flag_service.create_flag(
            db_session=session,
            flag_key="experiment.alpha",
            flag_kind=FlagKind.BOOLEAN,
            default_value=False,
            rules=None,
            actor_user_id=None,
        )
    except FlagAlreadyExistsError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_percentage_flag_decision_matches_bucket_cutoff():
    """
    **Feature: 1-feature-flags**
    **Property: A PERCENTAGE flag returns True exactly when the
    context's bucket falls below rollout_percentage_bp.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()

    flag_service.create_flag(
        db_session=session,
        flag_key="experiment.percent",
        flag_kind=FlagKind.PERCENTAGE,
        default_value=False,
        rules={"rollout_percentage_bp": 5000},
        actor_user_id=None,
    )

    ctx = FlagContext(bucketing_key="stable-key-42", user_id=None, project_id=None, attributes=())
    bucket = compute_bucket(flag_key="experiment.percent", bucketing_key=ctx.bucketing_key)
    expected = bucket < 5000

    actual = flag_evaluator.evaluate_flag(
        db_session=session,
        flag_key="experiment.percent",
        context=ctx,
        default=None,
    )
    testbase.assert_equal(actual, expected)
    return
