"""
.. module:: test_p7a_environment_registry_m1
    :synopsis: Tests for P7a — 6-environment-registry M1.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import List

from ccai import testbase

from ccai.pychestrate.core.defaults import new_uuid

from ccai.pychestrate.webservice.extensions.registry import (
    reset_registry_for_testing,
)
from ccai.pychestrate.webservice.messaging.event_bus import (
    EntityEvent,
    reset_for_testing as reset_event_bus,
    subscribe,
)
from ccai.pychestrate.webservice.orchestration.infra.environment import (
    EnvironmentAttrsInvalidError,
    EnvironmentDeclareInputs,
    EnvironmentEventTopics,
    EnvironmentKindUnknownError,
    EnvironmentNameConflictError,
    EnvironmentNotFoundError,
    EnvironmentState,
    EnvironmentStateError,
    archive_environment,
    declare_environment,
    freeze_environment,
    get_environment,
    list_environments,
    mark_destroyed,
    record_apply,
    register_builtin_extensions as environment_register,
    unfreeze_environment,
    update_attrs,
)

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
)


PROJECT_UUID = "00000000-0000-4000-8000-000000040001"
ACTOR_UUID = "00000000-0000-4000-8000-000000040002"
RUN_UUID = "00000000-0000-4000-8000-000000040003"


def _prepare_runtime() -> None:
    reset_registry_for_testing()
    reset_event_bus()
    environment_register()
    return


def _valid_k8s_inputs(*, name: str = "prod-east") -> EnvironmentDeclareInputs:
    rtnval = EnvironmentDeclareInputs(
        name=name,
        kind_name="k8s-cluster",
        attrs={
            "cluster_id": "cluster-001",
            "region": "us-east-1",
            "api_endpoint": "https://api.cluster-001.example.com",
            "node_pool_count": 3,
            "capability_tags": ["gpu", "linux"],
        },
    )
    return rtnval


# -------------------------------------
# declare_environment
# -------------------------------------

def test_declare_persists_and_emits():
    """
    **Feature: 6-environment-registry (M1)**
    **Property: declare_environment persists an Environment in
    ACTIVE + appends a DECLARED ledger row + emits
    entity.environment.declared.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=EnvironmentEventTopics.DECLARED,
        subscriber=lambda e: received.append(e),
    )
    view = declare_environment(
        db_session=session, project_id=PROJECT_UUID,
        inputs=_valid_k8s_inputs(),
        actor_id=ACTOR_UUID,
    )
    testbase.assert_equal(view.state, EnvironmentState.ACTIVE)
    testbase.assert_equal(view.kind_name, "k8s-cluster")
    testbase.assert_equal(view.attrs["cluster_id"], "cluster-001")
    testbase.assert_equal(len(received), 1)
    return


def test_declare_unknown_kind_raises():
    """
    **Feature: 6-environment-registry (M1)**
    **Property: an unknown kind_name raises
    EnvironmentKindUnknownError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    bad = EnvironmentDeclareInputs(
        name="x", kind_name="unknown-kind", attrs={},
    )
    raised = False
    try:
        declare_environment(
            db_session=session, project_id=PROJECT_UUID, inputs=bad,
        )
    except EnvironmentKindUnknownError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_declare_invalid_attrs_aggregates_issues():
    """
    **Feature: 6-environment-registry (M1)**
    **Property: invalid attrs raise EnvironmentAttrsInvalidError
    listing every issue.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    bad = EnvironmentDeclareInputs(
        name="bad",
        kind_name="k8s-cluster",
        attrs={
            # missing cluster_id, region
            "api_endpoint": "ftp://nope",
            "node_pool_count": -3,
            "capability_tags": [""],
        },
    )
    raised = False
    try:
        declare_environment(
            db_session=session, project_id=PROJECT_UUID, inputs=bad,
        )
    except EnvironmentAttrsInvalidError as xcpt:
        raised = True
        msg = str(xcpt)
        testbase.assert_equal("cluster_id" in msg, True)
        testbase.assert_equal("region" in msg, True)
        testbase.assert_equal("api_endpoint" in msg, True)
        testbase.assert_equal("node_pool_count" in msg, True)
    testbase.assert_equal(raised, True)
    return


