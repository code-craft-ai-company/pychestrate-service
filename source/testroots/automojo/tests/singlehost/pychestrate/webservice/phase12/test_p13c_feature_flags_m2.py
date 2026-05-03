"""
.. module:: test_p13c_feature_flags_m2
    :synopsis: Tests for P13c — 1-feature-flags M2.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime, timedelta, timezone
from typing import List

from automojo import testbase

from automojo.errors.exceptions import SemanticError

from automojo.pychestrate.webservice.identity.flags import flag_service
from automojo.pychestrate.webservice.identity.flags.events import (
    FlagEventTopics,
)
from automojo.pychestrate.webservice.identity.flags.exceptions import (
    FlagAlreadyRetiredError,
    FlagKindImmutableError,
    FlagNotFoundError,
    FlagValueInvalidError,
)
from automojo.pychestrate.webservice.identity.flags.models import (
    FeatureFlag,
    FeatureFlagVersion,
    FlagKind,
    FlagState,
)
from automojo.pychestrate.webservice.messaging.event_bus import (
    EntityEvent,
    subscribe,
)

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
    reset_phase1_runtime,
)


def _setup() -> tuple:
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()
    return (session,)


# -------------------------------------
# validate_value_for_kind
# -------------------------------------

def test_validate_boolean_kind_rejects_non_bool():
    """
    **Feature: 1-feature-flags (M2)**
    **Property: a BOOLEAN flag's value must be a Python bool.**
    """
    raised = False
    try:
        flag_service.validate_value_for_kind(
            flag_kind=FlagKind.BOOLEAN, value="true",
        )
    except FlagValueInvalidError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_validate_string_kind_rejects_int():
    """
    **Feature: 1-feature-flags (M2)**
    **Property: a STRING flag's value must be a Python str.**
    """
    raised = False
    try:
        flag_service.validate_value_for_kind(
            flag_kind=FlagKind.STRING, value=42,
        )
    except FlagValueInvalidError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_validate_enum_kind_requires_choices_in_rules():
    """
    **Feature: 1-feature-flags (M2)**
    **Property: an ENUM flag's rules must declare a non-empty
    'choices' list.**
    """
    raised = False
    try:
        flag_service.validate_value_for_kind(
            flag_kind=FlagKind.ENUM, value="canary", rules={},
        )
    except FlagValueInvalidError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_validate_enum_kind_rejects_value_outside_choices():
    """
    **Feature: 1-feature-flags (M2)**
    **Property: an ENUM flag value not in the choices set
    raises FlagValueInvalidError.**
    """
    raised = False
    try:
        flag_service.validate_value_for_kind(
            flag_kind=FlagKind.ENUM,
            value="ghost",
            rules={"choices": ["canary", "stable", "beta"]},
        )
    except FlagValueInvalidError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_validate_percentage_kind_requires_bool_default():
    """
    **Feature: 1-feature-flags (M2)**
    **Property: a PERCENTAGE flag's default_value must be a
    bool — the percentage cutoff lives in
    rules['rollout_percentage_bp'].**
    """
    raised = False
    try:
        flag_service.validate_value_for_kind(
            flag_kind=FlagKind.PERCENTAGE, value=50,
        )
    except FlagValueInvalidError:
        raised = True
    testbase.assert_equal(raised, True)
    # bool default is accepted.
    flag_service.validate_value_for_kind(
        flag_kind=FlagKind.PERCENTAGE, value=True,
    )
    return


def test_validate_percentage_kind_validates_rollout_percentage_bp():
    """
    **Feature: 1-feature-flags (M2)**
    **Property: rollout_percentage_bp must be an integer in
    [0, 10000].**
    """
    raised_low = False
    try:
        flag_service.validate_value_for_kind(
            flag_kind=FlagKind.PERCENTAGE,
            value=False,
            rules={"rollout_percentage_bp": -1},
        )
    except FlagValueInvalidError:
        raised_low = True
    raised_high = False
    try:
        flag_service.validate_value_for_kind(
            flag_kind=FlagKind.PERCENTAGE,
            value=False,
            rules={"rollout_percentage_bp": 10001},
        )
    except FlagValueInvalidError:
        raised_high = True
    testbase.assert_equal(raised_low, True)
    testbase.assert_equal(raised_high, True)
    # Boundary values are accepted.
    flag_service.validate_value_for_kind(
        flag_kind=FlagKind.PERCENTAGE,
        value=False,
        rules={"rollout_percentage_bp": 0},
    )
    flag_service.validate_value_for_kind(
        flag_kind=FlagKind.PERCENTAGE,
        value=False,
        rules={"rollout_percentage_bp": 10000},
    )
    return


# -------------------------------------
# create_flag now validates value
# -------------------------------------

def test_create_flag_rejects_mismatched_default_value():
    """
    **Feature: 1-feature-flags (M2)**
    **Property: create_flag with a default_value that does
    not match flag_kind raises FlagValueInvalidError.**
    """
    (session,) = _setup()
    raised = False
    try:
        flag_service.create_flag(
            db_session=session,
            flag_key="bad.string.flag",
            flag_kind=FlagKind.STRING,
            default_value=42,
            rules=None,
            actor_user_id=None,
        )
    except FlagValueInvalidError:
        raised = True
    testbase.assert_equal(raised, True)
    return


# -------------------------------------
# update_flag_rules
# -------------------------------------

def test_update_flag_rules_bumps_version_and_emits():
    """
    **Feature: 1-feature-flags (M2)**
    **Property: update_flag_rules bumps current_version,
    inserts a new FeatureFlagVersion row, and emits
    FLAG_UPDATED.**
    """
    (session,) = _setup()
    received: List[EntityEvent] = []
    subscribe(
        topic=FlagEventTopics.FLAG_UPDATED,
        subscriber=lambda e: received.append(e),
    )
    flag_service.create_flag(
        db_session=session,
        flag_key="ops.bool.flag",
        flag_kind=FlagKind.BOOLEAN,
        default_value=False,
        rules=None,
        actor_user_id=None,
    )
    flag_service.update_flag_rules(
        db_session=session,
        flag_key="ops.bool.flag",
        default_value=True,
        rules={"sticky": True},
        actor_user_id=None,
    )
    refreshed = (
        session.query(FeatureFlag)
        .filter(FeatureFlag.flag_key == "ops.bool.flag")
        .first()
    )
    testbase.assert_equal(refreshed.current_version, 2)
    versions = (
        session.query(FeatureFlagVersion)
        .filter(FeatureFlagVersion.flag_key == "ops.bool.flag")
        .all()
    )
    testbase.assert_equal(len(versions), 2)
    testbase.assert_equal(len(received), 1)
    testbase.assert_equal(received[0].payload["version"], 2)
    return


def test_update_flag_rules_unknown_key_raises():
    """
    **Feature: 1-feature-flags (M2)**
    **Property: update_flag_rules on a missing flag_key
    raises FlagNotFoundError.**
    """
    (session,) = _setup()
    raised = False
    try:
        flag_service.update_flag_rules(
            db_session=session,
            flag_key="never.created",
            default_value=False,
            rules=None,
            actor_user_id=None,
        )
    except FlagNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_update_flag_rules_rejects_kind_change():
    """
    **Feature: 1-feature-flags (M2)**
    **Property: update_flag_rules with a flag_kind argument
    that does not match the persisted kind raises
    FlagKindImmutableError.**
    """
    (session,) = _setup()
    flag_service.create_flag(
        db_session=session,
        flag_key="ops.kind.swap",
        flag_kind=FlagKind.BOOLEAN,
        default_value=False,
        rules=None,
        actor_user_id=None,
    )
    raised = False
    try:
        flag_service.update_flag_rules(
            db_session=session,
            flag_key="ops.kind.swap",
            default_value="hello",
            rules=None,
            actor_user_id=None,
            flag_kind=FlagKind.STRING,
        )
    except FlagKindImmutableError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_update_flag_rules_validates_new_value_against_kind():
    """
    **Feature: 1-feature-flags (M2)**
    **Property: update_flag_rules with a default_value that
    does not match the persisted kind raises
    FlagValueInvalidError.**
    """
    (session,) = _setup()
    flag_service.create_flag(
        db_session=session,
        flag_key="ops.val.mismatch",
        flag_kind=FlagKind.STRING,
        default_value="initial",
        rules=None,
        actor_user_id=None,
    )
    raised = False
    try:
        flag_service.update_flag_rules(
            db_session=session,
            flag_key="ops.val.mismatch",
            default_value=42,
            rules=None,
            actor_user_id=None,
        )
    except FlagValueInvalidError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_update_flag_rules_rejects_non_active_flag():
    """
    **Feature: 1-feature-flags (M2)**
    **Property: update_flag_rules on a RETIRED flag raises
    SemanticError.**
    """
    (session,) = _setup()
    flag_service.create_flag(
        db_session=session,
        flag_key="ops.retired.flag",
        flag_kind=FlagKind.BOOLEAN,
        default_value=False,
        rules=None,
        actor_user_id=None,
    )
    flag_service.retire_flag(
        db_session=session,
        flag_key="ops.retired.flag",
        actor_user_id=None,
    )
    raised = False
    try:
        flag_service.update_flag_rules(
            db_session=session,
            flag_key="ops.retired.flag",
            default_value=True,
            rules=None,
            actor_user_id=None,
        )
    except SemanticError:
        raised = True
    testbase.assert_equal(raised, True)
    return


# -------------------------------------
# retire_flag
# -------------------------------------

def test_retire_flag_flips_state_and_emits():
    """
    **Feature: 1-feature-flags (M2)**
    **Property: retire_flag flips state to RETIRED, stamps
    retired_at + grace_expires_at, and emits FLAG_RETIRED.**
    """
    (session,) = _setup()
    received: List[EntityEvent] = []
    subscribe(
        topic=FlagEventTopics.FLAG_RETIRED,
        subscriber=lambda e: received.append(e),
    )
    flag_service.create_flag(
        db_session=session,
        flag_key="ops.retire.target",
        flag_kind=FlagKind.BOOLEAN,
        default_value=False,
        rules=None,
        actor_user_id=None,
    )
    flag = flag_service.retire_flag(
        db_session=session,
        flag_key="ops.retire.target",
        actor_user_id=None,
    )
    testbase.assert_equal(flag.state, FlagState.RETIRED)
    testbase.assert_equal(flag.retired_at is not None, True)
    testbase.assert_equal(flag.grace_expires_at is not None, True)
    testbase.assert_equal(len(received), 1)
    return


def test_retire_flag_already_retired_raises():
    """
    **Feature: 1-feature-flags (M2)**
    **Property: retiring an already-retired flag raises
    FlagAlreadyRetiredError.**
    """
    (session,) = _setup()
    flag_service.create_flag(
        db_session=session,
        flag_key="ops.retire.dup",
        flag_kind=FlagKind.BOOLEAN,
        default_value=False,
        rules=None,
        actor_user_id=None,
    )
    flag_service.retire_flag(
        db_session=session,
        flag_key="ops.retire.dup",
        actor_user_id=None,
    )
    raised = False
    try:
        flag_service.retire_flag(
            db_session=session,
            flag_key="ops.retire.dup",
            actor_user_id=None,
        )
    except FlagAlreadyRetiredError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_retire_flag_unknown_key_raises():
    """
    **Feature: 1-feature-flags (M2)**
    **Property: retiring an unknown flag raises
    FlagNotFoundError.**
    """
    (session,) = _setup()
    raised = False
    try:
        flag_service.retire_flag(
            db_session=session,
            flag_key="never.created",
            actor_user_id=None,
        )
    except FlagNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return


# -------------------------------------
# remove_flag
# -------------------------------------

def test_remove_flag_requires_retire_first():
    """
    **Feature: 1-feature-flags (M2)**
    **Property: remove_flag against an ACTIVE flag raises
    SemanticError.**
    """
    (session,) = _setup()
    flag_service.create_flag(
        db_session=session,
        flag_key="ops.active.remove",
        flag_kind=FlagKind.BOOLEAN,
        default_value=False,
        rules=None,
        actor_user_id=None,
    )
    raised = False
    try:
        flag_service.remove_flag(
            db_session=session,
            flag_key="ops.active.remove",
            actor_user_id=None,
        )
    except SemanticError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_remove_flag_blocked_inside_grace_window():
    """
    **Feature: 1-feature-flags (M2)**
    **Property: remove_flag inside the grace window raises
    SemanticError; force=True bypasses.**
    """
    (session,) = _setup()
    flag_service.create_flag(
        db_session=session,
        flag_key="ops.grace.respect",
        flag_kind=FlagKind.BOOLEAN,
        default_value=False,
        rules=None,
        actor_user_id=None,
    )
    flag_service.retire_flag(
        db_session=session,
        flag_key="ops.grace.respect",
        actor_user_id=None,
        grace_period=timedelta(days=14),
    )
    raised = False
    try:
        flag_service.remove_flag(
            db_session=session,
            flag_key="ops.grace.respect",
            actor_user_id=None,
        )
    except SemanticError:
        raised = True
    testbase.assert_equal(raised, True)

    # Force bypasses and emits FLAG_REMOVED.
    received: List[EntityEvent] = []
    subscribe(
        topic=FlagEventTopics.FLAG_REMOVED,
        subscriber=lambda e: received.append(e),
    )
    flag_service.remove_flag(
        db_session=session,
        flag_key="ops.grace.respect",
        actor_user_id=None,
        force=True,
    )
    testbase.assert_equal(len(received), 1)
    refreshed = (
        session.query(FeatureFlag)
        .filter(FeatureFlag.flag_key == "ops.grace.respect")
        .first()
    )
    testbase.assert_equal(refreshed, None)
    return


def test_remove_flag_after_grace_window_succeeds():
    """
    **Feature: 1-feature-flags (M2)**
    **Property: remove_flag past the grace deadline removes
    the row and emits FLAG_REMOVED.**
    """
    (session,) = _setup()
    flag_service.create_flag(
        db_session=session,
        flag_key="ops.grace.elapsed",
        flag_kind=FlagKind.BOOLEAN,
        default_value=False,
        rules=None,
        actor_user_id=None,
    )
    flag_service.retire_flag(
        db_session=session,
        flag_key="ops.grace.elapsed",
        actor_user_id=None,
        grace_period=timedelta(days=14),
    )
    future = datetime.now(tz=timezone.utc) + timedelta(days=30)
    flag_service.remove_flag(
        db_session=session,
        flag_key="ops.grace.elapsed",
        actor_user_id=None,
        now=future,
    )
    refreshed = (
        session.query(FeatureFlag)
        .filter(FeatureFlag.flag_key == "ops.grace.elapsed")
        .first()
    )
    testbase.assert_equal(refreshed, None)
    return


# -------------------------------------
# sweep_retired_flags
# -------------------------------------

def test_sweep_retired_flags_removes_past_grace_rows_only():
    """
    **Feature: 1-feature-flags (M2)**
    **Property: sweep_retired_flags removes RETIRED rows
    whose grace_expires_at is in the past, leaves rows still
    in their grace window untouched, and ignores ACTIVE
    flags.**
    """
    (session,) = _setup()
    flag_service.create_flag(
        db_session=session,
        flag_key="ops.sweep.fresh",
        flag_kind=FlagKind.BOOLEAN,
        default_value=False,
        rules=None,
        actor_user_id=None,
    )
    flag_service.retire_flag(
        db_session=session,
        flag_key="ops.sweep.fresh",
        actor_user_id=None,
        grace_period=timedelta(days=14),
    )
    flag_service.create_flag(
        db_session=session,
        flag_key="ops.sweep.elapsed",
        flag_kind=FlagKind.BOOLEAN,
        default_value=False,
        rules=None,
        actor_user_id=None,
    )
    flag_service.retire_flag(
        db_session=session,
        flag_key="ops.sweep.elapsed",
        actor_user_id=None,
        grace_period=timedelta(days=14),
    )
    flag_service.create_flag(
        db_session=session,
        flag_key="ops.sweep.active",
        flag_kind=FlagKind.BOOLEAN,
        default_value=False,
        rules=None,
        actor_user_id=None,
    )
    future = datetime.now(tz=timezone.utc) + timedelta(days=30)
    removed = flag_service.sweep_retired_flags(
        db_session=session, now=future,
    )
    testbase.assert_equal(removed, 2)
    survivors = sorted(
        f.flag_key for f in
        session.query(FeatureFlag).all()
    )
    testbase.assert_equal(survivors, ["ops.sweep.active"])
    return
