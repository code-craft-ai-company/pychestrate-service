"""
.. module:: test_p13h_resources_error_copy_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The resources pages show people user-facing messages for
               refused requests, not the managers' log text (audit finding
               RES-26).

.. moduleauthor:: Code Craft AI LLC

The route layer flashed the managers' messages verbatim: "start_time must be
before end_time", Python ``ipaddress`` wording, user UUIDs, an overlap message
that listed the pools twice. Each typed manager error now carries a specific
error code, and the route layer maps codes to copy written for people; the
manager's text goes to the log.

**Feature: resources (RES-26 user-facing error copy)**
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import uuid

from datetime import datetime, timedelta, timezone
from typing import Any

import sqlalchemy as sa

from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from ccai import testbase

from ccai.pychestrate.core.defaults import utc_now
from ccai.pychestrate.core.managers.allocation_manager import (
    AllocationManager,
    InvalidTimeWindowError,
    NotAllocationOwnerError,
    ReservationConflictError,
    ReservationRequest,
    ReservationResponse,
)
from ccai.pychestrate.core.managers.health_monitor import (
    InvalidHealthCheckConfigError,
)
from ccai.pychestrate.core.managers.ip_pool_manager import (
    CIDROverlapError,
    IPAllocationRequest,
    IPPoolCreateRequest,
    IPPoolManager,
    IPPoolValidationError,
)
from ccai.pychestrate.core.orm import PychestrateModelBase, Resource
from ccai.pychestrate.webservice.webinterface.blueprints.resources import (
    routes as resources_routes,
    routes_health as resources_routes_health,
    routes_ip_pools as resources_routes_ip_pools,
)


def _session() -> Any:
    engine = sa.create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False},
    )
    PychestrateModelBase.metadata.create_all(engine)
    rtnval = sessionmaker(bind=engine, expire_on_commit=False)()
    return rtnval


def _refusal_of(*, action: Any) -> Any:
    try:
        action()
    except Exception as refusal:
        return refusal
    return None


# ---------------------------------------------------------------------------
# Reservation windows
# ---------------------------------------------------------------------------


def test_end_before_start_reads_as_a_sentence():
    """
    **Feature: resources (RES-26 user-facing error copy)**
    **Property: a window whose end is not after its start is reported as
    "The end time must be after the start time.", not in field names.**
    """
    session = _session()
    resource = Resource(name="board-1", resource_type="device", metadata_json={}, sensitive_fields=[], capacity=1, health_status="online")
    session.add(resource)
    session.commit()
    start = utc_now() + timedelta(days=1)
    refusal = _refusal_of(action=lambda: AllocationManager(session).create_reservation(
        ReservationRequest(resource_id=resource.id, start_time=start, end_time=start - timedelta(hours=1)),
        str(uuid.uuid4()),
    ))

    message = resources_routes._describe_allocation_error(exc=refusal)

    testbase.assert_equal(message, "The end time must be after the start time.")
    return


def test_start_in_the_past_reads_as_a_sentence():
    """
    **Feature: resources (RES-26 user-facing error copy)**
    **Property: a window that starts in the past is reported in plain
    words.**
    """
    refusal = InvalidTimeWindowError("start_time cannot be in the past", error_code="START_IN_PAST")

    message = resources_routes._describe_allocation_error(exc=refusal)

    testbase.assert_equal(message, "The start time has already passed. Choose a start time in the future.")
    return


def test_conflict_names_each_reservation_once_with_its_zone():
    """
    **Feature: resources (RES-26 user-facing error copy)**
    **Property: a reservation conflict names the conflicting reservation
    and its window once, with the times marked UTC.**
    """
    held = ReservationResponse(
        id=2, resource_id=1, resource_name="board-1", user_id="u", username="dana", job_id=None,
        start_time=datetime(2026, 9, 25, 16, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 9, 25, 19, 30, tzinfo=timezone.utc),
        mode="exclusive", status="pending", created_at=datetime(2026, 9, 22, tzinfo=timezone.utc),
    )
    refusal = ReservationConflictError(
        "Reservation conflicts with 1 existing reservation(s)", conflicting_reservations=[held],
    )

    message = resources_routes._describe_allocation_error(exc=refusal)

    testbase.assert_equal(
        message,
        "The resource is already reserved for part of that time: reservation #2"
        " from 2026-09-25 16:00 UTC to 2026-09-25 19:30 UTC.",
    )
    return


def test_ownership_refusal_does_not_show_user_ids():
    """
    **Feature: resources (RES-26 user-facing error copy)**
    **Property: checking in someone else's allocation is explained
    without printing the user's UUID.**
    """
    user_id = str(uuid.uuid4())
    refusal = NotAllocationOwnerError("User '{}' is not the owner of allocation '5'".format(user_id))

    message = resources_routes._describe_allocation_error(exc=refusal)

    testbase.assert_equal(
        (user_id in message, message.startswith("Only the person who checked this resource out")),
        (False, True),
    )
    return


# ---------------------------------------------------------------------------
# IP pools
# ---------------------------------------------------------------------------


def test_overlap_names_the_pools_once():
    """
    **Feature: resources (RES-26 user-facing error copy)**
    **Property: a CIDR overlap names the overlapping pool once (it used
    to be listed twice).**
    """
    refusal = CIDROverlapError(
        "CIDR range '10.20.30.0/28' overlaps with existing pools: lab-net", overlapping_pools=["lab-net"],
    )

    message = resources_routes_ip_pools._describe_ip_pool_error(exc=refusal)

    testbase.assert_equal(message, "That range overlaps the IP pool lab-net.")
    return


def test_malformed_cidr_is_explained_without_python_wording():
    """
    **Feature: resources (RES-26 user-facing error copy)**
    **Property: a range that is not CIDR notation is explained with an
    example instead of Python's "does not appear to be an IPv4 or IPv6
    network".**
    """
    refusal = _refusal_of(action=lambda: IPPoolManager(_session()).create_pool(
        IPPoolCreateRequest(name="lab", cidr="10.0.0.0/33")
    ))

    message = resources_routes_ip_pools._describe_ip_pool_error(exc=refusal)

    testbase.assert_equal(
        message, "Enter the range in CIDR notation, such as 192.168.1.0/24 or 2001:db8::/64."
    )
    return


def test_malformed_dns_server_is_explained_without_python_wording():
    """
    **Feature: resources (RES-26 user-facing error copy)**
    **Property: a DNS server that is not an IP address is explained with
    an example.**
    """
    refusal = _refusal_of(action=lambda: IPPoolManager(_session()).create_pool(
        IPPoolCreateRequest(name="lab", cidr="10.0.0.0/24", dns_servers=["dns.local"])
    ))

    message = resources_routes_ip_pools._describe_ip_pool_error(exc=refusal)

    testbase.assert_equal(message, "Each DNS server must be an IP address, such as 8.8.8.8.")
    return


def test_specific_address_that_is_not_an_ip_is_called_that():
    """
    **Feature: resources (RES-26 user-facing error copy)**
    **Property: checking out the "address" banana is refused as "not a
    valid IP address", not as "not in pool CIDR range".**
    """
    manager = IPPoolManager(_session())
    pool = manager.create_pool(IPPoolCreateRequest(name="lab-net", cidr="10.20.30.0/28"))
    refusal = _refusal_of(action=lambda: manager.checkout_ip(
        IPAllocationRequest(pool_id=pool.id, specific_ip="banana"), str(uuid.uuid4())
    ))

    message = resources_routes_ip_pools._describe_ip_pool_error(exc=refusal)

    testbase.assert_equal(
        (isinstance(refusal, IPPoolValidationError), message), (True, "'banana' is not a valid IP address.")
    )
    return


# ---------------------------------------------------------------------------
# Health checks
# ---------------------------------------------------------------------------


def test_health_config_limits_are_explained_in_words():
    """
    **Feature: resources (RES-26 user-facing error copy)**
    **Property: an interval below 1 second is reported as "The check
    interval must be at least 1 second.", not "interval_seconds must be
    at least 1".**
    """
    refusal = InvalidHealthCheckConfigError("interval_seconds must be at least 1", error_code="INTERVAL_TOO_SHORT")

    message = resources_routes_health._describe_health_monitor_error(exc=refusal)

    testbase.assert_equal(message, "The check interval must be at least 1 second.")
    return