def test_declare_duplicate_name_raises():
    """
    **Feature: 6-environment-registry (M1)**
    **Property: a second declare with the same (project, kind,
    name) raises EnvironmentNameConflictError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    declare_environment(
        db_session=session, project_id=PROJECT_UUID,
        inputs=_valid_k8s_inputs(name="dup"),
    )
    raised = False
    try:
        declare_environment(
            db_session=session, project_id=PROJECT_UUID,
            inputs=_valid_k8s_inputs(name="dup"),
        )
    except EnvironmentNameConflictError:
        raised = True
    testbase.assert_equal(raised, True)
    return


# -------------------------------------
# update_attrs
# -------------------------------------

def test_update_attrs_persists_and_emits():
    """
    **Feature: 6-environment-registry (M1)**
    **Property: update_attrs re-validates against the kind +
    persists new attrs + emits UPDATED.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=EnvironmentEventTopics.UPDATED,
        subscriber=lambda e: received.append(e),
    )
    view = declare_environment(
        db_session=session, project_id=PROJECT_UUID,
        inputs=_valid_k8s_inputs(),
    )
    new_attrs = dict(view.attrs)
    new_attrs["node_pool_count"] = 6
    updated = update_attrs(
        db_session=session, environment_id=view.environment_id,
        new_attrs=new_attrs, actor_id=ACTOR_UUID,
    )
    testbase.assert_equal(updated.attrs["node_pool_count"], 6)
    testbase.assert_equal(len(received), 1)
    return


def test_update_attrs_invalid_raises():
    """
    **Feature: 6-environment-registry (M1)**
    **Property: updates that fail kind validation raise
    EnvironmentAttrsInvalidError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    view = declare_environment(
        db_session=session, project_id=PROJECT_UUID,
        inputs=_valid_k8s_inputs(),
    )
    raised = False
    try:
        update_attrs(
            db_session=session, environment_id=view.environment_id,
            new_attrs={"cluster_id": "", "region": "us", "api_endpoint": "x"},
        )
    except EnvironmentAttrsInvalidError:
        raised = True
    testbase.assert_equal(raised, True)
    return


# -------------------------------------
# freeze / unfreeze
# -------------------------------------

def test_freeze_unfreeze_round_trip_with_emits():
    """
    **Feature: 6-environment-registry (M1)**
    **Property: freeze flips ACTIVE → FROZEN + records actor +
    reason + emits FROZEN; unfreeze flips back + emits
    UNFROZEN.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received_frozen: List[EntityEvent] = []
    received_unfrozen: List[EntityEvent] = []
    subscribe(
        topic=EnvironmentEventTopics.FROZEN,
        subscriber=lambda e: received_frozen.append(e),
    )
    subscribe(
        topic=EnvironmentEventTopics.UNFROZEN,
        subscriber=lambda e: received_unfrozen.append(e),
    )
    view = declare_environment(
        db_session=session, project_id=PROJECT_UUID,
        inputs=_valid_k8s_inputs(),
    )
    frozen = freeze_environment(
        db_session=session, environment_id=view.environment_id,
        reason="security review", actor_id=ACTOR_UUID,
    )
    testbase.assert_equal(frozen.state, EnvironmentState.FROZEN)
    testbase.assert_equal(frozen.frozen_by, ACTOR_UUID)
    testbase.assert_equal(frozen.frozen_reason, "security review")

    unfrozen = unfreeze_environment(
        db_session=session, environment_id=view.environment_id,
        reason="cleared", actor_id=ACTOR_UUID,
    )
    testbase.assert_equal(unfrozen.state, EnvironmentState.ACTIVE)
    testbase.assert_equal(unfrozen.frozen_by is None, True)
    testbase.assert_equal(len(received_frozen), 1)
    testbase.assert_equal(len(received_unfrozen), 1)
    return


def test_freeze_idempotent_on_already_frozen():
    """
    **Feature: 6-environment-registry (M1)**
    **Property: freeze on an already-frozen env is a no-op (no
    second event).**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=EnvironmentEventTopics.FROZEN,
        subscriber=lambda e: received.append(e),
    )
    view = declare_environment(
        db_session=session, project_id=PROJECT_UUID,
        inputs=_valid_k8s_inputs(),
    )
    freeze_environment(
        db_session=session, environment_id=view.environment_id,
        reason="x",
    )
    freeze_environment(
        db_session=session, environment_id=view.environment_id,
        reason="y",
    )
    testbase.assert_equal(len(received), 1)
    return


# -------------------------------------
# archive / mark_destroyed
# -------------------------------------

def test_archive_emits_and_blocks_attr_updates():
    """
    **Feature: 6-environment-registry (M1)**
    **Property: archive emits ARCHIVED + subsequent
    update_attrs raises EnvironmentStateError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=EnvironmentEventTopics.ARCHIVED,
        subscriber=lambda e: received.append(e),
    )
    view = declare_environment(
        db_session=session, project_id=PROJECT_UUID,
        inputs=_valid_k8s_inputs(),
    )
    archived = archive_environment(
        db_session=session, environment_id=view.environment_id,
        reason="end of life",
    )
    testbase.assert_equal(archived.state, EnvironmentState.ARCHIVED)
    testbase.assert_equal(len(received), 1)

    raised = False
    try:
        update_attrs(
            db_session=session, environment_id=view.environment_id,
            new_attrs=dict(view.attrs),
        )
    except EnvironmentStateError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_archive_destroyed_env_raises():
    """
    **Feature: 6-environment-registry (M1)**
    **Property: archiving a DESTROYED env raises
    EnvironmentStateError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    view = declare_environment(
        db_session=session, project_id=PROJECT_UUID,
        inputs=_valid_k8s_inputs(),
    )
    mark_destroyed(
        db_session=session, environment_id=view.environment_id,
    )
    raised = False
    try:
        archive_environment(
            db_session=session, environment_id=view.environment_id,
            reason="oops",
        )
    except EnvironmentStateError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_mark_destroyed_emits_and_idempotent():
    """
    **Feature: 6-environment-registry (M1)**
    **Property: mark_destroyed emits DESTROYED on the first
    call; subsequent calls are no-ops.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=EnvironmentEventTopics.DESTROYED,
        subscriber=lambda e: received.append(e),
    )
    view = declare_environment(
        db_session=session, project_id=PROJECT_UUID,
        inputs=_valid_k8s_inputs(),
    )
    mark_destroyed(
        db_session=session, environment_id=view.environment_id,
        actor_id=ACTOR_UUID, run_id=RUN_UUID, reason="cleanup",
    )
    mark_destroyed(
        db_session=session, environment_id=view.environment_id,
    )
    testbase.assert_equal(len(received), 1)
    refreshed = get_environment(
        db_session=session, environment_id=view.environment_id,
    )
    testbase.assert_equal(refreshed.state, EnvironmentState.DESTROYED)
    return


