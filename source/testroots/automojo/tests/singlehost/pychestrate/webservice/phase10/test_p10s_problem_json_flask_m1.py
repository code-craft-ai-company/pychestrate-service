"""
.. module:: test_p10s_problem_json_flask_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the flask glue around the problem_json builder.

.. moduleauthor:: Automation Mojo LLC

The helper imports flask lazily so this module is importable without
flask installed. Tests inject a stub ``flask_module`` carrying just
the three callables the helper needs (``jsonify`` / ``make_response``
/ ``abort``) and assert on the captured response objects.

The end-to-end behavior — ``flask.abort`` raising an HTTPException
that flask-restx returns verbatim — is exercised by the controller
refits (flags / users / audit) when run inside a real flask app;
these tests cover the wiring and the response shape.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Dict, List

from automojo import testbase

from automojo.pychestrate.webservice.api.problem_json import (
    PROBLEM_JSON_MEDIA_TYPE,
    PROBLEM_TYPE_BAD_REQUEST,
    PROBLEM_TYPE_CONFLICT,
    PROBLEM_TYPE_NOT_FOUND,
    PROBLEM_TYPE_SERVICE_UNAVAILABLE,
)
from automojo.pychestrate.webservice.api.problem_json_flask import (
    abort_with_problem,
    build_flask_problem_response,
)


class _FakeFlaskResponse:
    """
        Minimal Flask-response shim. Records header writes so tests
        can assert on the Content-Type the helper attaches.
    """

    def __init__(self, *, body: Any, status_code: int) -> None:
        self.body: Any = body
        self.status_code: int = int(status_code)
        self.headers: Dict[str, str] = {}


class _AbortException(Exception):
    """
        Stand-in for the HTTPException flask.abort raises. Carries the
        Flask response object the helper handed in so tests can
        inspect it.
    """

    def __init__(self, response: _FakeFlaskResponse) -> None:
        super().__init__("aborted")
        self.response: _FakeFlaskResponse = response


class _FakeFlaskModule:
    """
        Stub passed in via the ``flask_module`` keyword arg. Records
        every ``jsonify`` / ``make_response`` / ``abort`` call.
    """

    def __init__(self) -> None:
        self.jsonify_calls: List[Any] = []
        self.make_response_calls: List = []
        self.aborts: List[_FakeFlaskResponse] = []

    def jsonify(self, body: Any) -> Any:
        self.jsonify_calls.append(body)
        rtnval = body
        return rtnval

    def make_response(self, body: Any, status_code: int) -> _FakeFlaskResponse:
        response = _FakeFlaskResponse(body=body, status_code=status_code)
        self.make_response_calls.append((body, status_code))
        rtnval = response
        return rtnval

    def abort(self, response: _FakeFlaskResponse) -> None:
        self.aborts.append(response)
        raise _AbortException(response=response)


# ---------------------------------------------------------------------------
# abort_with_problem — happy paths
# ---------------------------------------------------------------------------

def test_abort_with_problem_routes_404_through_documented_type():
    """
    **Feature: 8-rest-api-v1 T1.4 (flask glue)**
    **Property: A 404 abort produces a body whose 'type' resolves to
    the documented ``not-found`` URI under
    https://docs.pychestrate.io/errors/.**
    """
    fake = _FakeFlaskModule()
    raised = False
    try:
        abort_with_problem(
            status=404, detail="missing", flask_module=fake
        )
    except _AbortException as xcpt:
        raised = True
        body = xcpt.response.body
        testbase.assert_equal(body["type"], PROBLEM_TYPE_NOT_FOUND)
        testbase.assert_equal(body["status"], 404)
        testbase.assert_equal(body["detail"], "missing")
    testbase.assert_equal(raised, True)
    return


def test_abort_with_problem_attaches_problem_json_content_type():
    """
    **Feature: 8-rest-api-v1 T1.4 (flask glue)**
    **Property: The Flask response is set to the documented
    ``application/problem+json`` content type per RFC 7807 §6.1.**
    """
    fake = _FakeFlaskModule()
    raised = False
    try:
        abort_with_problem(status=409, detail="dupe", flask_module=fake)
    except _AbortException as xcpt:
        raised = True
        testbase.assert_equal(
            xcpt.response.headers["Content-Type"], PROBLEM_JSON_MEDIA_TYPE
        )
    testbase.assert_equal(raised, True)
    return


def test_abort_with_problem_passes_status_code_to_make_response():
    """
    **Feature: 8-rest-api-v1 T1.4 (flask glue)**
    **Property: The status_code arg propagates to flask's
    make_response so the wire response carries the documented HTTP
    status.**
    """
    fake = _FakeFlaskModule()
    try:
        abort_with_problem(status=503, detail="db down", flask_module=fake)
    except _AbortException:
        pass
    testbase.assert_equal(len(fake.make_response_calls), 1)
    body, status_code = fake.make_response_calls[0]
    testbase.assert_equal(status_code, 503)
    return


def test_abort_with_problem_includes_instance_when_supplied():
    """
    **Feature: 8-rest-api-v1 T1.4 (flask glue)**
    **Property: An ``instance`` URI appears in the rendered body.**
    """
    fake = _FakeFlaskModule()
    raised = False
    try:
        abort_with_problem(
            status=400,
            detail="bad input",
            instance="/api/v1/flags/some-key",
            flask_module=fake,
        )
    except _AbortException as xcpt:
        raised = True
        testbase.assert_equal(
            xcpt.response.body["instance"], "/api/v1/flags/some-key"
        )
    testbase.assert_equal(raised, True)
    return


def test_abort_with_problem_omits_instance_when_not_supplied():
    """
    **Feature: 8-rest-api-v1 T1.4 (flask glue)**
    **Property: Body omits the 'instance' key when the helper
    receives no instance argument.**
    """
    fake = _FakeFlaskModule()
    try:
        abort_with_problem(status=400, detail="bad", flask_module=fake)
    except _AbortException as xcpt:
        testbase.assert_equal("instance" in xcpt.response.body, False)
    return


def test_abort_with_problem_merges_extension_members():
    """
    **Feature: 8-rest-api-v1 T1.4 (flask glue)**
    **Property: Extension members appear in the rendered body
    alongside the reserved RFC 7807 fields.**
    """
    fake = _FakeFlaskModule()
    raised = False
    try:
        abort_with_problem(
            status=409,
            detail="duplicate",
            extensions={"flag_key": "auth.local"},
            flask_module=fake,
        )
    except _AbortException as xcpt:
        raised = True
        body = xcpt.response.body
        testbase.assert_equal(body["flag_key"], "auth.local")
        testbase.assert_equal(body["type"], PROBLEM_TYPE_CONFLICT)
    testbase.assert_equal(raised, True)
    return


def test_abort_with_problem_invokes_flask_abort_exactly_once():
    """
    **Feature: 8-rest-api-v1 T1.4 (flask glue)**
    **Property: Exactly one flask.abort call is made (no double
    abort, no leak past the abort).**
    """
    fake = _FakeFlaskModule()
    try:
        abort_with_problem(status=400, detail="x", flask_module=fake)
    except _AbortException:
        pass
    testbase.assert_equal(len(fake.aborts), 1)
    return


def test_abort_with_problem_falls_through_to_unknown_error_for_unrecognized_status():
    """
    **Feature: 8-rest-api-v1 T1.4 (flask glue)**
    **Property: An unrecognized status (e.g., 418) falls back to
    'unknown-error' rather than producing a malformed document.**
    """
    fake = _FakeFlaskModule()
    raised = False
    try:
        abort_with_problem(status=418, detail="teapot", flask_module=fake)
    except _AbortException as xcpt:
        raised = True
        testbase.assert_equal(
            xcpt.response.body["type"].endswith("/unknown-error"), True
        )
        testbase.assert_equal(xcpt.response.body["status"], 418)
    testbase.assert_equal(raised, True)
    return


# ---------------------------------------------------------------------------
# build_flask_problem_response — non-aborting wrapper
# ---------------------------------------------------------------------------

def test_build_flask_problem_response_returns_response_without_aborting():
    """
    **Feature: 8-rest-api-v1 T1.4 (flask glue)**
    **Property: build_flask_problem_response returns a Flask response
    object directly (no abort) so middleware / non-abort code paths
    can reuse the wire shape.**
    """
    fake = _FakeFlaskModule()
    response = build_flask_problem_response(
        problem_type="https://example.com/errors/x",
        title="X",
        status=422,
        detail="bad input",
        flask_module=fake,
    )
    testbase.assert_equal(len(fake.aborts), 0)
    testbase.assert_equal(response.status_code, 422)
    testbase.assert_equal(
        response.headers["Content-Type"], PROBLEM_JSON_MEDIA_TYPE
    )
    return


def test_build_flask_problem_response_emits_custom_problem_type():
    """
    **Feature: 8-rest-api-v1 T1.4 (flask glue)**
    **Property: An extension-defined problem_type passes through to
    the body verbatim — bridges the framework helpers to caller-
    specific error classes.**
    """
    fake = _FakeFlaskModule()
    response = build_flask_problem_response(
        problem_type="https://docs.pychestrate.io/errors/quota-exhausted",
        title="Quota Exhausted",
        status=429,
        detail="daily quota",
        flask_module=fake,
    )
    testbase.assert_equal(
        response.body["type"],
        "https://docs.pychestrate.io/errors/quota-exhausted",
    )
    return


# ---------------------------------------------------------------------------
# Stock 4xx / 5xx coverage
# ---------------------------------------------------------------------------

def test_abort_with_problem_covers_documented_stock_codes():
    """
    **Feature: 8-rest-api-v1 T1.4 (flask glue)**
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
        fake = _FakeFlaskModule()
        try:
            abort_with_problem(status=status, detail="x", flask_module=fake)
        except _AbortException as xcpt:
            testbase.assert_equal(xcpt.response.body["type"], expected_type)
            testbase.assert_equal(xcpt.response.body["status"], status)
    return


