"""
.. module:: test_resource_manager_server_side_rules
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Rules the resources forms state are enforced by the managers
               too (audit finding RES-24).

.. moduleauthor:: Code Craft AI LLC

The forms said pool names take only letters, digits, underscores and hyphens,
that a manual health status change needs a reason for the audit trail, and
the IP pool form took a CIDR; the server accepted "android phones", an empty
reason, and stored "10.50.0.5/29" as typed. The managers now enforce the
stated rules and store the canonical network.

**Feature: resources (RES-24 server-side validation)**
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import uuid

from typing import Any, Optional

import sqlalchemy as sa

from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from ccai import testbase

from ccai.pychestrate.core.managers.health_monitor import (
    TRIGGER_HEALTH_CHECK,
    HealthChangeReasonRequiredError,
    HealthMonitor,
)
from ccai.pychestrate.core.managers.ip_pool_manager import (
    CIDROverlapError,
    IPPoolCreateRequest,
    IPPoolManager,
    IPPoolUpdateRequest,
    IPPoolValidationError,
)
from ccai.pychestrate.core.managers.resource_manager import (
    ResourceManager,
    ResourcePoolCreateRequest,
    ResourceValidationError,
)
from ccai.pychestrate.core.orm import (
    HealthTransitionLog,
    PychestrateModelBase,
    Resource,
)


def _session() -> Any:
    engine = sa.create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False},
    )
    PychestrateModelBase.metadata.create_all(engine)
    rtnval = sessionmaker(bind=engine, expire_on_commit=False)()
    return rtnval


def _device(*, session: Any) -> int:
    resource = Resource(
        name="board-" + uuid.uuid4().hex[:6], resource_type="device", metadata_json={},
        sensitive_fields=[], capacity=1, health_status="online",
    )
    session.add(resource)
    session.commit()
    rtnval = resource.id
    return rtnval


def _error_code_of(*, action: Any) -> Optional[str]:
    try:
        action()
    except (ResourceValidationError, IPPoolValidationError, HealthChangeReasonRequiredError) as refusal:
        return refusal.error_code
    return None


# ---------------------------------------------------------------------------
# Resource pool names
# ---------------------------------------------------------------------------


def test_pool_name_with_a_space_is_refused():
    """
    **Feature: resources (RES-24 server-side validation)**
    **Property: creating the resource pool "android phones" is refused
    with INVALID_POOL_NAME, as the form's rule says.**
    """
    manager = ResourceManager(_session())

    code = _error_code_of(action=lambda: manager.create_pool(ResourcePoolCreateRequest(name="android phones")))

    testbase.assert_equal(code, "INVALID_POOL_NAME")
    return


def test_pool_name_within_the_rule_is_accepted():
    """
    **Feature: resources (RES-24 server-side validation)**
    **Property: "android-phones_2" (letters, digits, hyphen, underscore)
    is accepted.**
    """
    manager = ResourceManager(_session())

    pool = manager.create_pool(ResourcePoolCreateRequest(name="android-phones_2"))

    testbase.assert_equal(pool.name, "android-phones_2")
    return


# ---------------------------------------------------------------------------
# Manual health status changes need a reason
# ---------------------------------------------------------------------------


def test_manual_health_change_without_a_reason_is_refused():
    """
    **Feature: resources (RES-24 server-side validation)**
    **Property: a user-triggered health status change with an empty (or
    blank) reason is refused and no transition is recorded.**
    """
    session = _session()
    resource_id = _device(session=session)
    monitor = HealthMonitor(session)

    code = _error_code_of(action=lambda: monitor.update_health_status(resource_id, "maintenance", "   ", str(uuid.uuid4())))
    logged = session.query(HealthTransitionLog).filter(HealthTransitionLog.resource_id == resource_id).count()

    testbase.assert_equal((code, logged), ("HEALTH_CHANGE_REASON_REQUIRED", 0))
    return


def test_manual_health_change_with_a_reason_is_recorded():
    """
    **Feature: resources (RES-24 server-side validation)**
    **Property: a user-triggered change with a reason is applied and its
    reason recorded.**
    """
    session = _session()
    resource_id = _device(session=session)

    transition = HealthMonitor(session).update_health_status(resource_id, "maintenance", "firmware update", str(uuid.uuid4()))

    testbase.assert_equal((transition.new_status, transition.reason), ("maintenance", "firmware update"))
    return


def test_automatic_health_change_needs_no_reason_from_a_person():
    """
    **Feature: resources (RES-24 server-side validation)**
    **Property: a change made by the health checker is not held to the
    manual-reason rule.**
    """
    session = _session()
    resource_id = _device(session=session)

    transition = HealthMonitor(session).update_health_status(
        resource_id, "offline", "", None, triggered_by=TRIGGER_HEALTH_CHECK,
    )

    testbase.assert_equal(transition.new_status, "offline")
    return


# ---------------------------------------------------------------------------
# IP pool ranges and addresses are stored canonical
# ---------------------------------------------------------------------------


def test_ip_pool_range_is_stored_as_its_network():
    """
    **Feature: resources (RES-24 server-side validation)**
    **Property: an IP pool created as 10.50.0.5/29 is stored as the
    network it names, 10.50.0.0/29.**
    """
    manager = IPPoolManager(_session())

    pool = manager.create_pool(IPPoolCreateRequest(name="lab-b", cidr="10.50.0.5/29"))

    testbase.assert_equal(pool.cidr, "10.50.0.0/29")
    return


def test_ip_pool_overlap_is_found_for_another_spelling_of_the_same_network():
    """
    **Feature: resources (RES-24 server-side validation)**
    **Property: after 10.50.0.5/29 exists, creating 10.50.0.2/29 (the
    same network spelled differently) is refused as an overlap.**
    """
    manager = IPPoolManager(_session())
    manager.create_pool(IPPoolCreateRequest(name="lab-b", cidr="10.50.0.5/29"))

    refused = False
    try:
        manager.create_pool(IPPoolCreateRequest(name="lab-c", cidr="10.50.0.2/29"))
    except CIDROverlapError:
        refused = True

    testbase.assert_equal(refused, True)
    return


def test_ip_pool_addresses_are_stored_canonical():
    """
    **Feature: resources (RES-24 server-side validation)**
    **Property: an IPv6 pool's range, gateway and reserved address typed
    in long upper-case form are stored in canonical form.**
    """
    manager = IPPoolManager(_session())

    pool = manager.create_pool(IPPoolCreateRequest(
        name="lab-v6", cidr="2001:DB8:0:0::/64", gateway="2001:DB8::0001", reserved_ips=["2001:db8:0::0005"],
    ))

    testbase.assert_equal((pool.cidr, pool.gateway, pool.reserved_ips), ("2001:db8::/64", "2001:db8::1", ["2001:db8::5"]))
    return


def test_ip_pool_reserved_value_that_is_not_an_address_is_named_as_such():
    """
    **Feature: resources (RES-24 server-side validation)**
    **Property: a reserved IP that is not an IP address at all is refused
    with INVALID_IP_ADDRESS (not "not in the pool's range").**
    """
    manager = IPPoolManager(_session())

    code = _error_code_of(action=lambda: manager.create_pool(
        IPPoolCreateRequest(name="lab-d", cidr="10.60.0.0/28", reserved_ips=["banana"])
    ))

    testbase.assert_equal(code, "INVALID_IP_ADDRESS")
    return


def test_ip_pool_gateway_can_be_cleared():
    """
    **Feature: resources (RES-24 server-side validation)**
    **Property: updating an IP pool with an empty gateway clears it.**
    """
    manager = IPPoolManager(_session())
    created = manager.create_pool(IPPoolCreateRequest(name="lab-e", cidr="10.70.0.0/28", gateway="10.70.0.1"))

    updated = manager.update_pool(created.id, IPPoolUpdateRequest(gateway=""))

    testbase.assert_equal(updated.gateway, None)
    return
