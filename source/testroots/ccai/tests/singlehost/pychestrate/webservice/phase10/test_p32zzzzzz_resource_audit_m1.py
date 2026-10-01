"""
.. module:: test_p32zzzzzz_resource_audit_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Who registered, changed or retired a resource is in the audit log (RES-22).

.. moduleauthor:: Code Craft AI LLC

The inventory published ``entity.resource.*`` events and no audit kind listened, so "who renamed this
device, who put it in maintenance, who retired it" had no answer on the Audit Logs page. Registering a resource,
changing its name, description or tags, and changing its state are now audit records whose target is
``resource:<id>`` and whose actor is the user who did it. Run here against a real in-memory database with the
audit subscriber wired to it.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import uuid

from typing import Any, Dict, List

from sqlalchemy.orm import sessionmaker

from ccai import testbase

from ccai.pychestrate.webservice.audit.audit_presenter import action_for_kind, describe_audit_record
from ccai.pychestrate.webservice.audit.bus_subscriber import wire_bus_subscribers
from ccai.pychestrate.webservice.audit.models import AuditRecord
from ccai.pychestrate.webservice.resources.inventory import register_builtin_extensions as inventory_register
from ccai.pychestrate.webservice.resources.inventory import service as inventory_service
from ccai.pychestrate.webservice.resources.inventory.models import ResourceState

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
    reset_phase1_runtime,
)


PROJECT_ID = "00000000-0000-4000-8000-0000000000f1"
ACTOR = str(uuid.UUID("00000000-0000-4000-8000-0000000000a1"))


def _records(factory: Any) -> List[Dict[str, Any]]:
    session = factory()
    try:
        rows = session.query(AuditRecord).filter(AuditRecord.kind.like("audit.resource.%")).order_by(AuditRecord.sequence_number.asc()).all()
        return [{"kind": row.kind, "actor": str(row.actor_user_id) if row.actor_user_id is not None else None, "target": row.target_ref, "payload": row.payload_json} for row in rows]
    finally:
        session.close()


def test_registering_changing_and_retiring_a_resource_is_in_the_audit_log_with_who_did_it():
    """
    **Feature: resource audit (RES-22)**
    **Property: registering a device, renaming it, and retiring it write three audit records of kinds
    registered, updated and state_changed, each targeting ``resource:<id>`` and each naming the acting user;
    the update names the fields that changed and the state change names the states; a change that alters nothing
    writes none.**
    """
    reset_phase1_runtime()
    inventory_register()
    engine, session = build_in_memory_session()
    factory = sessionmaker(bind=engine)
    wire_bus_subscribers(session_factory=factory)

    view = inventory_service.register_resource(
        db_session=session, project_id=PROJECT_ID, kind="device", display_name="Bench phone 1",
        attributes={"hostname": "phone-audit", "mac_address": "aa:bb:cc:dd:ee:99"}, tags=("android",), actor="user:" + ACTOR,
    )
    resource_id = str(view.resource_id)
    inventory_service.update_resource(db_session=session, resource_id=resource_id, display_name="Bench phone 1", actor="user:" + ACTOR)
    after_noop = len(_records(factory))
    inventory_service.update_resource(db_session=session, resource_id=resource_id, display_name="Bench phone 2", tags=("android", "lab"), actor="user:" + ACTOR)
    inventory_service.transition_state(db_session=session, resource_id=resource_id, new_state=ResourceState.RETIRED, actor="user:" + ACTOR, reason="dropped")
    records = _records(factory)

    testbase.assert_equal(
        (
            after_noop, [record["kind"] for record in records],
            {record["actor"] for record in records}, {record["target"] for record in records},
            sorted(records[1]["payload"]["changed"]), records[2]["payload"]["from_state"], records[2]["payload"]["to_state"], records[2]["payload"]["reason"],
        ),
        (
            1, ["audit.resource.registered", "audit.resource.updated", "audit.resource.state_changed"],
            {ACTOR}, {"resource:" + resource_id},
            ["display_name", "tags"], "available", "retired", "dropped",
        ),
    )
    return


def test_the_audit_page_describes_a_resource_record_in_words():
    """
    **Feature: resource audit (RES-22)**
    **Property: the Audit Logs page names the three actions ("Registered resource", "Updated resource",
    "Changed resource state") and its detail column says which resource and what happened: its name and kind;
    its name and the fields changed; its name, the states and the reason.**
    """
    reset_phase1_runtime()
    inventory_register()
    engine, session = build_in_memory_session()
    factory = sessionmaker(bind=engine)
    wire_bus_subscribers(session_factory=factory)
    view = inventory_service.register_resource(
        db_session=session, project_id=PROJECT_ID, kind="device", display_name="Bench phone 1",
        attributes={"hostname": "phone-words", "mac_address": "aa:bb:cc:dd:ee:98"}, actor="user:" + ACTOR,
    )
    inventory_service.update_resource(db_session=session, resource_id=str(view.resource_id), description="moved to rack 4", actor="user:" + ACTOR)
    inventory_service.transition_state(db_session=session, resource_id=str(view.resource_id), new_state=ResourceState.MAINTENANCE, actor="user:" + ACTOR, reason="firmware")
    reader = factory()
    try:
        rows = reader.query(AuditRecord).filter(AuditRecord.kind.like("audit.resource.%")).order_by(AuditRecord.sequence_number.asc()).all()
        described = [describe_audit_record(record=row, logins={ACTOR: "ada"}) for row in rows]
    finally:
        reader.close()

    testbase.assert_equal(
        ([row.action for row in described], [row.summary for row in described]),
        (
            ["Registered resource", "Updated resource", "Changed resource state"],
            ['"Bench phone 1" - device', '"Bench phone 1" - changed: description', '"Bench phone 1" - available to maintenance - reason: "firmware"'],
        ),
    )
    return
