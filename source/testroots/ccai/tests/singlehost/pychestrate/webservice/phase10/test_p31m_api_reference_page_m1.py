"""
.. module:: test_p31m_api_reference_page_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the REST API explorer page
               ``GET /api/v1/_meta/docs`` (DOC-06), a Swagger UI.

.. moduleauthor:: Code Craft AI LLC

None of the 16 URLs an evaluator would try for the API reference was
served, although the service already served the OpenAPI document. ``GET /api/docs``
now shows the document with the Swagger UI that codecraftai-webworks ships, served
from this origin so the page works under the service's Content-Security-Policy
(which allows scripts from this origin only, so the starter script is a file of its
own), to any signed-in caller. It opens folded and grouped by path, and Try it out
sends requests as the person signed in. It lives under ``/api/v1/`` because only that
prefix resolves the session cookie; ``GET /api/docs`` redirects to it. It replaced a
read-only ReDoc page: behind the same sign-in, read-only protected nothing.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import os
import re

from typing import Any, Dict, Optional

from ccai import testbase

from ccai.pychestrate.webservice.api import openapi_document
from ccai.pychestrate.webservice.security.auth.models import AuthProviderKind
from ccai.pychestrate.webservice.security.auth.session_service import AuthPrincipal

from ccai.tests.singlehost.pychestrate.webservice.shared.webworks_test_harness import (
    make_fake_app,
)


class _FakeRequest:
    def __init__(self, *, path: str, auth_principal: Optional[Any], path_params: Optional[Dict[str, str]] = None) -> None:
        self.path = path
        self.auth_principal = auth_principal
        self.path_params = path_params if path_params is not None else {}
        self.db_session = None
        return


def _principal() -> AuthPrincipal:
    rtnval = AuthPrincipal(
        user_id="u-1", session_id="s-1", provider_kind=AuthProviderKind.LOCAL, provider_name="local",
    )
    return rtnval


PAGE_PATH: str = "/api/v1/_meta/docs"
ASSET_PATTERN: str = "/api/v1/_meta/docs/assets/{filename}"
ASSET_DIRECTORY: str = "/api/v1/_meta/docs/assets"


def _app() -> Any:
    app = make_fake_app()
    openapi_document.register_api_docs_routes(app=app, version_prefix="/api/v1")
    return app


def _page(*, principal: Optional[Any]) -> Any:
    handler = _app().find_handler(path=PAGE_PATH, method="GET")
    rtnval = handler(_FakeRequest(path=PAGE_PATH, auth_principal=principal))
    return rtnval


def _asset(*, filename: str, principal: Optional[Any]) -> Any:
    # The fake app records the route pattern, not a concrete path.
    handler = _app().find_handler(path=ASSET_PATTERN, method="GET")
    path = "/api/v1/_meta/docs/assets/{}".format(filename)
    rtnval = handler(_FakeRequest(path=path, auth_principal=principal, path_params={"filename": filename}))
    return rtnval


def test_the_explorer_page_loads_swagger_ui_and_its_starter_from_this_origin():
    """
    **Feature: REST API explorer (DOC-06)**
    **Property: GET /api/v1/_meta/docs answers 200 HTML with the Swagger UI container and the library's script and style and the starter script all loaded from
    this origin, and no address on another host.**
    """
    response = _page(principal=_principal())
    html = response.body.decode("utf-8")

    testbase.assert_equal(
        (
            response.status_code, 'id="swagger-ui"' in html,
            'src="{}/swagger-ui-bundle.js"'.format(ASSET_DIRECTORY) in html, 'href="{}/swagger-ui.css"'.format(ASSET_DIRECTORY) in html,
            'src="{}/swagger-initializer.js"'.format(ASSET_DIRECTORY) in html, "http://" in html or "https://" in html,
        ),
        (200, True, True, True, True, False),
    )
    return


def test_the_explorer_page_holds_no_script_of_its_own():
    """
    **Feature: REST API explorer (DOC-06)**
    **Property: every ``<script>`` in the page has a ``src`` and no body, because the page's policy allows scripts from this origin only: an inline starter would be
    blocked and the page would stay empty.**
    """
    html = _page(principal=_principal()).body.decode("utf-8")
    scripts = re.findall(r"<script\b([^>]*)>(.*?)</script>", html, re.S)

    testbase.assert_equal((len(scripts), all("src=" in attributes and body.strip() == "" for attributes, body in scripts)), (2, True))
    return


def test_the_explorer_page_needs_a_signed_in_caller():
    """
    **Feature: REST API explorer (DOC-06)**
    **Property: an anonymous caller gets 401, as for the OpenAPI document the page reads.**
    """
    response = _page(principal=None)

    testbase.assert_equal(response.status_code, 401)
    return


def test_the_swagger_ui_files_are_served_from_this_origin_with_their_content_types():
    """
    **Feature: REST API explorer (DOC-06)**
    **Property: the bundled Swagger UI script, style and icon are served as JavaScript, CSS and PNG and are the real library (hundreds of kilobytes for the script).**
    """
    answers = {}
    for name in ("swagger-ui-bundle.js", "swagger-ui.css", "favicon-32x32.png"):
        response = _asset(filename=name, principal=_principal())
        answers[name] = (response.status_code, response.headers.get("Content-Type", ""), len(response.body) > 500)

    testbase.assert_equal(
        answers,
        {"swagger-ui-bundle.js": (200, "application/javascript", True), "swagger-ui.css": (200, "text/css", True), "favicon-32x32.png": (200, "image/png", True)},
    )
    return


def test_only_the_swagger_ui_files_and_the_starter_are_served_as_assets():
    """
    **Feature: REST API explorer (DOC-06)**
    **Property: any other name, including the old ReDoc script, a manifest and names that climb out of the asset directory, answers 404 and no file content.**
    """
    answers = []
    for name in ("redoc.standalone.js", "manifest.json", "../manifest.json", "..%2fmanifest.json", "../../static/manifest.json", "swagger-ui.css.map", ""):
        response = _asset(filename=name, principal=_principal())
        answers.append((response.status_code, len(response.body) > 10_000))

    testbase.assert_equal(answers, [(404, False)] * 7)
    return


def test_the_page_and_every_file_it_loads_need_a_signed_in_caller():
    """
    **Feature: REST API explorer (DOC-06)**
    **Property: an anonymous caller gets 401 for the library files and the starter too.**
    """
    answers = [_asset(filename=name, principal=None).status_code for name in ("swagger-ui-bundle.js", "swagger-ui.css", "swagger-initializer.js")]

    testbase.assert_equal(answers, [401, 401, 401])
    return


def test_the_address_people_try_first_redirects_to_the_page():
    """
    **Feature: REST API explorer (DOC-06)**
    **Property: GET /api/docs, which is outside the prefix that
    resolves a session, answers a redirect to the explorer page.**
    """
    handler = _app().find_handler(path="/api/docs", method="GET")
    response = handler(_FakeRequest(path="/api/docs", auth_principal=None))

    testbase.assert_equal(
        (response.status_code in (301, 302, 307, 308), response.headers.get("Location", "")),
        (True, PAGE_PATH),
    )
    return


def test_the_page_runs_scripts_from_this_origin_only_and_may_call_only_this_service():
    """
    **Feature: REST API explorer (DOC-06)**
    **Property: the page sets a policy whose ``script-src`` is this origin alone (no inline, no eval), whose ``connect-src`` is this origin (so Try it out can only call this
    service), which allows no ``blob:`` worker (that was ReDoc's search) and which names no third-party host.**
    """
    policy = _page(principal=_principal()).headers.get("Content-Security-Policy", "")
    parts = policy.split("; ")

    testbase.assert_equal(
        ("script-src 'self'" in parts, "connect-src 'self'" in parts, "blob:" in policy, "http" in policy),
        (True, True, False, False),
    )
    return


def _starter(*, setting: Optional[str]) -> str:
    previous = os.environ.get(openapi_document.TRY_IT_OUT_ENV_VAR, None)
    try:
        if setting is None:
            os.environ.pop(openapi_document.TRY_IT_OUT_ENV_VAR, None)
        else:
            os.environ[openapi_document.TRY_IT_OUT_ENV_VAR] = setting
        rtnval = _asset(filename="swagger-initializer.js", principal=_principal()).body.decode("utf-8")
    finally:
        if previous is None:
            os.environ.pop(openapi_document.TRY_IT_OUT_ENV_VAR, None)
        else:
            os.environ[openapi_document.TRY_IT_OUT_ENV_VAR] = previous
    return rtnval


def test_the_starter_opens_folded_on_the_path_grouped_document_and_leaves_try_it_out_to_a_click():
    """
    **Feature: REST API explorer (DOC-06)**
    **Property: the starter script starts Swagger UI on ``/api/v1/_meta/openapi.json?group_by=path`` with everything folded, deep links on, the Schemas block hidden and
    Try it out switched on by a person (not on by default); with no setting, every method may be sent.**
    """
    script = _starter(setting=None)

    testbase.assert_equal(
        (
            '"url": "/api/v1/_meta/openapi.json?group_by=path"' in script, '"docExpansion": "none"' in script, '"deepLinking": true' in script,
            '"defaultModelsExpandDepth": -1' in script, '"tryItOutEnabled": false' in script, "supportedSubmitMethods" in script,
        ),
        (True, True, True, True, True, False),
    )
    return


def test_the_operator_setting_limits_what_try_it_out_may_send():
    """
    **Feature: REST API explorer (DOC-06)**
    **Property: ``PYCHESTRATE_API_DOCS_TRY_IT_OUT`` of ``get`` limits Try it out to GET, ``off`` removes it, ``all`` and an empty value allow every method, and an unrecognised
    value (a typo in a setting meant to make the page safer) is read as ``get`` rather than leaving every method on.**
    """
    answers = {}
    for setting in ("get", "GET", "off", "all", "", "get-only"):
        previous = os.environ.get(openapi_document.TRY_IT_OUT_ENV_VAR, None)
        os.environ[openapi_document.TRY_IT_OUT_ENV_VAR] = setting
        try:
            answers[setting] = openapi_document.try_it_out_methods()
        finally:
            if previous is None:
                os.environ.pop(openapi_document.TRY_IT_OUT_ENV_VAR, None)
            else:
                os.environ[openapi_document.TRY_IT_OUT_ENV_VAR] = previous
    testbase.assert_equal(
        answers,
        {"get": ("GET",), "GET": ("GET",), "off": (), "all": None, "": None, "get-only": ("GET",)},
    )
    return


def test_the_starter_carries_the_operator_setting_into_the_page():
    """
    **Feature: REST API explorer (DOC-06)**
    **Property: with the setting at ``get`` the starter script lists only ``get`` as a method Try it out may send; at ``off`` it lists none.**
    """
    get_only = _starter(setting="get")
    off = _starter(setting="off")

    testbase.assert_equal(
        (re.search(r'"supportedSubmitMethods": \[\s*"get"\s*\]', get_only) is not None, re.search(r'"supportedSubmitMethods": \[\s*\]', off) is not None),
        (True, True),
    )
    return


def _document(query: Dict[str, str]) -> Any:
    openapi_document.reset_cache_for_testing()
    request = _FakeRequest(path="/api/v1/_meta/openapi.json", auth_principal=_principal())
    request.query_params = query
    return openapi_document.handle_get_openapi_document(request)


def test_the_document_grouped_by_path_tags_each_operation_by_where_its_path_puts_it():
    """
    **Feature: REST API explorer (DOC-06)**
    **Property: ``?group_by=path`` returns the document with every operation carrying exactly one tag, its path's group (``projects / rpa``), the tag list rebuilt with counts, and
    the feature tags kept on each operation under ``x-original-tags``.**
    """
    response = _document({"group_by": "path"})
    document = json.loads(response.body.decode("utf-8"))
    trigger = document["paths"]["/projects/{project_id}/rpa/specs/{spec_id}/trigger"]["post"]

    testbase.assert_equal(
        (response.status_code, trigger["tags"], trigger["x-original-tags"], "projects / rpa" in [tag["name"] for tag in document["tags"]], len(document["tags"]) > 60),
        (200, ["projects / rpa"], ["rpa"], True, True),
    )
    return


def test_the_plain_document_keeps_its_feature_tags_for_the_pyc_cli():
    """
    **Feature: REST API explorer (DOC-06)**
    **Property: without ``group_by`` the document is unchanged: the trigger operation is tagged ``rpa`` and carries no ``x-original-tags``, so the command list ``pyc`` builds is not
    disturbed by the explorer.**
    """
    document = json.loads(_document({}).body.decode("utf-8"))
    trigger = document["paths"]["/projects/{project_id}/rpa/specs/{spec_id}/trigger"]["post"]

    testbase.assert_equal((trigger["tags"], "x-original-tags" in trigger), (["rpa"], False))
    return


def test_an_unknown_group_by_is_a_400_that_names_the_choice():
    """
    **Feature: REST API explorer (DOC-06)**
    **Property: ``?group_by=tag`` answers 400 saying ``group_by`` must be ``path``, rather than silently returning the plain document.**
    """
    response = _document({"group_by": "tag"})

    testbase.assert_equal((response.status_code, "'path'" in json.loads(response.body.decode("utf-8"))["detail"]), (400, True))
    return


def test_the_served_document_names_the_right_licence():
    """
    **Feature: REST reference page (DOC-06)**
    **Property: the OpenAPI document declares the Code Craft AI Source
    Available License, not Apache-2.0.**
    """
    openapi_document.reset_cache_for_testing()
    document = openapi_document.load_served_document()

    testbase.assert_equal(
        (document["info"]["license"]["name"], "apache" in str(document["info"]["license"]).lower()),
        ("Code Craft AI Source Available License", False),
    )
    return
