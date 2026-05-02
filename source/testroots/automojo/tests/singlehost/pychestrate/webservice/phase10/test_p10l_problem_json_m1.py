"""
.. module:: test_p10l_problem_json_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the framework-agnostic RFC 7807 builder.

.. moduleauthor:: Automation Mojo LLC

The builder is the foundation for ``8-rest-api-v1`` T1.4. Tests cover
the ProblemDocument dataclass invariants, every documented stock
status mapping, the extension-member merge, the reserved-key collision
guard, and the JSON-friendly body ordering.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import json

from automojo import testbase

from automojo.pychestrate.webservice.api.problem_json import (
    PROBLEM_JSON_MEDIA_TYPE,
    PROBLEM_TYPE_BASE_URL,
    PROBLEM_TYPE_BAD_REQUEST,
    PROBLEM_TYPE_CONFLICT,
    PROBLEM_TYPE_FORBIDDEN,
    PROBLEM_TYPE_INTERNAL_SERVER_ERROR,
    PROBLEM_TYPE_METHOD_NOT_ALLOWED,
    PROBLEM_TYPE_NOT_FOUND,
    PROBLEM_TYPE_RATE_LIMITED,
    PROBLEM_TYPE_SERVICE_UNAVAILABLE,
    PROBLEM_TYPE_UNAUTHENTICATED,
    PROBLEM_TYPE_VALIDATION_FAILED,
    ProblemDocument,
    ProblemResponse,
    build_problem_document,
    build_problem_response,
    problem_for_http_status,
)


# ---------------------------------------------------------------------------
# ProblemDocument dataclass
# ---------------------------------------------------------------------------

def test_problem_document_is_frozen_and_carries_documented_fields():
    """
    **Feature: 8-rest-api-v1 T1.4 (RFC 7807)**
    **Property: ProblemDocument is frozen with the five RFC 7807
    members plus the optional extensions mapping.**
    """
    document = ProblemDocument(
        type="https://example.com/errors/x",
        title="X",
        status=400,
        detail="bad",
        instance="/api/v1/x",
        extensions={"trace_id": "abc"},
    )
    testbase.assert_equal(document.type, "https://example.com/errors/x")
    testbase.assert_equal(document.title, "X")
    testbase.assert_equal(document.status, 400)
    testbase.assert_equal(document.detail, "bad")
    testbase.assert_equal(document.instance, "/api/v1/x")
    testbase.assert_equal(document.extensions["trace_id"], "abc")

    raised = False
    try:
        document.title = "different"
    except Exception:
        raised = True
    testbase.assert_equal(raised, True)
    return


# ---------------------------------------------------------------------------
# build_problem_document validation
# ---------------------------------------------------------------------------

def test_build_problem_document_rejects_status_below_100():
    """
    **Feature: 8-rest-api-v1 T1.4 (RFC 7807)**
    **Property: status < 100 raises ValueError.**
    """
    raised = False
    try:
        build_problem_document(
            problem_type="t", title="T", status=99, detail="d",
            instance=None, extensions=None,
        )
    except ValueError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_build_problem_document_rejects_status_above_599():
    """
    **Feature: 8-rest-api-v1 T1.4 (RFC 7807)**
    **Property: status > 599 raises ValueError.**
    """
    raised = False
    try:
        build_problem_document(
            problem_type="t", title="T", status=600, detail="d",
            instance=None, extensions=None,
        )
    except ValueError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_build_problem_document_rejects_extension_collision_with_reserved_key():
    """
    **Feature: 8-rest-api-v1 T1.4 (RFC 7807)**
    **Property: Reserved RFC 7807 names refused as extension keys
    so the wire body never contradicts the spec.**
    """
    for reserved in ("type", "title", "status", "detail", "instance"):
        raised = False
        try:
            build_problem_document(
                problem_type="t", title="T", status=400, detail="d",
                instance=None,
                extensions={reserved: "x"},
            )
        except ValueError:
            raised = True
        testbase.assert_equal(raised, True)
    return


def test_build_problem_document_default_extensions_is_empty_mapping():
    """
    **Feature: 8-rest-api-v1 T1.4 (RFC 7807)**
    **Property: Passing extensions=None yields an empty mapping on
    the document.**
    """
    document = build_problem_document(
        problem_type="t", title="T", status=400, detail="d",
        instance=None, extensions=None,
    )
    testbase.assert_equal(len(document.extensions), 0)
    return


# ---------------------------------------------------------------------------
# build_problem_response shape
# ---------------------------------------------------------------------------

def test_build_problem_response_uses_problem_json_content_type():
    """
    **Feature: 8-rest-api-v1 T1.4 (RFC 7807)**
    **Property: ProblemResponse content_type is always
    application/problem+json.**
    """
    response = build_problem_response(
        problem_type=PROBLEM_TYPE_BAD_REQUEST,
        title="Bad Request",
        status=400,
        detail="bad",
    )
    testbase.assert_equal(response.content_type, PROBLEM_JSON_MEDIA_TYPE)
    testbase.assert_equal(response.status_code, 400)
    return


def test_build_problem_response_body_carries_required_members():
    """
    **Feature: 8-rest-api-v1 T1.4 (RFC 7807)**
    **Property: body contains the four required members.**
    """
    response = build_problem_response(
        problem_type="https://example.com/errors/x",
        title="X",
        status=400,
        detail="bad",
    )
    for required_key in ("type", "title", "status", "detail"):
        testbase.assert_equal(required_key in response.body, True)
    return


def test_build_problem_response_omits_instance_when_not_supplied():
    """
    **Feature: 8-rest-api-v1 T1.4 (RFC 7807)**
    **Property: instance is optional — body omits the key when
    instance=None.**
    """
    response = build_problem_response(
        problem_type="t", title="T", status=400, detail="d",
    )
    testbase.assert_equal("instance" in response.body, False)
    return


def test_build_problem_response_includes_instance_when_supplied():
    """
    **Feature: 8-rest-api-v1 T1.4 (RFC 7807)**
    **Property: instance lands in the body when supplied.**
    """
    response = build_problem_response(
        problem_type="t", title="T", status=400, detail="d",
        instance="/api/v1/x",
    )
    testbase.assert_equal(response.body["instance"], "/api/v1/x")
    return


def test_build_problem_response_merges_extension_members():
    """
    **Feature: 8-rest-api-v1 T1.4 (RFC 7807)**
    **Property: Extension members appear alongside the reserved
    fields in the wire body.**
    """
    response = build_problem_response(
        problem_type="t", title="T", status=429, detail="d",
        extensions={"limit": 100, "remaining": 0},
    )
    testbase.assert_equal(response.body["limit"], 100)
    testbase.assert_equal(response.body["remaining"], 0)
    return


def test_build_problem_response_json_round_trips():
    """
    **Feature: 8-rest-api-v1 T1.4 (RFC 7807)**
    **Property: The body round-trips through json.dumps / json.loads
    without loss.**
    """
    response = build_problem_response(
        problem_type=PROBLEM_TYPE_NOT_FOUND,
        title="Not Found",
        status=404,
        detail="missing",
        instance="/x",
        extensions={"k": 1},
    )
    serialized = json.dumps(response.body)
    parsed = json.loads(serialized)
    testbase.assert_equal(parsed["type"], PROBLEM_TYPE_NOT_FOUND)
    testbase.assert_equal(parsed["status"], 404)
    testbase.assert_equal(parsed["k"], 1)
    return


# ---------------------------------------------------------------------------
# problem_for_http_status registry coverage
# ---------------------------------------------------------------------------

def test_problem_for_http_status_400_maps_to_bad_request():
    response = problem_for_http_status(status=400, detail="bad")
    testbase.assert_equal(response.body["type"], PROBLEM_TYPE_BAD_REQUEST)
    testbase.assert_equal(response.body["title"], "Bad Request")
    return


def test_problem_for_http_status_401_maps_to_unauthenticated():
    response = problem_for_http_status(status=401, detail="x")
    testbase.assert_equal(response.body["type"], PROBLEM_TYPE_UNAUTHENTICATED)
    return


def test_problem_for_http_status_403_maps_to_forbidden():
    response = problem_for_http_status(status=403, detail="x")
    testbase.assert_equal(response.body["type"], PROBLEM_TYPE_FORBIDDEN)
    return


def test_problem_for_http_status_404_maps_to_not_found():
    response = problem_for_http_status(status=404, detail="x")
    testbase.assert_equal(response.body["type"], PROBLEM_TYPE_NOT_FOUND)
    return


def test_problem_for_http_status_405_maps_to_method_not_allowed():
    response = problem_for_http_status(status=405, detail="x")
    testbase.assert_equal(response.body["type"], PROBLEM_TYPE_METHOD_NOT_ALLOWED)
    return


def test_problem_for_http_status_409_maps_to_conflict():
    response = problem_for_http_status(status=409, detail="x")
    testbase.assert_equal(response.body["type"], PROBLEM_TYPE_CONFLICT)
    return


def test_problem_for_http_status_422_maps_to_validation_failed():
    response = problem_for_http_status(status=422, detail="x")
    testbase.assert_equal(response.body["type"], PROBLEM_TYPE_VALIDATION_FAILED)
    return


def test_problem_for_http_status_429_maps_to_rate_limited():
    response = problem_for_http_status(status=429, detail="x")
    testbase.assert_equal(response.body["type"], PROBLEM_TYPE_RATE_LIMITED)
    return


def test_problem_for_http_status_500_maps_to_internal_server_error():
    response = problem_for_http_status(status=500, detail="x")
    testbase.assert_equal(response.body["type"], PROBLEM_TYPE_INTERNAL_SERVER_ERROR)
    return


def test_problem_for_http_status_503_maps_to_service_unavailable():
    response = problem_for_http_status(status=503, detail="x")
    testbase.assert_equal(response.body["type"], PROBLEM_TYPE_SERVICE_UNAVAILABLE)
    return


def test_problem_for_http_status_unknown_status_falls_back_to_unknown_error():
    """
    **Feature: 8-rest-api-v1 T1.4 (RFC 7807)**
    **Property: An unrecognized status (e.g., 418) falls back to
    a generic 'unknown-error' type rather than producing a
    malformed document.**
    """
    response = problem_for_http_status(status=418, detail="teapot")
    testbase.assert_equal(
        response.body["type"], PROBLEM_TYPE_BASE_URL + "unknown-error"
    )
    testbase.assert_equal(response.body["title"], "Error")
    testbase.assert_equal(response.body["status"], 418)
    return


def test_problem_for_http_status_passes_extensions_through():
    """
    **Feature: 8-rest-api-v1 T1.4 (RFC 7807)**
    **Property: extensions= flows through the shortcut.**
    """
    response = problem_for_http_status(
        status=429, detail="too many", extensions={"retry_after_seconds": 60}
    )
    testbase.assert_equal(response.body["retry_after_seconds"], 60)
    return


def test_problem_response_status_code_matches_status_field():
    """
    **Feature: 8-rest-api-v1 T1.4 (RFC 7807)**
    **Property: ProblemResponse.status_code matches the
    body's ``status`` integer.**
    """
    response = problem_for_http_status(status=404, detail="x")
    testbase.assert_equal(response.status_code, response.body["status"])
    return


# ---------------------------------------------------------------------------
# Sanity: media type matches RFC 7807
# ---------------------------------------------------------------------------

def test_problem_json_media_type_is_application_problem_json():
    testbase.assert_equal(PROBLEM_JSON_MEDIA_TYPE, "application/problem+json")
    return
