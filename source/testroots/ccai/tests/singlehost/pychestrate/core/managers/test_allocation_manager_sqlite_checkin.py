"""
.. module:: test_allocation_manager_sqlite_checkin
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Check-in, force check-in, expiry and utilisation against a real
               SQLite database (audit finding RES-01).

.. moduleauthor:: Code Craft AI LLC

SQLite stores no time zone, so a ``DateTime(timezone=True)`` value written as
aware UTC used to come back naive. The next request's check-in then computed
``utc_now() - allocation.checkout_time`` and crashed with ``TypeError: can't
subtract offset-naive and offset-aware datetimes``: a checked-out device could
never be returned. The earlier manager tests used mocks holding aware values,
so they could not see it. Every test here writes through one session and reads
back through a fresh one, the way two web requests do.

**Feature: resources (RES-01 check-in on SQLite)**
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import uuid

from datetime import timedelta
from typing import Any, Callable, Tuple

import sqlalchemy as sa

from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from ccai import testbase

from ccai.pychestrate.core.defaults import utc_now
from ccai.pychestrate.core.managers.allocation_manager import (
    AllocationManager,
    CheckoutRequest,
)
from ccai.pychestrate.core.orm import (
    Allocation,
    PychestrateModelBase,
    Resource,
)


def _sqlite_database() -> Callable[[], Any]:
    """
        An in-memory SQLite database with the core schema. Returns a
        session factory configured like production (``expire_on_commit``
        off); each call to it plays the part of a new request.
    """
    engine = sa.create_engine(
        "sqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    PychestrateModelBase.metadata.create_all(engine)
    rtnval = sessionmaker(bind=engine, expire_on_commit=False)
    return rtnval


def _resource(*, new_session: Callable[[], Any]) -> int:
    """
        Create one online device and return its id.
    """
    session = new_session()
    resource = Resource(
        name="board-{}".format(uuid.uuid4().hex[:8]),
        resource_type="device",
        metadata_json={},
        sensitive_fields=[],
        capacity=1,
        health_status="online",
    )
    session.add(resource)
    session.commit()
    rtnval = resource.id
    session.close()
    return rtnval


def _checked_out(*, new_session: Callable[[], Any]) -> Tuple[int, str]:
    """
        Check a new device out through the manager in one "request" and
        return ``(allocation_id, user_id)``.
    """
    resource_id = _resource(new_session=new_session)
    user_id = str(uuid.uuid4())
    session = new_session()
    allocation = AllocationManager(session).checkout(
        CheckoutRequest(resource_id=resource_id, reason="bench test"), user_id
    )
    session.close()
    rtnval = (allocation.id, user_id)
    return rtnval


def _stored_allocation(
        *,
        new_session: Callable[[], Any],
        checked_out_minutes_ago: int,
        expected_checkin_minutes_ago: Any = None
    ) -> Tuple[int, str]:
    """
        Store an active allocation whose checkout happened
        ``checked_out_minutes_ago`` minutes ago and return
        ``(allocation_id, user_id)``.
    """
    resource_id = _resource(new_session=new_session)
    user_id = str(uuid.uuid4())
    now = utc_now()
    expected_checkin = None
    if expected_checkin_minutes_ago is not None:
        expected_checkin = now - timedelta(minutes=expected_checkin_minutes_ago)
    session = new_session()
    allocation = Allocation(
        resource_id=resource_id,
        user_id=user_id,
        mode="exclusive",
        status="active",
        checkout_time=now - timedelta(minutes=checked_out_minutes_ago),
        expected_checkin=expected_checkin,
        metadata_snapshot={},
    )
    session.add(allocation)
    session.commit()
    rtnval = (allocation.id, user_id)
    session.close()
    return rtnval


def test_checkin_in_a_later_request_releases_the_allocation():
    """
    **Feature: resources (RES-01 check-in on SQLite)**
    **Property: an allocation checked out in one request is checked in by
    its owner in a later request on SQLite, and ends up released.**
    """
    new_session = _sqlite_database()
    allocation_id, user_id = _checked_out(new_session=new_session)

    session = new_session()
    response = AllocationManager(session).checkin(allocation_id, user_id)

    testbase.assert_equal(response.status, "released")
    return


def test_force_checkin_in_a_later_request_releases_the_allocation():
    """
    **Feature: resources (RES-01 check-in on SQLite)**
    **Property: an administrator's force check-in of an allocation made in
    an earlier request succeeds on SQLite and records the forced status.**
    """
    new_session = _sqlite_database()
    allocation_id, _ = _checked_out(new_session=new_session)

    session = new_session()
    response = AllocationManager(session).force_checkin(
        allocation_id, str(uuid.uuid4()), "device stuck on a dead runner"
    )

    testbase.assert_equal(response.status, "forced")
    return


def test_checkin_records_the_elapsed_duration():
    """
    **Feature: resources (RES-01 check-in on SQLite)**
    **Property: checking in an allocation that was checked out 90 minutes
    ago records a duration of 90 minutes.**
    """
    new_session = _sqlite_database()
    allocation_id, user_id = _stored_allocation(
        new_session=new_session, checked_out_minutes_ago=90
    )

    session = new_session()
    response = AllocationManager(session).checkin(allocation_id, user_id)

    testbase.assert_equal(response.duration_minutes, 90)
    return


def test_checked_in_allocation_reads_back_with_aware_utc_times():
    """
    **Feature: resources (RES-01 check-in on SQLite)**
    **Property: after a check-in, the stored checkout and check-in times
    read back from SQLite as timezone-aware UTC values.**
    """
    new_session = _sqlite_database()
    allocation_id, user_id = _checked_out(new_session=new_session)
    session = new_session()
    AllocationManager(session).checkin(allocation_id, user_id)
    session.close()

    reader = new_session()
    stored = reader.query(Allocation).filter(Allocation.id == allocation_id).one()
    offsets = (stored.checkout_time.utcoffset(), stored.actual_checkin.utcoffset())

    testbase.assert_equal(offsets, (timedelta(0), timedelta(0)))
    return


def test_expiry_releases_a_timed_out_allocation():
    """
    **Feature: resources (RES-01 check-in on SQLite)**
    **Property: the timeout sweep expires an allocation whose expected
    check-in has passed, on SQLite, instead of crashing on the duration.**
    """
    new_session = _sqlite_database()
    _stored_allocation(
        new_session=new_session,
        checked_out_minutes_ago=120,
        expected_checkin_minutes_ago=60,
    )

    session = new_session()
    expired = AllocationManager(session).expire_timed_out_allocations()

    testbase.assert_equal(expired, 1)
    return


def test_utilisation_metrics_count_an_open_allocation():
    """
    **Feature: resources (RES-01 check-in on SQLite)**
    **Property: utilisation metrics over an allocation that is still open
    (no check-in, no expected check-in) are computed on SQLite; the open
    allocation counts toward peak concurrent use.**
    """
    new_session = _sqlite_database()
    _stored_allocation(new_session=new_session, checked_out_minutes_ago=30)

    session = new_session()
    metrics = AllocationManager(session).get_utilization_metrics()

    testbase.assert_equal(metrics["peak_concurrent_usage"], 1)
    return
