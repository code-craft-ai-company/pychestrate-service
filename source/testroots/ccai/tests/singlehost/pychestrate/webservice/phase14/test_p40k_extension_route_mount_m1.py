"""
.. module:: test_p40k_extension_route_mount_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests that extension REST routes are mounted and guarded.

.. moduleauthor:: Code Craft AI LLC

Audit finding CLI-01: the server listed the example extension's
``GET /api/v1/ext/example/echo`` route but never mounted it
(``dynamic_mount: deferred``), so ``pyc ext example echo`` could not work
and no extension could contribute a working REST route. The host now
mounts every route whose extension names a handler, and checks the
caller, the route's permissions and the extension's sandbox capability
grants on every request.

**Feature: plugin API (CLI-01 extension routes)**
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json

from typing import Any, Callable, Dict, List, Optional, Tuple

from ccai import testbase
from ccai.testbase.mocking import create_module_patch

from ccai.pychestrate.webservice.extensions.ext_router import mount_extension_routes
from ccai.pychestrate.webservice.extensions.rest_endpoint_example import ExampleEchoEndpoints
from ccai.pychestrate.webservice.extensions.rest_endpoint_protocol import (
    HTTP_METHOD_GET,
    RestEndpointDescriptor,
    RestEndpointExtension,
)
from ccai.pychestrate.webservice.extensions.sandbox.authority import get_capability_authority
from ccai.pychestrate.webservice.plugin_api.restapi.v1 import catalog_routes, ext_mount_routes
from ccai.pychestrate.webservice.security.rbac import rbac_evaluator


class _App:
    """
        Records ``attach_route`` calls like the webworks application.
    """

    def __init__(self) -> None:
        self.routes: Dict[Tuple[str, str], Callable] = {}
        return

    def attach_route(self, path: str, methods: Optional[List[str]] = None) -> Callable:
        def decorator(func: Callable) -> Callable:
            for method in methods or ["GET"]:
                self.routes[(method, path)] = func
            return func
        return decorator


class _Query:
    def __init__(self, values: Optional[Dict[str, str]] = None) -> None:
        self._values = values or {}
        return

    def get(self, key: str, default: Any = None) -> Any:
        return self._values.get(key, default)


class _Request:
    def __init__(self, *, path: str, query: Optional[Dict[str, str]] = None, signed_in: bool = True) -> None:
        self.path = path
        self.query_params = _Query(query)
        self.auth_principal = object() if signed_in else None
        self.db_session = object()
        return


class _Decision:
    def __init__(self, allowed: bool) -> None:
        self.allowed = allowed
        return


def _body(response: Any) -> Dict[str, Any]:
    raw = getattr(response, "body", None) or getattr(response, "_body", b"")
    rtnval = json.loads(raw.decode("utf-8"))
    return rtnval


def _extension(*, ext_name: str, descriptor: RestEndpointDescriptor, handler: Optional[Callable] = None) -> type:
    """
        A throw-away extension class serving ``descriptor`` with
        ``handler`` (named ``serve``).
    """
    captured = descriptor

    class _Synthetic(RestEndpointExtension):
        @classmethod
        def declare_endpoints(cls) -> Tuple[RestEndpointDescriptor, ...]:
            return (captured,)

    _Synthetic.ext_name = ext_name
    if handler is not None:
        _Synthetic.serve = classmethod(lambda cls, *, request: handler(request))
    return _Synthetic


def _descriptor(*, permissions: Tuple[str, ...] = (), capabilities: Tuple[str, ...] = (),
                handler_name: str = "serve") -> RestEndpointDescriptor:
    rtnval = RestEndpointDescriptor(
        method=HTTP_METHOD_GET,
        path_suffix="/thing",
        required_permissions=permissions,
        required_capabilities=capabilities,
        description="",
        handler_name=handler_name,
    )
    return rtnval


def _mount(ext_class: type) -> Tuple[_App, Optional[Callable]]:
    app = _App()
    ext_mount_routes.attach_extension_routes(app=app, manifest=mount_extension_routes(extensions=[ext_class]))
    rtnval = (app, app.routes.get(("GET", "/api/v1/ext/{}/thing".format(ext_class.ext_name))))
    return rtnval


def test_the_example_echo_route_is_mounted_and_echoes():
    """
    **Feature: plugin API (CLI-01 extension routes)**
    **Property: the in-tree example's GET /api/v1/ext/example/echo is
    mounted and answers {"message": ...} for a signed-in caller.**
    """
    app = _App()
    ext_mount_routes.attach_extension_routes(
        app=app, manifest=mount_extension_routes(extensions=[ExampleEchoEndpoints]),
    )
    handler = app.routes[("GET", "/api/v1/ext/example/echo")]
    response = handler(_Request(path="/api/v1/ext/example/echo", query={"message": "hello"}))
    testbase.assert_equal((response.status_code, _body(response)), (200, {"message": "hello"}))
    return


def test_an_anonymous_request_to_an_extension_route_is_401():
    """
    **Feature: plugin API (CLI-01 extension routes)**
    **Property: a request without a principal never reaches the
    extension.**
    """
    calls: List[Any] = []
    _, handler = _mount(_extension(ext_name="anon-check", descriptor=_descriptor(),
                                   handler=lambda request: calls.append(request) or {}))
    response = handler(_Request(path="/api/v1/ext/anon-check/thing", signed_in=False))
    testbase.assert_equal((response.status_code, calls), (401, []))
    return


def test_a_route_permission_the_caller_lacks_is_403():
    """
    **Feature: plugin API (CLI-01 extension routes)**
    **Property: a caller without one of the descriptor's
    required_permissions is answered 403 naming it, and the extension is
    not called.**
    """
    calls: List[Any] = []
    _, handler = _mount(_extension(ext_name="perm-check", descriptor=_descriptor(permissions=("system:lab.read",)),
                                   handler=lambda request: calls.append(request) or {}))
    patch = create_module_patch(rbac_evaluator, "check_permission")
    patch.activate().configure(side_effect=lambda *, db_session, principal, permission_key, now: _Decision(False))
    try:
        response = handler(_Request(path="/api/v1/ext/perm-check/thing"))
    finally:
        patch.deactivate()
    testbase.assert_equal(
        (response.status_code, _body(response).get("required_permission"), calls), (403, "system:lab.read", []),
    )
    return


def test_a_capability_the_extension_was_not_granted_is_403_until_granted():
    """
    **Feature: plugin API (CLI-01 extension routes)**
    **Property: a route needing a sandbox capability answers 403 until the
    extension is granted it, and then serves the request.**
    """
    authority = get_capability_authority()
    capability = sorted(authority.vocabulary)[0]
    _, handler = _mount(_extension(ext_name="cap-check", descriptor=_descriptor(capabilities=(capability,)),
                                   handler=lambda request: {"ok": True}))
    before = handler(_Request(path="/api/v1/ext/cap-check/thing"))
    authority.grant_capability_in_memory(ext_name="cap-check", capability=capability)
    try:
        after = handler(_Request(path="/api/v1/ext/cap-check/thing"))
    finally:
        authority.revoke_capability_in_memory(ext_name="cap-check", capability=capability)
    testbase.assert_equal((before.status_code, after.status_code), (403, 200))
    return


def test_a_descriptor_without_a_handler_is_listed_but_not_mounted():
    """
    **Feature: plugin API (CLI-01 extension routes)**
    **Property: a descriptor naming no handler the extension has is not
    attached to the app.**
    """
    app, handler = _mount(_extension(ext_name="no-handler", descriptor=_descriptor(handler_name="")))
    testbase.assert_equal((handler, len(app.routes)), (None, 0))
    return


def test_an_extension_that_raises_answers_500_without_its_error_text():
    """
    **Feature: plugin API (CLI-01 extension routes)**
    **Property: an exception inside an extension becomes a 500 problem
    document that does not echo the exception's text.**
    """
    def explode(request: Any) -> Any:
        raise RuntimeError("database password is hunter2")

    _, handler = _mount(_extension(ext_name="boom", descriptor=_descriptor(), handler=explode))
    response = handler(_Request(path="/api/v1/ext/boom/thing"))
    testbase.assert_equal(
        (response.status_code, "hunter2" in json.dumps(_body(response))), (500, False),
    )
    return


def test_the_listing_reports_the_mounted_routes():
    """
    **Feature: plugin API (CLI-01 extension routes)**
    **Property: once the catalog routes are registered, GET /api/v1/ext
    reports dynamic_mount "mounted" and marks the example route mounted.**
    """
    ext_mount_routes.reset_extension_mounts_for_testing()
    catalog_routes.register_catalog_routes(app=_App(), version_prefix="/api/v1")
    patch = create_module_patch(rbac_evaluator, "check_permission")
    patch.activate().configure(side_effect=lambda *, db_session, principal, permission_key, now: _Decision(True))
    try:
        response = catalog_routes.handle_list_ext(_Request(path="/api/v1/ext"))
    finally:
        patch.deactivate()
    body = _body(response)
    example = [item for item in body["items"] if item["full_path"] == "/api/v1/ext/example/echo"]
    testbase.assert_equal(
        (body["dynamic_mount"], [item["mounted"] for item in example]), ("mounted", [True]),
    )
    return
