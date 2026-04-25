"""
.. module:: test_p4a_resource_inventory_pools_m1
    :synopsis: Tests for P4a — 4-resource-inventory + 4-resource-pools M1.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import List

from automojo import testbase

from automojo.pychestrate.core.defaults import new_uuid

from automojo.errors.exceptions import SemanticError

from automojo.pychestrate.webservice.extensions.registry import (
    reset_registry_for_testing,
)
from automojo.pychestrate.webservice.messaging.event_bus import (
    EntityEvent,
    reset_for_testing as reset_event_bus,
    subscribe,
)
from automojo.pychestrate.webservice.resources.inventory import (
    DeviceResourceKind,
    ResourceEventTopics,
    ResourceIdentityConflictError,
    ResourceKindUnknownError,
    ResourceNotFoundError,
    ResourceState,
    get_resource,
    list_resources,
    register_builtin_extensions as inventory_register,
    register_resource,
    transition_state,
)
from automojo.pychestrate.webservice.resources.inventory.errors import (
    ResourceStateTransitionError,
)
from automojo.pychestrate.webservice.resources.pools import (
    AllocationAspects,
    PoolEmptyError,
    PoolEventTopics,
    PoolMemberConflictError,
    PoolNotFoundError,
    add_member,
    create_pool,
    get_pool,
    list_pools,
    pick_candidate,
    remove_member,
)

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
)


PROJECT_UUID = "00000000-0000-4000-8000-0000000000a4"


def _prepare_runtime() -> None:
    """
        Reset cross-test globals + register the in-tree
        :class:`DeviceResourceKind`.
    """
    reset_registry_for_testing()
    reset_event_bus()
    inventory_register()
    return


# -----------------------------
# 4-resource-inventory tests
# -----------------------------

def test_register_resource_persists_and_emits():
    """
    **Feature: 4-resource-inventory (M1)**
    **Property: register_resource normalizes attributes via the
    DeviceResourceKind, persists a row in AVAILABLE, emits
    entity.resource.registered.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=ResourceEventTopics.REGISTERED,
        subscriber=lambda e: received.append(e),
    )

    view = register_resource(
        db_session=session,
        project_id=PROJECT_UUID,
        kind="device",
        display_name="Smoke Lab Box",
        attributes={
            "hostname": "  smoke-lab-01  ",
            "mac_address": "00:11:22:33:44:55",
            "vendor": "ACME",
        },
        description="single-host smoke lab",
        tags=("lab", "us-west"),
    )
    testbase.assert_equal(view.kind, "device")
    testbase.assert_equal(view.state, ResourceState.AVAILABLE)
    # Hostname trimmed by normalize.
    testbase.assert_equal(view.attributes["hostname"], "smoke-lab-01")
    testbase.assert_equal(len(view.identity_hash), 64)
    testbase.assert_equal(len(received), 1)
    return


def test_register_duplicate_identity_raises():
    """
    **Feature: 4-resource-inventory (M1)**
    **Property: registering a second device with the same
    (hostname, mac_address) tuple raises
    ResourceIdentityConflictError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    register_resource(
        db_session=session,
        project_id=PROJECT_UUID,
        kind="device",
        display_name="Box",
        attributes={
            "hostname": "host-a",
            "mac_address": "aa:bb:cc:dd:ee:ff",
        },
    )
    raised = False
    try:
        register_resource(
            db_session=session,
            project_id=PROJECT_UUID,
            kind="device",
            display_name="Box dup",
            attributes={
                "hostname": "host-a",
                "mac_address": "aa:bb:cc:dd:ee:ff",
            },
        )
    except ResourceIdentityConflictError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_register_unknown_kind_raises():
    """
    **Feature: 4-resource-inventory (M1)**
    **Property: a kind that has no registered protocol impl
    raises ResourceKindUnknownError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    raised = False
    try:
        register_resource(
            db_session=session,
            project_id=PROJECT_UUID,
            kind="alien-fake-kind",
            display_name="x",
            attributes={"hostname": "h"},
        )
    except ResourceKindUnknownError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_device_kind_rejects_unknown_attribute_keys():
    """
    **Feature: 4-resource-inventory (M1)**
    **Property: DeviceResourceKind.normalize raises SemanticError
    when caller supplies an unknown attribute key.**
    """
    _prepare_runtime()
    raised = False
    try:
        DeviceResourceKind.normalize(
            attributes={"hostname": "h", "made_up_key": "x"},
        )
    except SemanticError as xcpt:
        raised = True
        testbase.assert_equal("made_up_key" in str(xcpt), True)
    testbase.assert_equal(raised, True)
    return


