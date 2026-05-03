"""
.. module:: test_p11b_audit_webworks_routes_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the webworks-native audit REST routes.

.. moduleauthor:: Automation Mojo LLC

The audit port is the second feature ported to webworks (after
flags in #115). It establishes that the per-feature port pattern
generalises beyond the flags-shaped surface — handlers query the
ORM directly here rather than going through a service-layer
module.

Tests cover:

* Route matrix matches the flask_restx ``audit_controller`` (2
  method+path pairs).
* Each handler's success path produces the documented JSON shape.
* Each handler's error paths produce RFC 7807 problem responses.
* Bootstrap source-smoke: register_audit_routes is wired in
  ``register_service_extensions``.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import json

from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from automojo import testbase
from automojo.webworks.routing.response import JSONResponse

from automojo.pychestrate.webservice.api.problem_json import (
    PROBLEM_JSON_MEDIA_TYPE,
    PROBLEM_TYPE_BAD_REQUEST,
    PROBLEM_TYPE_NOT_FOUND,
    PROBLEM_TYPE_SERVICE_UNAVAILABLE,
)
from automojo.pychestrate.webservice.audit.restapi.v1 import audit_routes


# ---------------------------------------------------------------------------
# Test stubs
# ---------------------------------------------------------------------------


class _FakeQueryParams:
    """
        Stand-in for webworks ``QueryParams``. Only ``get`` is used
        by the audit handlers.
    """

    def __init__(self, *, values: Optional[Dict[str, str]] = None) -> None:
        self._values: Dict[str, str] = values if values is not None else {}
        return

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        rtnval = self._values.get(key, default)
        return rtnval


class _FakeRequest:
    """
        Minimal duck-typed Request. The audit handlers touch
        ``path``, ``path_params``, ``query_params``, and read
        ``db_session`` off the Request as an attribute.
    """

    def __init__(
        self,
        *,
        path: str,
        path_params: Optional[Dict[str, Any]] = None,
        query: Optional[Dict[str, str]] = None,
        db_session: Optional[Any] = None,
    ) -> None:
        self.path: str = path
        self.path_params: Dict[str, Any] = path_params if path_params is not None else {}
        self.query_params: _FakeQueryParams = _FakeQueryParams(values=query)
        self.db_session: Optional[Any] = db_session
        return


_UNSET = object()


class _FakeRecord:
    """
        Stand-in for an :class:`AuditRecord` ORM row. Attribute names
        match what ``_record_to_dict`` reads. ``written_at`` uses a
        sentinel default so tests can pass ``None`` explicitly to
        exercise the null-handling branch without falling through to
        the default datetime.
    """

    def __init__(
        self,
        *,
        sequence_number: int,
        record_id: str = "rec-x",
        kind: str = "test.kind",
        source_topic: str = "topic.test",
        actor_user_id: Optional[str] = None,
        target_ref: str = "target.ref",
        payload_json: Optional[Dict[str, Any]] = None,
        record_hash: Optional[bytes] = None,
        written_at: Any = _UNSET,
    ) -> None:
        self.sequence_number: int = sequence_number
        self.record_id: str = record_id
        self.kind: str = kind
        self.source_topic: str = source_topic
        self.actor_user_id: Optional[str] = actor_user_id
        self.target_ref: str = target_ref
        self.payload_json: Optional[Dict[str, Any]] = payload_json
        self.record_hash: Optional[bytes] = record_hash
        if written_at is _UNSET:
            self.written_at: Optional[datetime] = datetime(
                2026, 5, 2, 12, 0, 0, tzinfo=timezone.utc
            )
        else:
            self.written_at = written_at
        return


class _FakeQuery:
    """
        Stand-in for the SQLAlchemy chained
        ``.query().order_by().limit().all()`` and
        ``.query().filter().first()`` flows the audit handlers use.
    """

    def __init__(
        self,
        *,
        rows: List[_FakeRecord],
        first_value: Optional[_FakeRecord] = None
    ) -> None:
        self._rows: List[_FakeRecord] = rows
        self._first_value: Optional[_FakeRecord] = first_value
        self.captured_limit: Optional[int] = None
        return

    def order_by(self, *args: Any, **kwargs: Any) -> "_FakeQuery":
        return self

    def limit(self, value: int) -> "_FakeQuery":
        self.captured_limit = int(value)
        return self

    def all(self) -> List[_FakeRecord]:
        return list(self._rows)

    def filter(self, *args: Any, **kwargs: Any) -> "_FakeQuery":
        return self

    def first(self) -> Optional[_FakeRecord]:
        return self._first_value


class _FakeSession:
    """
        SQLAlchemy session stub returning a configured ``_FakeQuery``
        from ``.query(...)``.
    """

    def __init__(
        self,
        *,
        rows: Optional[List[_FakeRecord]] = None,
        first_value: Optional[_FakeRecord] = None
    ) -> None:
        self._query: _FakeQuery = _FakeQuery(
            rows=rows if rows is not None else [],
            first_value=first_value,
        )
        return

    def query(self, *args: Any, **kwargs: Any) -> _FakeQuery:
        return self._query

    @property
    def captured_limit(self) -> Optional[int]:
        return self._query.captured_limit


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


# ---------------------------------------------------------------------------
# Route registration matrix
# ---------------------------------------------------------------------------


def test_register_audit_routes_attaches_two_routes_under_version_prefix():
    """
    **Feature: 1-audit-log T1.1 (webworks routes)**
    **Property: register_audit_routes attaches the same two
    method+path pairs the flask_restx controller exposed, with the
    documented int converter on the sequence_number path param.**
    """
    app = _FakeApp()
    audit_routes.register_audit_routes(app=app, version_prefix="/api/v1")

    expected_pairs = (
        ("/api/v1/audit", ("GET",)),
        ("/api/v1/audit/{sequence_number:int}", ("GET",)),
    )
    actual_pairs = tuple((path, methods) for path, methods, _ in app.calls)
    testbase.assert_equal(actual_pairs, expected_pairs)
    return


# ---------------------------------------------------------------------------
# 503 misconfig path
# ---------------------------------------------------------------------------


def test_handle_list_returns_503_when_session_missing():
    """
    **Feature: 1-audit-log T1.1 (webworks routes)**
    **Property: A request with no db_session attached produces the
    same 503 problem document the flask controller emitted.**
    """
    request = _FakeRequest(path="/api/v1/audit", db_session=None)
    response = audit_routes.handle_list_audit_records(request)
    testbase.assert_equal(response.status_code, 503)
    testbase.assert_equal(
        response.headers["Content-Type"], PROBLEM_JSON_MEDIA_TYPE
    )
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_SERVICE_UNAVAILABLE)
    testbase.assert_equal(body["instance"], "/api/v1/audit")
    return


def test_handle_read_returns_503_when_session_missing():
    """
    **Feature: 1-audit-log T1.1 (webworks routes)**
    **Property: detail handler also returns 503 when the
    db_session attribute is missing.**
    """
    request = _FakeRequest(
        path="/api/v1/audit/42",
        path_params={"sequence_number": 42},
        db_session=None,
    )
    response = audit_routes.handle_read_audit_record(request)
    testbase.assert_equal(response.status_code, 503)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_SERVICE_UNAVAILABLE)
    return


# ---------------------------------------------------------------------------
# handle_list_audit_records — happy paths and limit clamping
# ---------------------------------------------------------------------------


def test_handle_list_returns_serialized_records_with_default_limit():
    """
    **Feature: 1-audit-log T1.1 (webworks routes)**
    **Property: Returns 200 with a JSON list of record dicts and
    applies the documented default limit of 50 when no ``limit``
    query parameter is supplied.**
    """
    rows = [
        _FakeRecord(sequence_number=2, record_id="rec-2"),
        _FakeRecord(sequence_number=1, record_id="rec-1"),
    ]
    session = _FakeSession(rows=rows)
    request = _FakeRequest(path="/api/v1/audit", db_session=session)

    response = audit_routes.handle_list_audit_records(request)

    testbase.assert_equal(response.status_code, 200)
    testbase.assert_equal(session.captured_limit, audit_routes.DEFAULT_LIMIT)
    body = _decode_body(response)
    testbase.assert_equal(len(body), 2)
    testbase.assert_equal(body[0]["sequence_number"], 2)
    testbase.assert_equal(body[0]["record_id"], "rec-2")
    return


def test_handle_list_caller_limit_propagates_to_query():
    """
    **Feature: 1-audit-log T1.1 (webworks routes)**
    **Property: A ``limit`` query parameter passes through to the
    SQLAlchemy ``.limit()`` call so callers can page within the
    documented bounds.**
    """
    session = _FakeSession(rows=[])
    request = _FakeRequest(
        path="/api/v1/audit", db_session=session, query={"limit": "25"}
    )
    audit_routes.handle_list_audit_records(request)
    testbase.assert_equal(session.captured_limit, 25)
    return


def test_handle_list_clamps_limit_above_max():
    """
    **Feature: 1-audit-log T1.1 (webworks routes)**
    **Property: A limit greater than MAX_LIMIT (500) is clamped to
    MAX_LIMIT — protects the database from unbounded scans.**
    """
    session = _FakeSession(rows=[])
    request = _FakeRequest(
        path="/api/v1/audit", db_session=session, query={"limit": "9999"}
    )
    audit_routes.handle_list_audit_records(request)
    testbase.assert_equal(session.captured_limit, audit_routes.MAX_LIMIT)
    return


def test_handle_list_clamps_limit_below_min():
    """
    **Feature: 1-audit-log T1.1 (webworks routes)**
    **Property: A limit less than MIN_LIMIT (1) is clamped to
    MIN_LIMIT. Callers cannot ask for zero rows.**
    """
    session = _FakeSession(rows=[])
    request = _FakeRequest(
        path="/api/v1/audit", db_session=session, query={"limit": "0"}
    )
    audit_routes.handle_list_audit_records(request)
    testbase.assert_equal(session.captured_limit, audit_routes.MIN_LIMIT)
    return


def test_handle_list_returns_400_on_non_integer_limit():
    """
    **Feature: 1-audit-log T1.1 (webworks routes)**
    **Property: A non-integer limit returns 400 problem+json. The
    flask controller had the same guard.**
    """
    session = _FakeSession(rows=[])
    request = _FakeRequest(
        path="/api/v1/audit", db_session=session, query={"limit": "abc"}
    )
    response = audit_routes.handle_list_audit_records(request)
    testbase.assert_equal(response.status_code, 400)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_BAD_REQUEST)
    testbase.assert_equal(body["instance"], "/api/v1/audit")
    return


# ---------------------------------------------------------------------------
# handle_read_audit_record — happy and 404 paths
# ---------------------------------------------------------------------------


def test_handle_read_returns_serialized_record_on_match():
    """
    **Feature: 1-audit-log T1.1 (webworks routes)**
    **Property: Returns 200 with the serialized record dict when
    the sequence_number matches.**
    """
    record = _FakeRecord(
        sequence_number=42, record_id="rec-42", kind="auth.login"
    )
    session = _FakeSession(first_value=record)
    request = _FakeRequest(
        path="/api/v1/audit/42",
        path_params={"sequence_number": 42},
        db_session=session,
    )
    response = audit_routes.handle_read_audit_record(request)
    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(body["sequence_number"], 42)
    testbase.assert_equal(body["record_id"], "rec-42")
    testbase.assert_equal(body["kind"], "auth.login")
    return


def test_handle_read_returns_404_with_sequence_number_extension():
    """
    **Feature: 1-audit-log T1.1 (webworks routes)**
    **Property: An unknown sequence_number returns 404 with the
    sequence_number carried as an extension member so wire
    consumers can correlate the error without re-parsing the detail
    string.**
    """
    session = _FakeSession(first_value=None)
    request = _FakeRequest(
        path="/api/v1/audit/9999",
        path_params={"sequence_number": 9999},
        db_session=session,
    )
    response = audit_routes.handle_read_audit_record(request)
    testbase.assert_equal(response.status_code, 404)
    body = _decode_body(response)
    testbase.assert_equal(body["type"], PROBLEM_TYPE_NOT_FOUND)
    testbase.assert_equal(body["sequence_number"], 9999)
    testbase.assert_equal(body["instance"], "/api/v1/audit/9999")
    return


# ---------------------------------------------------------------------------
# Record serialization edge cases
# ---------------------------------------------------------------------------


def test_record_serialization_emits_hex_record_hash_when_present():
    """
    **Feature: 1-audit-log T1.1 (webworks routes)**
    **Property: ``record_hash`` bytes serialize to lowercase hex
    string. The flask controller already had this contract;
    preserving it keeps wire consumers stable.**
    """
    record = _FakeRecord(
        sequence_number=1, record_hash=bytes.fromhex("deadbeef")
    )
    session = _FakeSession(first_value=record)
    request = _FakeRequest(
        path="/api/v1/audit/1",
        path_params={"sequence_number": 1},
        db_session=session,
    )
    response = audit_routes.handle_read_audit_record(request)
    body = _decode_body(response)
    testbase.assert_equal(body["record_hash_hex"], "deadbeef")
    return


def test_record_serialization_handles_null_optional_fields():
    """
    **Feature: 1-audit-log T1.1 (webworks routes)**
    **Property: actor_user_id, payload_json, record_hash, and
    written_at all gracefully serialize to ``None`` when the ORM
    row has no value. Crash-on-None would break legitimate audit
    records (some kinds have no actor).**
    """
    record = _FakeRecord(
        sequence_number=1,
        actor_user_id=None,
        payload_json=None,
        record_hash=None,
        written_at=None,
    )
    session = _FakeSession(first_value=record)
    request = _FakeRequest(
        path="/api/v1/audit/1",
        path_params={"sequence_number": 1},
        db_session=session,
    )
    response = audit_routes.handle_read_audit_record(request)
    body = _decode_body(response)
    testbase.assert_equal(body["actor_user_id"], None)
    testbase.assert_equal(body["payload_json"], None)
    testbase.assert_equal(body["record_hash_hex"], None)
    testbase.assert_equal(body["written_at"], None)
    return


# ---------------------------------------------------------------------------
# Bootstrap source-smoke
# ---------------------------------------------------------------------------


def test_bootstrap_imports_register_audit_routes_and_calls_it():
    """
    **Feature: 1-audit-log T1.1 (webworks routes)**
    **Property: app_pychestrate_main.py wires register_audit_routes
    into register_service_extensions so the routes are queued before
    app.startup. Source-level smoke; full app boot is out of scope
    for the singlehost suite.**
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
        "from automojo.pychestrate.webservice.audit.restapi.v1.audit_routes import"
        in text
    )
    has_call = "register_audit_routes(app=app, version_prefix=\"/api/v1\")" in text
    testbase.assert_equal(has_import, True)
    testbase.assert_equal(has_call, True)
    return


# ---------------------------------------------------------------------------
# Wire-shape: every error response is application/problem+json
# ---------------------------------------------------------------------------


def test_every_error_response_is_application_problem_json():
    """
    **Feature: 1-audit-log T1.1 (webworks routes)**
    **Property: 503 / 400 / 404 all carry the documented
    ``application/problem+json`` content type and round-trip through
    the real ``JSONResponse`` class.**
    """
    cases = []

    cases.append(audit_routes.handle_list_audit_records(
        _FakeRequest(path="/api/v1/audit", db_session=None)
    ))

    cases.append(audit_routes.handle_list_audit_records(
        _FakeRequest(
            path="/api/v1/audit",
            db_session=_FakeSession(rows=[]),
            query={"limit": "garbage"},
        )
    ))

    cases.append(audit_routes.handle_read_audit_record(
        _FakeRequest(
            path="/api/v1/audit/9999",
            path_params={"sequence_number": 9999},
            db_session=_FakeSession(first_value=None),
        )
    ))

    for response in cases:
        testbase.assert_equal(
            response.headers["Content-Type"], PROBLEM_JSON_MEDIA_TYPE
        )
        is_json_response = isinstance(response, JSONResponse)
        testbase.assert_equal(is_json_response, True)
    return