# ---------------------------------------------------------------------------
# Refit smoke — controllers import cleanly with the new helper.
#
# Flask is not installed in the test venv, so we cannot import the
# controller modules end-to-end. We can, however, assert the refit
# replaced every `_ns.abort(` call site with `abort_with_problem(`
# by reading the source — a low-cost regression guard.
# ---------------------------------------------------------------------------

def _read_source(*, controller_relative_path: str) -> str:
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    repo_source_root = os.path.normpath(
        os.path.join(here, "..", "..", "..", "..", "..", "..", "..", "..", "source", "site")
    )
    full = os.path.join(repo_source_root, controller_relative_path)
    with open(full, "r", encoding="utf-8") as fh:
        rtnval = fh.read()
    return rtnval


def test_flags_controller_has_zero_legacy_abort_sites():
    text = _read_source(
        controller_relative_path=os.path.join(
            "automojo", "pychestrate", "webservice", "identity", "flags",
            "restapi", "v1", "flags_controller.py",
        )
    )
    testbase.assert_equal("flags_ns.abort(" in text, False)
    testbase.assert_equal("abort_with_problem" in text, True)
    return


def test_users_controller_has_zero_legacy_abort_sites():
    text = _read_source(
        controller_relative_path=os.path.join(
            "automojo", "pychestrate", "webservice", "identity", "users",
            "restapi", "v1", "users_controller.py",
        )
    )
    testbase.assert_equal("users_ns.abort(" in text, False)
    testbase.assert_equal("abort_with_problem" in text, True)
    return


def test_audit_controller_has_zero_legacy_abort_sites():
    text = _read_source(
        controller_relative_path=os.path.join(
            "automojo", "pychestrate", "webservice", "audit",
            "restapi", "v1", "audit_controller.py",
        )
    )
    testbase.assert_equal("audit_ns.abort(" in text, False)
    testbase.assert_equal("abort_with_problem" in text, True)
    return


# Provide ``os`` at module scope for the helper above (kept inline so the
# test reader sees the import close to use).
import os  # noqa: E402  — late import keeps the module narrow during read.
