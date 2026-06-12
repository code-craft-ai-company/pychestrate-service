"""
.. module:: test_p10v_problem_json_webworks_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the webworks glue around the problem_json builder.

.. moduleauthor:: Code Craft AI LLC

The webworks glue parallels the flask glue's two-function shape but
adapts to the webworks ``return-a-response`` idiom — handlers return
responses, including error responses, because the dispatcher does
not carry custom bodies through :class:`HTTPException`.

Most tests inject a stub ``response_cls`` so the helpers' behavior
is exercisable in isolation. One round-trip test uses the real
:class:`JSONResponse` to verify wire-shape compatibility — webworks
is installed in the runtime venv so the import works.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Dict, Optional

from ccai import testbase

from ccai.pychestrate.webservice.api.problem_json import (
    PROBLEM_JSON_MEDIA_TYPE,
    PROBLEM_TYPE_BAD_REQUEST,
    PROBLEM_TYPE_CONFLICT,
    PROBLEM_TYPE_NOT_FOUND,
    PROBLEM_TYPE_SERVICE_UNAVAILABLE,
)
from ccai.pychestrate.webservice.api.problem_json_webworks import (
    build_webworks_problem_response,
    problem_response_for_http_status,
)


class _FakeJSONResponse:
    """
        Stand-in for :class:`ccai.webworks.routing.response.JSONResponse`.

        Captures the constructor arguments and any ``set_header`` calls
        the helper makes so tests can assert on the resulting response
        without coupling to webworks internals.
    """

    def __init__(
        self,
        content: Any,
        status_code: int = 200,
        headers: Optional[Dict[str, str]] = None
    ) -> None:
        self.content: Any = content
        self.status_code: int = int(status_code)
        self.headers: Dict[str, str] = {}
        if headers is not None:
            for name, value in headers.items():
                self.headers[name] = value
        return

    def set_header(self, name: str, value: str) -> None:
        self.headers[name] = value
        return


# ---------------------------------------------------------------------------
# problem_response_for_http_status — happy paths
# ---------------------------------------------------------------------------


def test_problem_response_for_http_status_routes_404_through_documented_type():
    """
    **Feature: 8-rest-api-v1 T1.4 (webworks glue)**
    **Property: A 404 response carries a body whose 'type' resolves to
    the documented ``not-found`` URI under
    https://docs.pychestrate.io/errors/.**
    """
    response = problem_response_for_http_status(
        status=404, detail="missing", response_cls=_FakeJSONResponse
    )
    body = response.content
    testbase.assert_equal(body["type"], PROBLEM_TYPE_NOT_FOUND)
    testbase.assert_equal(body["status"], 404)
    testbase.assert_equal(body["detail"], "missing")
    return


def test_problem_response_for_http_status_attaches_problem_json_content_type():
    """
    **Feature: 8-rest-api-v1 T1.4 (webworks glue)**
    **Property: The response is set to the documented
    ``application/problem+json`` content type per RFC 7807 §6.1.**
    """
    response = problem_response_for_http_status(
        status=409, detail="dupe", response_cls=_FakeJSONResponse
    )
    testbase.assert_equal(
        response.headers["Content-Type"], PROBLEM_JSON_MEDIA_TYPE
    )
    return


def test_problem_response_for_http_status_passes_status_code_to_response():
    """
    **Feature: 8-rest-api-v1 T1.4 (webworks glue)**
    **Property: The status_code arg propagates to the JSONResponse
    constructor so the wire response carries the documented HTTP
    status.**
    """
    response = problem_response_for_http_status(
        status=503, detail="db down", response_cls=_FakeJSONResponse
    )
    testbase.assert_equal(response.status_code, 503)
    return


def test_problem_response_for_http_status_includes_instance_when_supplied():
    """
    **Feature: 8-rest-api-v1 T1.4 (webworks glue)**
    **Property: An ``instance`` URI appears in the rendered body.**
    """
    response = problem_response_for_http_status(
        status=400,
        detail="bad input",
        instance="/api/v1/flags/some-key",
        response_cls=_FakeJSONResponse,
    )
    testbase.assert_equal(
        response.content["instance"], "/api/v1/flags/some-key"
    )
    return


def test_problem_response_for_http_status_omits_instance_when_not_supplied():
    """
    **Feature: 8-rest-api-v1 T1.4 (webworks glue)**
    **Property: Body omits the 'instance' key when the helper
    receives no instance argument.**
    """
    response = problem_response_for_http_status(
        status=400, detail="bad", response_cls=_FakeJSONResponse
    )
    has_instance = "instance" in response.content
    testbase.assert_equal(has_instance, False)
    return


def test_problem_response_for_http_status_merges_extension_members():
    """
    **Feature: 8-rest-api-v1 T1.4 (webworks glue)**
    **Property: Extension members appear in the rendered body
    alongside the reserved RFC 7807 fields.**
    """
    response = problem_response_for_http_status(
        status=409,
        detail="duplicate",
        extensions={"flag_key": "auth.local"},
        response_cls=_FakeJSONResponse,
    )
    body = response.content
    testbase.assert_equal(body["flag_key"], "auth.local")
    testbase.assert_equal(body["type"], PROBLEM_TYPE_CONFLICT)
    return


def test_problem_response_for_http_status_falls_through_to_unknown_error_for_unrecognized_status():
    """
    **Feature: 8-rest-api-v1 T1.4 (webworks glue)**
    **Property: An unrecognized status (e.g., 418) falls back to
    'unknown-error' rather than producing a malformed document.**
    """
    response = problem_response_for_http_status(
        status=418, detail="teapot", response_cls=_FakeJSONResponse
    )
    type_url = response.content["type"]
    ends_with_unknown = type_url.endswith("/unknown-error")
    testbase.assert_equal(ends_with_unknown, True)
    testbase.assert_equal(response.content["status"], 418)
    return


# ---------------------------------------------------------------------------
# build_webworks_problem_response — custom problem type
# ---------------------------------------------------------------------------


def test_build_webworks_problem_response_returns_response_with_documented_content_type():
    """
    **Feature: 8-rest-api-v1 T1.4 (webworks glue)**
    **Property: build_webworks_problem_response returns a webworks
    response object with the documented ``application/problem+json``
    content type so middleware and non-stock-status code paths can
    reuse the wire shape.**
    """
    response = build_webworks_problem_response(
        problem_type="https://example.com/errors/x",
        title="X",
        status=422,
        detail="bad input",
        response_cls=_FakeJSONResponse,
    )
    testbase.assert_equal(response.status_code, 422)
    testbase.assert_equal(
        response.headers["Content-Type"], PROBLEM_JSON_MEDIA_TYPE
    )
    return


def test_build_webworks_problem_response_emits_custom_problem_type():
    """
    **Feature: 8-rest-api-v1 T1.4 (webworks glue)**
    **Property: An extension-defined problem_type passes through to
    the body verbatim — bridges the framework helpers to caller-
    specific error classes.**
    """
    response = build_webworks_problem_response(
        problem_type="https://docs.pychestrate.io/errors/quota-exhausted",
        title="Quota Exhausted",
        status=429,
        detail="daily quota",
        response_cls=_FakeJSONResponse,
    )
    testbase.assert_equal(
        response.content["type"],
        "https://docs.pychestrate.io/errors/quota-exhausted",
    )
    return


# ---------------------------------------------------------------------------
# Stock 4xx / 5xx coverage
# ---------------------------------------------------------------------------


def test_problem_response_for_http_status_covers_documented_stock_codes():
    """
    **Feature: 8-rest-api-v1 T1.4 (webworks glue)**
    **Property: Every documented stock status (400, 404, 409, 503)
    routes through to the matching PROBLEM_TYPE_* URL.**
    """
    expected_pairs = (
        (400, PROBLEM_TYPE_BAD_REQUEST),
        (404, PROBLEM_TYPE_NOT_FOUND),
        (409, PROBLEM_TYPE_CONFLICT),
        (503, PROBLEM_TYPE_SERVICE_UNAVAILABLE),
    )
    for status, expected_type in expected_pairs:
        response = problem_response_for_http_status(
            status=status, detail="x", response_cls=_FakeJSONResponse
        )
        testbase.assert_equal(response.content["type"], expected_type)
        testbase.assert_equal(response.content["status"], status)
    return


# ---------------------------------------------------------------------------
# Real-JSONResponse round-trip — verifies wire compatibility
#
# webworks is installed in the test venv (unlike flask) so this
# integration check runs as part of the singlehost suite. It catches
# any drift between the helper's contract and JSONResponse's actual
# constructor / set_header surface.
# ---------------------------------------------------------------------------


def test_problem_response_for_http_status_roundtrips_through_real_json_response():
    """
    **Feature: 8-rest-api-v1 T1.4 (webworks glue)**
    **Property: When given the real ``JSONResponse`` class, the
    helper produces a response whose serialized body decodes back to
    the documented RFC 7807 dict and whose Content-Type header is
    ``application/problem+json``.**
    """
    import json

    from ccai.webworks.routing.response import JSONResponse

    response = problem_response_for_http_status(
        status=404, detail="missing", instance="/api/v1/flags/x"
    )

    is_json_response = isinstance(response, JSONResponse)
    testbase.assert_equal(is_json_response, True)
    testbase.assert_equal(response.status_code, 404)
    testbase.assert_equal(
        response.headers["Content-Type"], PROBLEM_JSON_MEDIA_TYPE
    )

    body_text = response.body.decode("utf-8")
    body_dict = json.loads(body_text)
    testbase.assert_equal(body_dict["type"], PROBLEM_TYPE_NOT_FOUND)
    testbase.assert_equal(body_dict["status"], 404)
    testbase.assert_equal(body_dict["detail"], "missing")
    testbase.assert_equal(body_dict["instance"], "/api/v1/flags/x")
    return
