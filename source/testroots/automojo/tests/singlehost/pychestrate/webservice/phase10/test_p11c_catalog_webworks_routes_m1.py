"""
.. module:: test_p11c_catalog_webworks_routes_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the webworks-native plugin-api meta routes.

.. moduleauthor:: Automation Mojo LLC

The catalog port is the third feature ported to webworks (after
flags in #115 and audit in #120). Catalog handlers are read-only
views over in-process state — no SQLAlchemy session, no actor
lookup, no auth gate — so the tests stub
``plugin_api_runtime.get_active_catalog`` and
``ext_router.mount_extension_routes`` and assert on the response
shape directly.

Tests cover:

* Route matrix matches the flask_restx ``catalog_controller`` (3
  method+path pairs).
* Each handler's success path produces the documented JSON shape.
* The detail endpoint returns a 404 problem document with the
  protocol name as an extension member when no entry matches —
  upgrading the flask controller's plain ``ns.abort(404)`` body to
  RFC 7807.
* Bootstrap source-smoke: register_catalog_routes is wired in
  ``register_service_extensions``.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import json

from typing import Any, Callable, Dict, List, Optional, Tuple

from automojo import testbase
from automojo.testbase.mocking import create_module_patch
from automojo.webworks.routing.response import JSONResponse

from automojo.pychestrate.webservice.api.problem_json import (
    PROBLEM_JSON_MEDIA_TYPE,
    PROBLEM_TYPE_NOT_FOUND,
)
from automojo.pychestrate.webservice.extensions import ext_router as ext_router_module
from automojo.pychestrate.webservice.plugin_api import runtime as plugin_api_runtime_module
from automojo.pychestrate.webservice.plugin_api.restapi.v1 import catalog_routes


# ---------------------------------------------------------------------------
# Test stubs
# ---------------------------------------------------------------------------


class _FakeRequest:
    """
        Minimal duck-typed Request. Catalog handlers only touch
        ``path`` and ``path_params``.
    """

    def __init__(
        self,
        *,
        path: str,
        path_params: Optional[Dict[str, Any]] = None
    ) -> None:
        self.path: str = path
        self.path_params: Dict[str, Any] = path_params if path_params is not None else {}
        return


class _FakeApp:
    """
        Stand-in for a webworks application; records
        ``attach_route(path, methods=...)`` calls.
    """

    def __init__(self) -> None:
        self.calls: List[Tuple[str, Tuple[str, ...], Callable]] = []
        return

    def attach_route(
        self, path: str, methods: Optional[List[str]] = None
    ) -> Callable:
        resolved_methods = tuple(methods if methods is not None else ["GET"])

        def decorator(func: Callable) -> Callable:
            self.calls.append((path, resolved_methods, func))
            rtnval = func
            return rtnval

        rtnval = decorator
        return rtnval


def _decode_body(response: Any) -> Any:
    body_text = response.body.decode("utf-8")
    rtnval = json.loads(body_text)
    return rtnval


def _make_catalog_jsonable() -> Dict[str, Any]:
    """
        Build a representative ``catalog_to_jsonable`` return dict for
        stubbing. Two factory-protocol entries and one
        resource-extension entry — enough surface to exercise the
        detail-lookup loop in both branches.
    """
    rtnval = {
        "factory_protocols": [
            {
                "name": "FactoryAlpha",
                "kind": "factory_protocol",
                "protocol_schema_version": 1,
                "min_schema_version": 1,
                "status": "supported",
                "deprecation_date": None,
                "sunset_date": None,
                "docs_url": "https://docs.example.com/alpha",
                "reference": "automojo.pkg.alpha:Alpha",
                "declaring_class": "automojo.pkg.alpha.Alpha",
            },
            {
                "name": "FactoryBeta",
                "kind": "factory_protocol",
                "protocol_schema_version": 2,
                "min_schema_version": 1,
                "status": "supported",
                "deprecation_date": None,
                "sunset_date": None,
                "docs_url": "https://docs.example.com/beta",
                "reference": "automojo.pkg.beta:Beta",
                "declaring_class": "automojo.pkg.beta.Beta",
            },
        ],
        "resource_extensions": [
            {
                "name": "ResourceGamma",
                "kind": "resource_extension",
                "protocol_schema_version": 1,
                "min_schema_version": 1,
                "status": "supported",
                "deprecation_date": None,
                "sunset_date": None,
                "docs_url": "https://docs.example.com/gamma",
                "reference": "automojo.pkg.gamma:Gamma",
                "declaring_class": "automojo.pkg.gamma.Gamma",
            },
        ],
    }
    return rtnval


def _patch_catalog(*, jsonable: Dict[str, Any]) -> Tuple[Any, Any]:
    """
        Patch ``plugin_api_runtime.get_active_catalog`` to return a
        sentinel and ``catalog_builder.catalog_to_jsonable`` (via the
        catalog_routes module's import) to return the supplied
        jsonable dict. Returns the two patches so callers can
        ``deactivate()`` in finally blocks.
    """
    # Patch get_active_catalog to return any sentinel — the routes
    # module passes its return value verbatim into catalog_to_jsonable
    # which we are also patching, so the actual catalog object never
    # gets read.
    catalog_patch = create_module_patch(
        plugin_api_runtime_module, "get_active_catalog"
    )
    mock_get = catalog_patch.activate()
    mock_get.configure(return_value=object())

    jsonable_patch = create_module_patch(
        catalog_routes, "catalog_to_jsonable"
    )
    mock_jsonable = jsonable_patch.activate()
    mock_jsonable.configure(return_value=jsonable)

    rtnval = (catalog_patch, jsonable_patch)
    return rtnval


# ---------------------------------------------------------------------------
# Route registration matrix
# ---------------------------------------------------------------------------


def test_register_catalog_routes_attaches_three_routes_under_version_prefix():
    """
    **Feature: 8-plugin-api T1.5 (webworks routes)**
    **Property: register_catalog_routes attaches the same three
    method+path pairs the flask_restx controller exposed.**
    """
    app = _FakeApp()
    catalog_routes.register_catalog_routes(app=app, version_prefix="/api/v1")

    expected_pairs = (
        ("/api/v1/plugin-api/_meta/catalog", ("GET",)),
        ("/api/v1/plugin-api/_meta/catalog/{protocol_name}", ("GET",)),
        ("/api/v1/plugin-api/_meta/mounts", ("GET",)),
    )
    actual_pairs = tuple((path, methods) for path, methods, _ in app.calls)
    testbase.assert_equal(actual_pairs, expected_pairs)
    return


def test_register_catalog_routes_declares_fixed_catalog_before_parameterized():
    """
    **Feature: 8-plugin-api T1.5 (webworks routes)**
    **Property: Fixed ``/catalog`` is registered before the
    parameterized ``/catalog/{protocol_name}`` route. Without that
    ordering, the webworks router could match
    ``GET /api/v1/plugin-api/_meta/catalog`` to
    :func:`handle_read_catalog_entry` with an empty path param.**
    """
    app = _FakeApp()
    catalog_routes.register_catalog_routes(app=app, version_prefix="/api/v1")

    fixed_index = None
    parameterized_index = None
    for index, (path, _, _) in enumerate(app.calls):
        if path == "/api/v1/plugin-api/_meta/catalog" and fixed_index is None:
            fixed_index = index
        if (
            path == "/api/v1/plugin-api/_meta/catalog/{protocol_name}"
            and parameterized_index is None
        ):
            parameterized_index = index

    testbase.assert_equal(fixed_index is not None, True)
    testbase.assert_equal(parameterized_index is not None, True)
    testbase.assert_equal(fixed_index < parameterized_index, True)
    return


# ---------------------------------------------------------------------------
# handle_list_catalog
# ---------------------------------------------------------------------------


def test_handle_list_catalog_returns_full_catalog_dict():
    """
    **Feature: 8-plugin-api T1.5 (webworks routes)**
    **Property: Returns 200 with a JSON dict shaped as
    ``{factory_protocols, resource_extensions}`` derived from
    ``catalog_to_jsonable(catalog=get_active_catalog())``.**
    """
    jsonable = _make_catalog_jsonable()
    catalog_patch, jsonable_patch = _patch_catalog(jsonable=jsonable)
    try:
        request = _FakeRequest(path="/api/v1/plugin-api/_meta/catalog")
        response = catalog_routes.handle_list_catalog(request)
    finally:
        catalog_patch.deactivate()
        jsonable_patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(len(body["factory_protocols"]), 2)
    testbase.assert_equal(len(body["resource_extensions"]), 1)
    testbase.assert_equal(body["factory_protocols"][0]["name"], "FactoryAlpha")
    testbase.assert_equal(body["resource_extensions"][0]["name"], "ResourceGamma")
    return


# ---------------------------------------------------------------------------
# handle_read_catalog_entry
# ---------------------------------------------------------------------------


def test_handle_read_catalog_entry_returns_factory_protocol_match():
    """
    **Feature: 8-plugin-api T1.5 (webworks routes)**
    **Property: A protocol_name that matches an entry under
    factory_protocols returns 200 with the entry dict.**
    """
    jsonable = _make_catalog_jsonable()
    catalog_patch, jsonable_patch = _patch_catalog(jsonable=jsonable)
    try:
        request = _FakeRequest(
            path="/api/v1/plugin-api/_meta/catalog/FactoryBeta",
            path_params={"protocol_name": "FactoryBeta"},
        )
        response = catalog_routes.handle_read_catalog_entry(request)
    finally:
        catalog_patch.deactivate()
        jsonable_patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(body["name"], "FactoryBeta")
    testbase.assert_equal(body["kind"], "factory_protocol")
    testbase.assert_equal(body["protocol_schema_version"], 2)
    return


def test_handle_read_catalog_entry_returns_resource_extension_match():
    """
    **Feature: 8-plugin-api T1.5 (webworks routes)**
    **Property: A protocol_name that matches an entry under
    resource_extensions returns 200 with the entry dict — the lookup
    walks both lists.**
    """
    jsonable = _make_catalog_jsonable()
    catalog_patch, jsonable_patch = _patch_catalog(jsonable=jsonable)
    try:
        request = _FakeRequest(
            path="/api/v1/plugin-api/_meta/catalog/ResourceGamma",
            path_params={"protocol_name": "ResourceGamma"},
        )
        response = catalog_routes.handle_read_catalog_entry(request)
    finally:
        catalog_patch.deactivate()
        jsonable_patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(body["name"], "ResourceGamma")
    testbase.assert_equal(body["kind"], "resource_extension")
    return


def test_handle_read_catalog_entry_returns_404_with_protocol_name_extension():
    """
    **Feature: 8-plugin-api T1.5 (webworks routes)**
    **Property: An unknown protocol_name returns 404 problem+json
    carrying the protocol name as an extension member. Upgrades the
    flask_restx ``ns.abort(404, ...)`` body (which produced
    ``{"message": "..."}``) to the documented RFC 7807 shape.**
    """
    jsonable = _make_catalog_jsonable()
    catalog_patch, jsonable_patch = _patch_catalog(jsonable=jsonable)
    try:
        request = _FakeRequest(
            path="/api/v1/plugin-api/_meta/catalog/Unknown",
            path_params={"protocol_name": "Unknown"},
        )
        response = catalog_routes.handle_read_catalog_entry(request)
    finally:
        catalog_patch.deactivate()
        jsonable_patch.deactivate()

    testbase.assert_equal(response.status_code, 404)
    testbase.assert_equal(
        response.headers["Content-Type"], PROBLEM_JSON_MEDIA_TYPE
    )
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_NOT_FOUND)
    testbase.assert_equal(body["protocol_name"], "Unknown")
    testbase.assert_equal(body["instance"], "/api/v1/plugin-api/_meta/catalog/Unknown")
    return


# ---------------------------------------------------------------------------
# handle_list_mounts
# ---------------------------------------------------------------------------


def test_handle_list_mounts_returns_serialized_manifest():
    """
    **Feature: 8-plugin-api T1.5 (webworks routes)**
    **Property: Returns 200 with the JSON list of mount entries
    derived from ``manifest_to_jsonable(mount_extension_routes(...))``.
    Mirrors the flask controller's wire shape — a list of dicts, not
    a wrapper object.**
    """
    manifest_jsonable = [
        {
            "ext_name": "echo",
            "method": "GET",
            "path_suffix": "/ping",
            "full_path": "/api/v1/ext/echo/ping",
            "handler_class": "automojo.example.EchoEndpoint",
            "required_permissions": [],
            "required_capabilities": [],
            "description": "Example echo endpoint.",
        },
    ]
    mount_patch = create_module_patch(catalog_routes, "mount_extension_routes")
    jsonable_patch = create_module_patch(catalog_routes, "manifest_to_jsonable")
    try:
        mock_mount = mount_patch.activate()
        mock_mount.configure(return_value=object())
        mock_jsonable = jsonable_patch.activate()
        mock_jsonable.configure(return_value=manifest_jsonable)

        request = _FakeRequest(path="/api/v1/plugin-api/_meta/mounts")
        response = catalog_routes.handle_list_mounts(request)
    finally:
        jsonable_patch.deactivate()
        mount_patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(len(body), 1)
    testbase.assert_equal(body[0]["ext_name"], "echo")
    testbase.assert_equal(body[0]["full_path"], "/api/v1/ext/echo/ping")
    return


def test_handle_list_mounts_invokes_mount_extension_routes_with_none():
    """
    **Feature: 8-plugin-api T1.5 (webworks routes)**
    **Property: ``mount_extension_routes`` is called with
    ``extensions=None`` (the discover-from-registry path), matching
    the flask controller's behavior. Passing a list would short the
    discovery and return only the supplied items.**
    """
    mount_patch = create_module_patch(catalog_routes, "mount_extension_routes")
    jsonable_patch = create_module_patch(catalog_routes, "manifest_to_jsonable")
    try:
        mock_mount = mount_patch.activate()
        mock_mount.configure(return_value=object())
        mock_jsonable = jsonable_patch.activate()
        mock_jsonable.configure(return_value=[])

        request = _FakeRequest(path="/api/v1/plugin-api/_meta/mounts")
        catalog_routes.handle_list_mounts(request)

        positional_args, keyword_args = mock_mount.call_args_list[0]
        testbase.assert_equal(keyword_args["extensions"], None)
    finally:
        jsonable_patch.deactivate()
        mount_patch.deactivate()
    return


# ---------------------------------------------------------------------------
# Bootstrap source-smoke
# ---------------------------------------------------------------------------


def test_bootstrap_imports_register_catalog_routes_and_calls_it():
    """
    **Feature: 8-plugin-api T1.5 (webworks routes)**
    **Property: app_pychestrate_main.py wires
    register_catalog_routes into register_service_extensions so the
    routes are queued before app.startup. Source-level smoke; full
    app boot is out of scope for the singlehost suite.**
    """
    import os

    here = os.path.dirname(os.path.abspath(__file__))
    repo_source_root = os.path.normpath(
        os.path.join(
            here, "..", "..", "..", "..", "..", "..", "..", "..",
            "source", "site",
        )
    )
    bootstrap_path = os.path.join(repo_source_root, "app_pychestrate_main.py")
    with open(bootstrap_path, "r", encoding="utf-8") as fh:
        text = fh.read()

    has_import = (
        "from automojo.pychestrate.webservice.plugin_api.restapi.v1.catalog_routes import"
        in text
    )
    has_call = "register_catalog_routes(app=app, version_prefix=\"/api/v1\")" in text
    testbase.assert_equal(has_import, True)
    testbase.assert_equal(has_call, True)
    return


# ---------------------------------------------------------------------------
# Wire-shape: 404 problem+json + JSONResponse
# ---------------------------------------------------------------------------


def test_404_response_round_trips_through_real_json_response():
    """
    **Feature: 8-plugin-api T1.5 (webworks routes)**
    **Property: The 404 problem+json response is a real
    JSONResponse so the dispatcher serializes it correctly. Catches
    any drift between problem_json_webworks and JSONResponse.**
    """
    jsonable = _make_catalog_jsonable()
    catalog_patch, jsonable_patch = _patch_catalog(jsonable=jsonable)
    try:
        request = _FakeRequest(
            path="/api/v1/plugin-api/_meta/catalog/Nope",
            path_params={"protocol_name": "Nope"},
        )
        response = catalog_routes.handle_read_catalog_entry(request)
    finally:
        catalog_patch.deactivate()
        jsonable_patch.deactivate()

    is_json_response = isinstance(response, JSONResponse)
    testbase.assert_equal(is_json_response, True)
    testbase.assert_equal(
        response.headers["Content-Type"], PROBLEM_JSON_MEDIA_TYPE
    )
    return
