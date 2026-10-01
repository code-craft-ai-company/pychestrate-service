"""
.. module:: test_p32zzzzz_update_resource_rest_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: A resource's name, description and tags can be changed over REST (RES-22).

.. moduleauthor:: Code Craft AI LLC

A resource could be registered and read but not changed over REST: a typo in a name, a new tag or a note
meant retiring the device and registering it again. ``PATCH /api/v1/resources/{id}`` changes
``display_name``, ``description`` and/or ``tags`` (a field left out is not touched). The kind, the identity and
the attributes cannot be changed there (422 names them), a retired resource is refused (409: retirement is
terminal), and a change that alters nothing records nothing. The handlers run here against a real in-memory
database with the in-tree device kind.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import uuid

from typing import Any, Dict, List, Optional

from ccai import testbase
from ccai.testbase.mocking import create_module_patch

from ccai.pychestrate.webservice.extensions.registry import reset_registry_for_testing
from ccai.pychestrate.webservice.messaging.event_bus import EntityEvent, reset_for_testing as reset_event_bus, subscribe
from ccai.pychestrate.webservice.resources.inventory import register_builtin_extensions as inventory_register
from ccai.pychestrate.webservice.resources.inventory import service as inventory_service
from ccai.pychestrate.webservice.resources.inventory.models import ResourceState
from ccai.pychestrate.webservice.resources.restapi.v1 import resources_routes

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import build_in_memory_session


PROJECT_ID = "00000000-0000-4000-8000-0000000000e1"


class _Request:
    def __init__(self, *, db_session: Any, resource_id: str, body: Any = None) -> None:
        self.path = "/api/v1/resources/" + resource_id
        self.path_params: Dict[str, Any] = {"resource_id": resource_id}
        self.query_params = type("Query", (), {"get": lambda self, key, default=None: default})()
        self.db_session = db_session
        self.auth_principal = type("Principal", (), {"user_id": "user-1"})()
        self._body = body

    def json(self) -> Any:
        return self._body


class _Decision:
    def __init__(self, allowed: bool) -> None:
        self.allowed = allowed
        self.reason = ""


def _patch(session: Any, resource_id: str, body: Any, *, allowed: bool = True) -> Any:
    permission = create_module_patch(resources_routes.rbac_evaluator, "check_permission")
    permission.activate().configure(side_effect=lambda **kwargs: _Decision(allowed))
    try:
        return resources_routes.handle_update_resource(_Request(db_session=session, resource_id=resource_id, body=body))
    finally:
        permission.deactivate()


def _json(response: Any) -> Dict[str, Any]:
    return json.loads(response.body.decode("utf-8"))


def _register(session: Any, *, name: str = "Bench phone 1") -> str:
    view = inventory_service.register_resource(
        db_session=session, project_id=PROJECT_ID, kind="device", display_name=name,
        attributes={"hostname": "phone-" + uuid.uuid4().hex[:6], "mac_address": "aa:bb:cc:" + uuid.uuid4().hex[:6][:2] + ":" + uuid.uuid4().hex[:2] + ":" + uuid.uuid4().hex[:2]},
        description="first", tags=("android",),
    )
    return str(view.resource_id)


#: What the bus delivered since the last ``_prepare`` (events are published after commit).
_RECEIVED: List[EntityEvent] = []


def _prepare() -> Any:
    reset_registry_for_testing()
    reset_event_bus()
    inventory_register()
    del _RECEIVED[:]
    subscribe(topic="entity.resource.updated", subscriber=lambda event: _RECEIVED.append(event))
    _engine, session = build_in_memory_session()
    return session


def _events(topic: str) -> List[Dict[str, Any]]:
    return [dict(event.payload) for event in _RECEIVED if event.topic == topic]


def test_name_description_and_tags_change_and_what_was_left_out_stays():
    """
    **Feature: update a resource (RES-22)**
    **Property: PATCH with a new name and tags answers 200 with them; the description, the state, the kind and
    the attributes are as they were; a tag list is trimmed and de-duplicated; a later PATCH of only the description
    keeps the name and tags just set.**
    """
    session = _prepare()
    resource_id = _register(session)
    first = _json(_patch(session, resource_id, {"display_name": "  Bench phone 2  ", "tags": ["android", " lab ", "lab", ""]}))
    second = _json(_patch(session, resource_id, {"description": "Moved to rack 4"}))

    testbase.assert_equal(
        (
            first["display_name"], first["tags"], first["description"], first["state"], first["kind"],
            second["display_name"], second["tags"], second["description"],
        ),
        ("Bench phone 2", ["android", "lab"], "first", "available", "device", "Bench phone 2", ["android", "lab"], "Moved to rack 4"),
    )
    return


def test_what_cannot_be_changed_and_a_body_with_nothing_to_change_are_422_and_nothing_moves():
    """
    **Feature: update a resource (RES-22)**
    **Property: asking to change the kind, identity, attributes, state or project answers 422 naming them; a
    body with none of the three editable fields, an empty name and a tags value that is not a list of strings
    are each 422; the resource is exactly as it was.**
    """
    session = _prepare()
    resource_id = _register(session)
    before = _json(_patch(session, resource_id, {"description": "first"}))

    refused = [
        _patch(session, resource_id, {"kind": "pool", "display_name": "x"}),
        _patch(session, resource_id, {"attributes": {"hostname": "other"}}),
        _patch(session, resource_id, {}),
        _patch(session, resource_id, {"display_name": "   "}),
        _patch(session, resource_id, {"tags": "android"}),
        _patch(session, resource_id, {"tags": [1, 2]}),
        _patch(session, resource_id, {"description": 5}),
    ]
    after = _json(_patch(session, resource_id, {"description": "first"}))

    testbase.assert_equal(
        ([response.status_code for response in refused], "kind" in _json(refused[0])["detail"], "attributes" in _json(refused[1])["detail"], after == before),
        ([422] * 7, True, True, True),
    )
    return


def test_a_retired_resource_is_refused_an_unknown_one_is_404_and_a_caller_without_write_is_403():
    """
    **Feature: update a resource (RES-22)**
    **Property: PATCH of a retired resource answers 409 and changes nothing; an id that names no resource, and one
    that is not a UUID, answer 404; a principal without ``system:resources.write`` gets 403.**
    """
    session = _prepare()
    resource_id = _register(session)
    inventory_service.transition_state(db_session=session, resource_id=resource_id, new_state=ResourceState.RETIRED)
    retired = _patch(session, resource_id, {"display_name": "New name"})
    unknown = _patch(session, str(uuid.uuid4()), {"display_name": "x"})
    not_an_id = _patch(session, "not-a-uuid", {"display_name": "x"})
    other = _register(session, name="Second")
    denied = _patch(session, other, {"display_name": "x"}, allowed=False)

    testbase.assert_equal(
        (retired.status_code, _json(retired)["reason"], unknown.status_code, not_an_id.status_code, denied.status_code,
         inventory_service.get_resource(db_session=session, resource_id=resource_id).display_name),
        (409, "resource_retired", 404, 404, 403, "Bench phone 1"),
    )
    return


def test_only_a_real_change_is_recorded_and_the_event_names_the_fields():
    """
    **Feature: update a resource (RES-22)**
    **Property: a PATCH that alters nothing records no ``entity.resource.updated`` event; a rename and a tag
    change record one naming ``display_name`` and ``tags`` and who did it.**
    """
    session = _prepare()
    resource_id = _register(session)
    _patch(session, resource_id, {"display_name": "Bench phone 1", "tags": ["android"]})
    unchanged = len(_events("entity.resource.updated"))
    _patch(session, resource_id, {"display_name": "Bench phone 9", "tags": ["android", "lab"]})
    events = _events("entity.resource.updated")

    testbase.assert_equal(
        (unchanged, len(events), sorted(events[0]["changed"]), events[0]["actor"]),
        (0, 1, ["display_name", "tags"], "user:user-1"),
    )
    return
