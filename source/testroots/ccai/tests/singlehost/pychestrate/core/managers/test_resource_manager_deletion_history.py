"""
.. module:: test_resource_manager_deletion_history
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Deleting a device that has history, against SQLite with foreign
               keys enforced (audit finding RES-09).

.. moduleauthor:: Code Craft AI LLC

Reservations, allocation records, the health check configuration, health and
metadata history, and project assignments all reference the resource through
NOT NULL foreign keys. Deleting a device that ever had any of them failed with
an IntegrityError ("unexpected error" in the UI), even for a cancelled
reservation. The manager now removes those records with the resource, in an
order the foreign keys allow. The database here enforces foreign keys, as
PostgreSQL does.

**Feature: resources (RES-09 deleting a device with history)**
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import uuid

from datetime import timedelta
from typing import Any, Callable, Dict, Tuple

import sqlalchemy as sa

from sqlalchemy import event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from ccai import testbase

from ccai.pychestrate.core.defaults import utc_now
from ccai.pychestrate.core.managers.resource_manager import ResourceManager
from ccai.pychestrate.core.orm import (
    Allocation,
    HealthCheckConfig,
    HealthTransitionLog,
    Project,
    PychestrateModelBase,
    Reservation,
    Resource,
    ResourceMetadataHistory,
    User,
    project_resources,
)


def _database() -> Callable[[], Any]:
    """
        In-memory SQLite with the core schema and foreign keys enforced.
    """
    engine = sa.create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _enforce_foreign_keys(dbapi_connection: Any, connection_record: Any) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")
        return

    PychestrateModelBase.metadata.create_all(engine)
    rtnval = sessionmaker(bind=engine, expire_on_commit=False)
    return rtnval


def _device_with_history(*, new_session: Callable[[], Any], **history: bool) -> Tuple[int, Dict[str, Any]]:
    """
        Store a device and the history records named in ``history``
        (``reservation``, ``activated_reservation``, ``allocation``,
        ``health_config``, ``health_transition``, ``metadata_change``,
        ``project``). Returns ``(resource_id, ids)``.
    """
    session = new_session()
    user = User(
        id=uuid.uuid4(), first_name="Dana", last_name="Lab", email="dana-{}@example.com".format(uuid.uuid4().hex[:6]),
        login="dana-" + uuid.uuid4().hex[:6], status="active", authtype="consumer",
    )
    session.add(user)
    resource = Resource(
        name="board-" + uuid.uuid4().hex[:6], resource_type="device", metadata_json={},
        sensitive_fields=[], capacity=1, health_status="online",
    )
    session.add(resource)
    session.flush()
    now = utc_now()
    ids: Dict[str, Any] = {"user_id": user.id}
    if history.get("allocation") or history.get("activated_reservation"):
        allocation = Allocation(
            resource_id=resource.id, user_id=user.id, mode="exclusive", status="released",
            checkout_time=now - timedelta(hours=3), actual_checkin=now - timedelta(hours=2),
            metadata_snapshot={},
        )
        session.add(allocation)
        session.flush()
        ids["allocation_id"] = allocation.id
    if history.get("reservation"):
        session.add(Reservation(
            resource_id=resource.id, user_id=user.id, mode="exclusive", status="cancelled",
            start_time=now + timedelta(days=1), end_time=now + timedelta(days=1, hours=2),
        ))
    if history.get("activated_reservation"):
        session.add(Reservation(
            resource_id=resource.id, user_id=user.id, mode="exclusive", status="completed",
            start_time=now - timedelta(hours=3), end_time=now - timedelta(hours=2),
            allocation_id=ids["allocation_id"],
        ))
    if history.get("health_config"):
        session.add(HealthCheckConfig(resource_id=resource.id, probe_url="http://10.0.4.21/health"))
    if history.get("health_transition"):
        session.add(HealthTransitionLog(
            resource_id=resource.id, old_status="online", new_status="maintenance",
            reason="firmware update", triggered_by="user", user_id=user.id,
        ))
    if history.get("metadata_change"):
        session.add(ResourceMetadataHistory(
            resource_id=resource.id, old_metadata_json={}, new_metadata_json={"serial": "SN-1"},
            changed_by_id=user.id,
        ))
    if history.get("project"):
        project = Project(name="proj-" + uuid.uuid4().hex[:6], owner_id=user.id, metadata_json={})
        session.add(project)
        session.flush()
        session.execute(project_resources.insert().values(proj_id=project.id, res_id=resource.id, assigned_at=now))
    session.commit()
    rtnval = (resource.id, ids)
    session.close()
    return rtnval


def _delete(*, new_session: Callable[[], Any], resource_id: int) -> Dict[str, Any]:
    session = new_session()
    rtnval = ResourceManager(session).delete_resource(resource_id, None)
    session.close()
    return rtnval


def _resource_exists(*, new_session: Callable[[], Any], resource_id: int) -> bool:
    session = new_session()
    rtnval = session.query(Resource).filter(Resource.id == resource_id).first() is not None
    session.close()
    return rtnval


def test_device_with_a_cancelled_reservation_is_deleted():
    """
    **Feature: resources (RES-09 deleting a device with history)**
    **Property: a device whose only history is a cancelled reservation is
    deleted.**
    """
    new_session = _database()
    resource_id, _ = _device_with_history(new_session=new_session, reservation=True)

    _delete(new_session=new_session, resource_id=resource_id)

    testbase.assert_equal(_resource_exists(new_session=new_session, resource_id=resource_id), False)
    return


def test_device_with_a_health_check_is_deleted():
    """
    **Feature: resources (RES-09 deleting a device with history)**
    **Property: a device with a health check configuration and health
    status history is deleted.**
    """
    new_session = _database()
    resource_id, _ = _device_with_history(new_session=new_session, health_config=True, health_transition=True)

    _delete(new_session=new_session, resource_id=resource_id)

    testbase.assert_equal(_resource_exists(new_session=new_session, resource_id=resource_id), False)
    return


def test_device_with_allocation_and_metadata_history_is_deleted():
    """
    **Feature: resources (RES-09 deleting a device with history)**
    **Property: a device with a released allocation and a metadata change
    is deleted.**
    """
    new_session = _database()
    resource_id, _ = _device_with_history(new_session=new_session, allocation=True, metadata_change=True)

    _delete(new_session=new_session, resource_id=resource_id)

    testbase.assert_equal(_resource_exists(new_session=new_session, resource_id=resource_id), False)
    return


def test_device_with_an_activated_reservation_is_deleted():
    """
    **Feature: resources (RES-09 deleting a device with history)**
    **Property: a device whose reservation was activated into an
    allocation (the reservation references the allocation) is deleted;
    the foreign keys are satisfied in order.**
    """
    new_session = _database()
    resource_id, _ = _device_with_history(new_session=new_session, activated_reservation=True)

    _delete(new_session=new_session, resource_id=resource_id)

    testbase.assert_equal(_resource_exists(new_session=new_session, resource_id=resource_id), False)
    return


def test_device_assigned_to_a_project_is_deleted():
    """
    **Feature: resources (RES-09 deleting a device with history)**
    **Property: a device assigned to a project is deleted and its
    project assignment goes with it.**
    """
    new_session = _database()
    resource_id, _ = _device_with_history(new_session=new_session, project=True)

    _delete(new_session=new_session, resource_id=resource_id)
    session = new_session()
    assignments = session.execute(
        sa.select(project_resources).where(project_resources.c.res_id == resource_id)
    ).fetchall()

    testbase.assert_equal(len(assignments), 0)
    return


def test_deletion_reports_the_records_removed():
    """
    **Feature: resources (RES-09 deleting a device with history)**
    **Property: delete_resource returns how many dependent records of
    each kind went with the device.**
    """
    new_session = _database()
    resource_id, _ = _device_with_history(
        new_session=new_session, reservation=True, activated_reservation=True, health_config=True,
        health_transition=True, metadata_change=True,
    )

    removed = _delete(new_session=new_session, resource_id=resource_id)

    testbase.assert_equal(removed, {
        "reservations": 2, "allocations": 1, "health_check_configs": 1,
        "health_transitions": 1, "metadata_history": 1,
    })
    return
