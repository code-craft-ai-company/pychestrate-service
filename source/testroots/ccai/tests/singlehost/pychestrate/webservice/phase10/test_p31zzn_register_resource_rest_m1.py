"""
.. module:: test_p31zzn_register_resource_rest_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: A resource can be registered and listed over REST (RES-04).

.. moduleauthor:: Code Craft AI LLC

``register_resource`` had no caller and the API had no create call, so no
resource existed, no pool could have a member, and no job could use a lab
resource. ``POST /api/v1/resources`` registers one (``201``; ``400`` for a kind
that is not loaded, naming the kinds that are; ``409`` for an identity that is
already registered; ``422`` when the kind refuses the attributes) and
``GET /api/v1/resources?project_id=`` lists a project's resources. The handlers
run here against a real in-memory database with the in-tree device kind.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json

from typing import Any, Dict, List, Optional

from ccai import testbase
from ccai.testbase.mocking import create_module_patch

from ccai.pychestrate.webservice.extensions.registry import reset_registry_for_testing
from ccai.pychestrate.webservice.messaging.event_bus import reset_for_testing as reset_event_bus
from ccai.pychestrate.webservice.resources.inventory import register_builtin_extensions as inventory_register
from ccai.pychestrate.webservice.resources.restapi.v1 import resources_routes

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import build_in_memory_session


PROJECT_ID = "00000000-0000-4000-8000-0000000000b2"
OTHER_PROJECT_ID = "00000000-0000-4000-8000-0000000000b3"


class _Query:
    def __init__(self, values: Dict[str, str]) -> None:
        self._values = values

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        return self._values.get(key, default)


class _Request:
    def __init__(self, *, db_session: Any, body: Any = None, query: Optional[Dict[str, str]] = None) -> None:
        self.path = "/api/v1/resources"
        self.path_params: Dict[str, Any] = {}
        self.query_params = _Query(query or {})
        self.db_session = db_session
        self.auth_principal = type("Principal", (), {"user_id": "user-1"})()
        self._body = body

    def json(self) -> Any:
        return self._body


class _Decision:
    def __init__(self, allowed: bool) -> None:
        self.allowed = allowed
        self.reason = ""


def _call(handler: Any, *, session: Any, body: Any = None, query: Optional[Dict[str, str]] = None, allowed: bool = True) -> Any:
    patch = create_module_patch(resources_routes.rbac_evaluator, "check_permission")
    mock = patch.activate()
    mock.configure(side_effect=lambda **kwargs: _Decision(allowed))
    try:
        rtnval = handler(_Request(db_session=session, body=body, query=query))
    finally:
        patch.deactivate()
    return rtnval


def _prepare() -> Any:
    reset_registry_for_testing()
    reset_event_bus()
    inventory_register()
    _engine, session = build_in_memory_session()
    return session


def _json(response: Any) -> Dict[str, Any]:
    return json.loads(response.body.decode("utf-8"))


def _device(name: str = "Bench phone 1", **attributes: str) -> Dict[str, Any]:
    payload = {"hostname": "phone-01", "mac_address": "aa:bb:cc:dd:ee:01"}
    payload.update(attributes)
    return {"project_id": PROJECT_ID, "kind": "device", "display_name": name, "attributes": payload, "tags": ["android", "lab"]}


def test_a_device_is_registered_and_comes_back_with_its_id_state_and_tags():
    """
    **Feature: register a resource (RES-04)**
    **Property: ``POST /api/v1/resources`` with a device answers 201 with a
    resource id, the state "available", the normalised attributes and the tags.**
    """
    session = _prepare()
    response = _call(resources_routes.handle_register_resource, session=session, body=_device(hostname="  phone-01  "))
    body = _json(response)

    testbase.assert_equal(
        (response.status_code, len(body["resource_id"]), body["state"], body["attributes"]["hostname"], body["tags"], body["project_id"]),
        (201, 36, "available", "phone-01", ["android", "lab"], PROJECT_ID),
    )
    return


def test_registering_the_same_device_twice_is_a_409():
    """
    **Feature: register a resource (RES-04)**
    **Property: the second registration of the same hostname and MAC answers
    409 naming the kind.**
    """
    session = _prepare()
    _call(resources_routes.handle_register_resource, session=session, body=_device())
    response = _call(resources_routes.handle_register_resource, session=session, body=_device(name="Same phone again"))

    testbase.assert_equal((response.status_code, "already registered" in _json(response)["detail"]), (409, True))
    return


def test_an_unknown_kind_is_a_400_that_lists_the_loaded_kinds():
    """
    **Feature: register a resource (RES-04)**
    **Property: a kind nobody loaded answers 400; the detail names the kind
    and lists the loaded kinds (``device``).**
    """
    session = _prepare()
    body = _device()
    body["kind"] = "toaster"
    response = _call(resources_routes.handle_register_resource, session=session, body=body)
    problem = _json(response)

    testbase.assert_equal(
        (response.status_code, "toaster" in problem["detail"], "device" in problem["detail"], problem.get("loaded_kinds")),
        (400, True, True, ["device"]),
    )
    return


def test_attributes_the_kind_refuses_are_a_422_not_a_crash():
    """
    **Feature: register a resource (RES-04)**
    **Property: an attribute the kind does not know, and a device with no
    hostname, each answer 422 (the kind's error is a ``BaseException``, which
    ``except Exception`` would let through as a 500).**
    """
    session = _prepare()
    unknown = _call(resources_routes.handle_register_resource, session=session, body=_device(colour="red"))
    no_host = _device()
    no_host["attributes"] = {"vendor": "ACME"}
    missing = _call(resources_routes.handle_register_resource, session=session, body=no_host)

    testbase.assert_equal((unknown.status_code, missing.status_code), (422, 422))
    return


def test_a_malformed_request_is_a_422_and_the_wrong_permission_is_a_403():
    """
    **Feature: register a resource (RES-04)**
    **Property: a missing display name, a project id that is not a UUID and
    tags that are not strings each answer 422; a caller without the write
    permission gets 403 and nothing is registered.**
    """
    session = _prepare()
    no_name = _device()
    no_name["display_name"] = "  "
    bad_project = _device()
    bad_project["project_id"] = "not-a-uuid"
    bad_tags = _device()
    bad_tags["tags"] = "android"
    denied = _call(resources_routes.handle_register_resource, session=session, body=_device(), allowed=False)
    listed = _json(_call(resources_routes.handle_list_resources, session=session, query={"project_id": PROJECT_ID}))

    testbase.assert_equal(
        (
            _call(resources_routes.handle_register_resource, session=session, body=no_name).status_code,
            _call(resources_routes.handle_register_resource, session=session, body=bad_project).status_code,
            _call(resources_routes.handle_register_resource, session=session, body=bad_tags).status_code,
            denied.status_code,
            listed["meta"]["total"],
        ),
        (422, 422, 422, 403, 0),
    )
    return


def test_the_list_is_per_project_and_filters_by_kind_state_and_tag():
    """
    **Feature: register a resource (RES-04)**
    **Property: ``GET /api/v1/resources?project_id=`` lists only that
    project's resources; ``tag`` narrows by tag, ``state`` by lifecycle
    state; the ``project_id`` is required (400) and must be a UUID.**
    """
    session = _prepare()
    _call(resources_routes.handle_register_resource, session=session, body=_device(name="A", hostname="a", mac_address="00:00:00:00:00:0a"))
    other_tags = _device(name="B", hostname="b", mac_address="00:00:00:00:00:0b")
    other_tags["tags"] = ["ios"]
    _call(resources_routes.handle_register_resource, session=session, body=other_tags)
    elsewhere = _device(name="C", hostname="c", mac_address="00:00:00:00:00:0c")
    elsewhere["project_id"] = OTHER_PROJECT_ID
    _call(resources_routes.handle_register_resource, session=session, body=elsewhere)

    def names(**query: str) -> List[str]:
        response = _call(resources_routes.handle_list_resources, session=session, query=dict({"project_id": PROJECT_ID}, **query))
        return [item["display_name"] for item in _json(response)["items"]]

    testbase.assert_equal(
        (
            names(),
            names(tag="ios"),
            names(state="available"),
            names(state="quarantined"),
            _call(resources_routes.handle_list_resources, session=session, query={}).status_code,
            _call(resources_routes.handle_list_resources, session=session, query={"project_id": "x"}).status_code,
            _call(resources_routes.handle_list_resources, session=session, query={"project_id": PROJECT_ID, "state": "bogus"}).status_code,
        ),
        (["A", "B"], ["B"], ["A", "B"], [], 400, 400, 400),
    )
    return