# -------------------------------------
# record_apply
# -------------------------------------

def test_record_apply_stamps_run_id_digest_and_emits():
    """
    **Feature: 6-environment-registry (M1)**
    **Property: record_apply stamps last_applied_run_id +
    last_output_digest_sha256 + last_applied_at and emits
    APPLIED.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=EnvironmentEventTopics.APPLIED,
        subscriber=lambda e: received.append(e),
    )
    view = declare_environment(
        db_session=session, project_id=PROJECT_UUID,
        inputs=_valid_k8s_inputs(),
    )
    applied = record_apply(
        db_session=session, environment_id=view.environment_id,
        run_id=RUN_UUID, output_digest_sha256="a" * 64,
    )
    testbase.assert_equal(applied.last_applied_run_id, RUN_UUID)
    testbase.assert_equal(applied.last_output_digest_sha256, "a" * 64)
    testbase.assert_equal(applied.last_applied_at is not None, True)
    testbase.assert_equal(len(received), 1)
    return


def test_record_apply_against_archived_raises():
    """
    **Feature: 6-environment-registry (M1)**
    **Property: record_apply on an archived env raises
    EnvironmentStateError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    view = declare_environment(
        db_session=session, project_id=PROJECT_UUID,
        inputs=_valid_k8s_inputs(),
    )
    archive_environment(
        db_session=session, environment_id=view.environment_id,
        reason="x",
    )
    raised = False
    try:
        record_apply(
            db_session=session, environment_id=view.environment_id,
            run_id=RUN_UUID, output_digest_sha256="b" * 64,
        )
    except EnvironmentStateError:
        raised = True
    testbase.assert_equal(raised, True)
    return


# -------------------------------------
# read helpers
# -------------------------------------

def test_get_environment_unknown_raises():
    """
    **Feature: 6-environment-registry (M1)**
    **Property: get_environment on an unknown id raises
    EnvironmentNotFoundError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    raised = False
    try:
        get_environment(db_session=session, environment_id=new_uuid())
    except EnvironmentNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_list_environments_filters_by_kind_and_state():
    """
    **Feature: 6-environment-registry (M1)**
    **Property: list_environments scopes to project, optionally
    filters by kind and state.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    other_project = new_uuid()
    declare_environment(
        db_session=session, project_id=PROJECT_UUID,
        inputs=_valid_k8s_inputs(name="a"),
    )
    declare_environment(
        db_session=session, project_id=PROJECT_UUID,
        inputs=_valid_k8s_inputs(name="b"),
    )
    declare_environment(
        db_session=session, project_id=other_project,
        inputs=_valid_k8s_inputs(name="c"),
    )

    rows = list_environments(
        db_session=session, project_id=PROJECT_UUID,
    )
    testbase.assert_equal(len(rows), 2)

    rows_kind = list_environments(
        db_session=session, project_id=PROJECT_UUID,
        kind_name="k8s-cluster",
    )
    testbase.assert_equal(len(rows_kind), 2)

    # Archive one, filter by ARCHIVED.
    archive_environment(
        db_session=session, environment_id=rows[0].environment_id,
        reason="x",
    )
    rows_archived = list_environments(
        db_session=session, project_id=PROJECT_UUID,
        state=EnvironmentState.ARCHIVED,
    )
    testbase.assert_equal(len(rows_archived), 1)
    return
