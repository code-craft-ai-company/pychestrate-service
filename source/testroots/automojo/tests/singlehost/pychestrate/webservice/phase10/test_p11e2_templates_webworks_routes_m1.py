"""
.. module:: test_p11e2_templates_webworks_routes_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the webworks-native project-templates routes.

.. moduleauthor:: Automation Mojo LLC

The templates port is read-only and has no SQLAlchemy session
dependency -- the service layer reads the in-process template
registry. Tests cover the route matrix, the list happy path, the
detail happy path, the 404 path with template_id extension, and
the bootstrap source-smoke.
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
from automojo.pychestrate.webservice.project_templates import (
    service as template_service_module,
)
from automojo.pychestrate.webservice.project_templates.exceptions import (
    TemplateNotRegisteredError,
)
from automojo.pychestrate.webservice.project_templates.restapi.v1 import (
    templates_routes,
)


class _FakeRequest:
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


class _FakeSummary:
    def __init__(
        self,
        *,
        template_id: str,
        template_version: str = "1.0.0",
        display_name: str = "Display",
        description: str = "Desc",
        variable_count: int = 0,
        tag_count: int = 0,
        notification_rule_count: int = 0,
        recommended_roles: Optional[List[str]] = None,
    ) -> None:
        self.template_id: str = template_id
        self.template_version: str = template_version
        self.display_name: str = display_name
        self.description: str = description
        self.variable_count: int = variable_count
        self.tag_count: int = tag_count
        self.notification_rule_count: int = notification_rule_count
        self.recommended_roles: List[str] = recommended_roles if recommended_roles is not None else []
        return


def _decode_body(response: Any) -> Any:
    body_text = response.body.decode("utf-8")
    rtnval = json.loads(body_text)
    return rtnval


def _raises(exc: BaseException) -> Callable[..., Any]:
    def side(*args: Any, **kwargs: Any) -> Any:
        raise exc

    rtnval = side
    return rtnval


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------


def test_register_templates_routes_attaches_two_routes():
    """
    **Feature: 2-project-templates T1.1 (webworks routes)**
    **Property: register_templates_routes attaches the same two
    method+path pairs the flask_restx controller exposed.**
    """
    app = _FakeApp()
    templates_routes.register_templates_routes(
        app=app, version_prefix="/api/v1"
    )

    expected_pairs = (
        ("/api/v1/project-templates", ("GET",)),
        ("/api/v1/project-templates/{template_id}", ("GET",)),
    )
    actual_pairs = tuple((path, methods) for path, methods, _ in app.calls)
    testbase.assert_equal(actual_pairs, expected_pairs)
    return


# ---------------------------------------------------------------------------
# handle_list_templates
# ---------------------------------------------------------------------------


def test_handle_list_returns_serialized_template_summaries():
    """
    **Feature: 2-project-templates T1.1 (webworks routes)**
    **Property: Returns 200 with a JSON list of template summary
    dicts derived from ``template_service.list_templates()``.**
    """
    summaries = [
        _FakeSummary(
            template_id="tmpl-a",
            display_name="Alpha",
            recommended_roles=["admin", "developer"],
        ),
        _FakeSummary(template_id="tmpl-b", display_name="Beta"),
    ]
    list_patch = create_module_patch(
        template_service_module, "list_templates"
    )
    try:
        mock_list = list_patch.activate()
        mock_list.configure(return_value=summaries)
        request = _FakeRequest(path="/api/v1/project-templates")
        response = templates_routes.handle_list_templates(request)
    finally:
        list_patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(len(body), 2)
    testbase.assert_equal(body[0]["template_id"], "tmpl-a")
    testbase.assert_equal(body[0]["recommended_roles"], ["admin", "developer"])
    return


# ---------------------------------------------------------------------------
# handle_read_template
# ---------------------------------------------------------------------------


def test_handle_read_returns_summary_on_match():
    """
    **Feature: 2-project-templates T1.1 (webworks routes)**
    **Property: A known template_id returns 200 with the serialized
    summary dict.**
    """
    summary = _FakeSummary(template_id="tmpl-a", display_name="Alpha")
    read_patch = create_module_patch(
        template_service_module, "read_template"
    )
    try:
        mock_read = read_patch.activate()
        mock_read.configure(return_value=summary)
        request = _FakeRequest(
            path="/api/v1/project-templates/tmpl-a",
            path_params={"template_id": "tmpl-a"},
        )
        response = templates_routes.handle_read_template(request)
    finally:
        read_patch.deactivate()

    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(body["template_id"], "tmpl-a")
    testbase.assert_equal(body["display_name"], "Alpha")
    return


def test_handle_read_returns_404_with_template_id_extension():
    """
    **Feature: 2-project-templates T1.1 (webworks routes)**
    **Property: An unregistered template_id returns 404 problem+json
    with the template id as an extension member.**
    """
    read_patch = create_module_patch(
        template_service_module, "read_template"
    )
    try:
        mock_read = read_patch.activate()
        mock_read.configure(
            side_effect=_raises(TemplateNotRegisteredError("missing"))
        )
        request = _FakeRequest(
            path="/api/v1/project-templates/missing",
            path_params={"template_id": "missing"},
        )
        response = templates_routes.handle_read_template(request)
    finally:
        read_patch.deactivate()

    testbase.assert_equal(response.status_code, 404)
    testbase.assert_equal(
        response.headers["Content-Type"], PROBLEM_JSON_MEDIA_TYPE
    )
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_NOT_FOUND)
    testbase.assert_equal(body["template_id"], "missing")
    is_json_response = isinstance(response, JSONResponse)
    testbase.assert_equal(is_json_response, True)
    return


# ---------------------------------------------------------------------------
# Bootstrap source-smoke
# ---------------------------------------------------------------------------


def test_bootstrap_imports_register_templates_routes_and_calls_it():
    """
    **Feature: 2-project-templates T1.1 (webworks routes)**
    **Property: app_pychestrate_main.py wires
    register_templates_routes into register_service_extensions.**
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
        "from automojo.pychestrate.webservice.project_templates.restapi.v1.templates_routes import"
        in text
    )
    has_call = "register_templates_routes(app=app, version_prefix=\"/api/v1\")" in text
    testbase.assert_equal(has_import, True)
    testbase.assert_equal(has_call, True)
    return
