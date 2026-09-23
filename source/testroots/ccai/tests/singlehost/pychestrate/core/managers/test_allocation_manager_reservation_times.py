"""
.. module:: test_allocation_manager_reservation_times
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Reservation windows given as naive or zoned datetimes, against
               a real SQLite database (audit finding RES-02).

.. moduleauthor:: Code Craft AI LLC

The reservation form handed the manager naive ``datetime-local`` values, and
``create_reservation`` / ``modify_reservation`` compared them with the aware
``utc_now()``: every valid window failed with "can't compare offset-naive and
offset-aware datetimes". The manager now takes a naive time to be UTC (as the
database layer stores it) and works in aware UTC throughout.

**Feature: resources (RES-02 reservation times)**
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import uuid

from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import sqlalchemy as sa

from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from ccai import testbase

from ccai.pychestrate.core.defaults import utc_now
from ccai.pychestrate.core.managers.allocation_manager import (
    AllocationManager,
    InvalidTimeWindowError,
    ReservationRequest,
)
from ccai.pychestrate.core.orm import (
    PychestrateModelBase,
    Reservation,
    Resource,
)


def _sqlite_database() -> Callable[[], Any]:
    engine = sa.create_engine(
        "sqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    PychestrateModelBase.metadata.create_all(engine)
    rtnval = sessionmaker(bind=engine, expire_on_commit=False)
    return rtnval


def _resource(*, new_session: Callable[[], Any]) -> int:
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


def _tomorrow_at(*, hour: int) -> datetime:
    """
        A naive datetime holding tomorrow's UTC date at ``hour``:00.
    """
    tomorrow = utc_now() + timedelta(days=1)
    rtnval = datetime(tomorrow.year, tomorrow.month, tomorrow.day, hour, 0)
    return rtnval


def test_create_reservation_takes_a_naive_window_as_utc():
    """
    **Feature: resources (RES-02 reservation times)**
    **Property: a reservation requested with naive start/end times is
    created (no TypeError) and stored as those times in UTC.**
    """
    new_session = _sqlite_database()
    resource_id = _resource(new_session=new_session)
    start = _tomorrow_at(hour=9)

    session = new_session()
    created = AllocationManager(session).create_reservation(
        ReservationRequest(resource_id=resource_id, start_time=start, end_time=_tomorrow_at(hour=11)),
        str(uuid.uuid4()),
    )

    testbase.assert_equal(created.start_time, start.replace(tzinfo=timezone.utc))
    return


def test_create_reservation_stores_a_zoned_window_as_the_same_instant():
    """
    **Feature: resources (RES-02 reservation times)**
    **Property: a window given at UTC-7 is stored as the same instants in
    UTC (09:00-07:00 reads back as 16:00 UTC).**
    """
    new_session = _sqlite_database()
    resource_id = _resource(new_session=new_session)
    pacific = timezone(timedelta(hours=-7))
    start = _tomorrow_at(hour=9).replace(tzinfo=pacific)

    session = new_session()
    created = AllocationManager(session).create_reservation(
        ReservationRequest(resource_id=resource_id, start_time=start, end_time=start + timedelta(hours=2)),
        str(uuid.uuid4()),
    )
    session.close()
    reader = new_session()
    stored = reader.query(Reservation).filter(Reservation.id == created.id).one()

    testbase.assert_equal(stored.start_time, start.astimezone(timezone.utc))
    return


def test_create_reservation_refuses_a_naive_window_in_the_past():
    """
    **Feature: resources (RES-02 reservation times)**
    **Property: a naive window that starts in the past is refused with
    InvalidTimeWindowError, not a naive/aware TypeError.**
    """
    new_session = _sqlite_database()
    resource_id = _resource(new_session=new_session)
    yesterday = _tomorrow_at(hour=9) - timedelta(days=2)

    session = new_session()
    error_code = None
    try:
        AllocationManager(session).create_reservation(
            ReservationRequest(
                resource_id=resource_id,
                start_time=yesterday,
                end_time=yesterday + timedelta(hours=2),
            ),
            str(uuid.uuid4()),
        )
    except InvalidTimeWindowError as refusal:
        error_code = refusal.error_code

    testbase.assert_equal(error_code is not None, True)
    return


def test_modify_reservation_takes_a_naive_window_as_utc():
    """
    **Feature: resources (RES-02 reservation times)**
    **Property: a reservation made in one request is moved in a later
    request with naive times, and the new window is stored in UTC.**
    """
    new_session = _sqlite_database()
    resource_id = _resource(new_session=new_session)
    owner = str(uuid.uuid4())
    session = new_session()
    created = AllocationManager(session).create_reservation(
        ReservationRequest(
            resource_id=resource_id,
            start_time=_tomorrow_at(hour=9).replace(tzinfo=timezone.utc),
            end_time=_tomorrow_at(hour=11).replace(tzinfo=timezone.utc),
        ),
        owner,
    )
    session.close()

    later = new_session()
    moved = AllocationManager(later).modify_reservation(
        created.id, owner, start_time=_tomorrow_at(hour=13), end_time=_tomorrow_at(hour=15),
    )

    testbase.assert_equal(moved.start_time, _tomorrow_at(hour=13).replace(tzinfo=timezone.utc))
    return