def test_transition_state_walks_lifecycle_and_emits_topics():
    """
    **Feature: 4-resource-inventory (M1)**
    **Property: AVAILABLE → QUARANTINED → AVAILABLE → RETIRED
    walks the permitted-edge set; each step emits state_changed
    plus the appropriate domain topic.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    view = register_resource(
        db_session=session,
        project_id=PROJECT_UUID,
        kind="device",
        display_name="Lifecycle Lab",
        attributes={"hostname": "lifecycle-1"},
    )

    received_quar: List[EntityEvent] = []
    received_unquar: List[EntityEvent] = []
    received_retired: List[EntityEvent] = []
    subscribe(
        topic=ResourceEventTopics.QUARANTINED,
        subscriber=lambda e: received_quar.append(e),
    )
    subscribe(
        topic=ResourceEventTopics.UNQUARANTINED,
        subscriber=lambda e: received_unquar.append(e),
    )
    subscribe(
        topic=ResourceEventTopics.RETIRED,
        subscriber=lambda e: received_retired.append(e),
    )

    snap = transition_state(
        db_session=session, resource_id=view.resource_id,
        new_state=ResourceState.QUARANTINED,
    )
    testbase.assert_equal(snap.state, ResourceState.QUARANTINED)
    testbase.assert_equal(len(received_quar), 1)

    snap = transition_state(
        db_session=session, resource_id=view.resource_id,
        new_state=ResourceState.AVAILABLE,
    )
    testbase.assert_equal(snap.state, ResourceState.AVAILABLE)
    testbase.assert_equal(len(received_unquar), 1)

    snap = transition_state(
        db_session=session, resource_id=view.resource_id,
        new_state=ResourceState.RETIRED,
    )
    testbase.assert_equal(snap.state, ResourceState.RETIRED)
    testbase.assert_equal(len(received_retired), 1)

    # Retired resources are excluded from the default listing.
    visible = list_resources(db_session=session, project_id=PROJECT_UUID)
    testbase.assert_equal(len(visible), 0)
    full = list_resources(
        db_session=session, project_id=PROJECT_UUID, include_retired=True,
    )
    testbase.assert_equal(len(full), 1)
    return


def test_transition_state_rejects_illegal_edge():
    """
    **Feature: 4-resource-inventory (M1)**
    **Property: transitioning from RETIRED raises
    ResourceStateTransitionError (terminal state).**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    view = register_resource(
        db_session=session,
        project_id=PROJECT_UUID,
        kind="device",
        display_name="r",
        attributes={"hostname": "h"},
    )
    transition_state(
        db_session=session, resource_id=view.resource_id,
        new_state=ResourceState.RETIRED,
    )
    raised = False
    try:
        transition_state(
            db_session=session, resource_id=view.resource_id,
            new_state=ResourceState.AVAILABLE,
        )
    except ResourceStateTransitionError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_get_resource_unknown_raises():
    """
    **Feature: 4-resource-inventory (M1)**
    **Property: get_resource on an unknown id raises
    ResourceNotFoundError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    raised = False
    try:
        get_resource(db_session=session, resource_id=new_uuid())
    except ResourceNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return


# -----------------------------
# 4-resource-pools tests
# -----------------------------

def test_pool_create_and_list_with_members():
    """
    **Feature: 4-resource-pools (M1)**
    **Property: create_pool persists; add_member is idempotent;
    member_count reflects current rows.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received_created: List[EntityEvent] = []
    received_added: List[EntityEvent] = []
    subscribe(
        topic=PoolEventTopics.CREATED,
        subscriber=lambda e: received_created.append(e),
    )
    subscribe(
        topic=PoolEventTopics.MEMBER_ADDED,
        subscriber=lambda e: received_added.append(e),
    )

    res_a = register_resource(
        db_session=session, project_id=PROJECT_UUID, kind="device",
        display_name="A", attributes={"hostname": "host-a"},
    )
    res_b = register_resource(
        db_session=session, project_id=PROJECT_UUID, kind="device",
        display_name="B", attributes={"hostname": "host-b"},
    )

    pool = create_pool(
        db_session=session, project_id=PROJECT_UUID,
        name="lab-west",
        capability_tags=("linux", "x86_64"),
    )
    testbase.assert_equal(pool.member_count, 0)
    testbase.assert_equal(len(received_created), 1)

    add_member(db_session=session, pool_id=pool.pool_id, resource_id=res_a.resource_id)
    add_member(db_session=session, pool_id=pool.pool_id, resource_id=res_a.resource_id)  # idempotent
    add_member(db_session=session, pool_id=pool.pool_id, resource_id=res_b.resource_id)

    refreshed = get_pool(db_session=session, pool_id=pool.pool_id)
    testbase.assert_equal(refreshed.member_count, 2)
    testbase.assert_equal(len(received_added), 2)  # 2 unique adds
    return


