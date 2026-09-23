"""
.. module:: test_ip_pool_manager_infrastructure_addresses
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The pool's gateway and in-range DNS servers are never handed out
               (audit finding RES-13).

.. moduleauthor:: Code Craft AI LLC

Auto-assign excluded only the pool's reserved list, so the first checkout from
``10.20.30.0/28`` with gateway ``10.20.30.1`` returned the gateway itself. The
gateway and any DNS servers inside the range are now reserved automatically:
never auto-assigned, refused as a specific address, counted as reserved, and
listed on the pool.

**Feature: resources (RES-13 infrastructure addresses)**
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import uuid

from typing import Any, Callable, List, Optional

import sqlalchemy as sa

from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from ccai import testbase

from ccai.pychestrate.core.managers.ip_pool_manager import (
    IPAllocationRequest,
    IPPoolCreateRequest,
    IPPoolManager,
    IPReservedError,
    infrastructure_addresses,
)
from ccai.pychestrate.core.orm import PychestrateModelBase


def _pool(
        *,
        gateway: Optional[str] = "10.20.30.1",
        dns_servers: Optional[List[str]] = None,
        reserved_ips: Optional[List[str]] = None
    ) -> Any:
    """
        An IPPoolManager over a fresh SQLite database holding one pool,
        ``lab-net`` = 10.20.30.0/28. Returns ``(manager, pool_id)``.
    """
    engine = sa.create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False},
    )
    PychestrateModelBase.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    manager = IPPoolManager(session)
    created = manager.create_pool(IPPoolCreateRequest(
        name="lab-net",
        cidr="10.20.30.0/28",
        gateway=gateway,
        dns_servers=list(dns_servers or []),
        reserved_ips=list(reserved_ips or []),
    ))
    rtnval = (manager, created.id)
    return rtnval


def test_auto_assign_skips_the_gateway():
    """
    **Feature: resources (RES-13 infrastructure addresses)**
    **Property: the first auto-assigned address from 10.20.30.0/28 with
    gateway 10.20.30.1 is 10.20.30.2, not the gateway.**
    """
    manager, pool_id = _pool()

    allocation = manager.checkout_ip(IPAllocationRequest(pool_id=pool_id), str(uuid.uuid4()))

    testbase.assert_equal(allocation.ip_address, "10.20.30.2")
    return


def test_auto_assign_skips_dns_servers_inside_the_range():
    """
    **Feature: resources (RES-13 infrastructure addresses)**
    **Property: a DNS server inside the range (10.20.30.2) is skipped by
    auto-assign as well; one outside the range changes nothing.**
    """
    manager, pool_id = _pool(dns_servers=["10.20.30.2", "8.8.8.8"])

    allocation = manager.checkout_ip(IPAllocationRequest(pool_id=pool_id), str(uuid.uuid4()))

    testbase.assert_equal(allocation.ip_address, "10.20.30.3")
    return


def test_bulk_checkout_skips_the_gateway():
    """
    **Feature: resources (RES-13 infrastructure addresses)**
    **Property: a contiguous checkout of three addresses starts after the
    gateway (10.20.30.2-4).**
    """
    manager, pool_id = _pool()

    bulk = manager.checkout_ips(IPAllocationRequest(pool_id=pool_id, count=3), str(uuid.uuid4()))

    testbase.assert_equal([a.ip_address for a in bulk.allocations], ["10.20.30.2", "10.20.30.3", "10.20.30.4"])
    return


def test_checking_out_the_gateway_by_address_is_refused():
    """
    **Feature: resources (RES-13 infrastructure addresses)**
    **Property: asking for the gateway as a specific address is refused
    with IPReservedError naming it as the gateway.**
    """
    manager, pool_id = _pool()

    message = None
    try:
        manager.checkout_ip(
            IPAllocationRequest(pool_id=pool_id, specific_ip="10.20.30.1"), str(uuid.uuid4())
        )
    except IPReservedError as refusal:
        message = refusal.message

    testbase.assert_true(message is not None and "gateway" in message, repr(message))
    return


def test_gateway_is_counted_as_reserved():
    """
    **Feature: resources (RES-13 infrastructure addresses)**
    **Property: a /28 (14 usable) with a gateway reports 1 reserved and
    13 available.**
    """
    manager, pool_id = _pool()

    pool = manager.get_pool(pool_id)

    testbase.assert_equal((pool.reserved_count, pool.available_count), (1, 13))
    return


def test_gateway_also_on_the_reserved_list_is_counted_once():
    """
    **Feature: resources (RES-13 infrastructure addresses)**
    **Property: a gateway that is also on the reserved list counts as one
    reserved address, not two.**
    """
    manager, pool_id = _pool(reserved_ips=["10.20.30.1", "10.20.30.9"])

    pool = manager.get_pool(pool_id)

    testbase.assert_equal(pool.reserved_count, 2)
    return


def test_pool_lists_its_infrastructure_addresses_with_their_roles():
    """
    **Feature: resources (RES-13 infrastructure addresses)**
    **Property: the pool response names the in-range gateway and DNS
    server with their roles, and leaves out a DNS server outside the
    range.**
    """
    manager, pool_id = _pool(dns_servers=["10.20.30.2", "8.8.8.8"])

    pool = manager.get_pool(pool_id)

    testbase.assert_equal(pool.infrastructure_ips, {"10.20.30.1": "gateway", "10.20.30.2": "DNS server"})
    return


def test_infrastructure_addresses_are_canonical():
    """
    **Feature: resources (RES-13 infrastructure addresses)**
    **Property: an IPv6 gateway typed in a long form is recognised in its
    canonical form (2001:db8::1), so it is excluded like any other.**
    """
    found = infrastructure_addresses("2001:db8::/64", "2001:DB8:0:0::0001", [])

    testbase.assert_equal(found, {"2001:db8::1": "gateway"})
    return