def test_pool_create_duplicate_name_raises():
    """
    **Feature: 4-resource-pools (M1)**
    **Property: create_pool with the same (project, name) raises
    PoolMemberConflictError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    create_pool(db_session=session, project_id=PROJECT_UUID, name="dup")
    raised = False
    try:
        create_pool(db_session=session, project_id=PROJECT_UUID, name="dup")
    except PoolMemberConflictError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_pick_candidate_returns_fifo_eligible_member():
    """
    **Feature: 4-resource-pools (M1)**
    **Property: pick_candidate returns the earliest-added member
    whose underlying resource is AVAILABLE; quarantined members
    are skipped; preferred_member short-circuits when eligible.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    res_a = register_resource(
        db_session=session, project_id=PROJECT_UUID, kind="device",
        display_name="A", attributes={"hostname": "fifo-a"},
    )
    res_b = register_resource(
        db_session=session, project_id=PROJECT_UUID, kind="device",
        display_name="B", attributes={"hostname": "fifo-b"},
    )
    res_c = register_resource(
        db_session=session, project_id=PROJECT_UUID, kind="device",
        display_name="C", attributes={"hostname": "fifo-c"},
    )

    pool = create_pool(db_session=session, project_id=PROJECT_UUID, name="fifo")
    add_member(db_session=session, pool_id=pool.pool_id, resource_id=res_a.resource_id)
    add_member(db_session=session, pool_id=pool.pool_id, resource_id=res_b.resource_id)
    add_member(db_session=session, pool_id=pool.pool_id, resource_id=res_c.resource_id)

    # FIFO picks res_a first.
    chosen = pick_candidate(db_session=session, pool_id=pool.pool_id)
    testbase.assert_equal(chosen.resource_id, res_a.resource_id)

    # preferred_member short-circuits when eligible.
    chosen = pick_candidate(
        db_session=session, pool_id=pool.pool_id,
        aspects=AllocationAspects(preferred_member=res_c.resource_id),
    )
    testbase.assert_equal(chosen.resource_id, res_c.resource_id)

    # Quarantine res_a and re-pick — FIFO now returns res_b.
    transition_state(
        db_session=session, resource_id=res_a.resource_id,
        new_state=ResourceState.QUARANTINED,
    )
    chosen = pick_candidate(db_session=session, pool_id=pool.pool_id)
    testbase.assert_equal(chosen.resource_id, res_b.resource_id)
    return


def test_pick_candidate_empty_pool_raises():
    """
    **Feature: 4-resource-pools (M1)**
    **Property: pick_candidate against a pool with no members
    raises PoolEmptyError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    pool = create_pool(db_session=session, project_id=PROJECT_UUID, name="empty")
    raised = False
    try:
        pick_candidate(db_session=session, pool_id=pool.pool_id)
    except PoolEmptyError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_pick_candidate_all_quarantined_raises_empty():
    """
    **Feature: 4-resource-pools (M1)**
    **Property: pick_candidate raises PoolEmptyError when every
    member is in a non-AVAILABLE state.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    res = register_resource(
        db_session=session, project_id=PROJECT_UUID, kind="device",
        display_name="Q", attributes={"hostname": "q-1"},
    )
    transition_state(
        db_session=session, resource_id=res.resource_id,
        new_state=ResourceState.QUARANTINED,
    )
    pool = create_pool(db_session=session, project_id=PROJECT_UUID, name="all-q")
    add_member(db_session=session, pool_id=pool.pool_id, resource_id=res.resource_id)
    raised = False
    try:
        pick_candidate(db_session=session, pool_id=pool.pool_id)
    except PoolEmptyError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_remove_member_idempotent():
    """
    **Feature: 4-resource-pools (M1)**
    **Property: remove_member is idempotent on missing
    membership.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    pool = create_pool(db_session=session, project_id=PROJECT_UUID, name="rem")
    res = register_resource(
        db_session=session, project_id=PROJECT_UUID, kind="device",
        display_name="X", attributes={"hostname": "x"},
    )
    add_member(db_session=session, pool_id=pool.pool_id, resource_id=res.resource_id)
    remove_member(db_session=session, pool_id=pool.pool_id, resource_id=res.resource_id)
    # Idempotent — second call is a no-op.
    remove_member(db_session=session, pool_id=pool.pool_id, resource_id=res.resource_id)
    refreshed = get_pool(db_session=session, pool_id=pool.pool_id)
    testbase.assert_equal(refreshed.member_count, 0)
    return
