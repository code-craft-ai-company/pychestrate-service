"""
.. module:: test_p31zzzj_run_results_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: A run's test results are listed, failing tests first, with the reason (ORC-10).

.. moduleauthor:: Code Craft AI LLC

The ingest tables kept every test's result and its raw testbase record but no
API exposed them, so a failed run showed counts and no reason.
``GET /api/v1/runs/{run_id}/results`` now lists them: failing tests first, each
with the exception type, message and stack frames (with source lines), bounded
because the record is pod output. The handler runs against a real in-memory
database with the permission check patched.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from ccai import testbase
from ccai.testbase.mocking import create_module_patch

from ccai.pychestrate.core.defaults import new_uuid
from ccai.pychestrate.webservice.ingest.result.models import TaskResult
from ccai.pychestrate.webservice.runs.restapi.v1 import runs_routes
from ccai.pychestrate.webservice.runs.restapi.v1 import task_results

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import build_in_memory_session


RUN: str = "0f6c2c1e-9999-4000-8000-000000000001"
OTHER_RUN: str = "0f6c2c1e-9999-4000-8000-000000000002"
PROJECT: str = "0f6c2c1e-9999-4000-8000-0000000000aa"
START = datetime(2026, 9, 29, 12, 0, 0, tzinfo=timezone.utc)


class _Query:
    def __init__(self, values: Dict[str, str]) -> None:
        self._values = values

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        return self._values.get(key, default)


class _Request:
    def __init__(self, *, session: Any, run_id: str = RUN, query: Optional[Dict[str, str]] = None, principal: Any = True) -> None:
        self.path = "/api/v1/runs/{}/results".format(run_id)
        self.path_params = {"run_id": run_id}
        self.query_params = _Query(query or {})
        self.db_session = session
        self.auth_principal = type("Principal", (), {"user_id": "user-1"})() if principal else None


class _Decision:
    def __init__(self, allowed: bool) -> None:
        self.allowed = allowed
        self.reason = ""


def _frames(count: int, lines: int = 1) -> List[Dict[str, Any]]:
    return [
        {"origin": {"file": "/lab/test_{}.py".format(index), "lineno": index + 1, "scope": "scope_{}".format(index)},
         "call": "call()", "code": ["{}: line".format(number) for number in range(lines)], "context": None}
        for index in range(count)
    ]


def _add(session: Any, *, name: str, result: str, run_id: str = RUN, detail: Any = None, seconds: float = 0.5, payload: Any = "default") -> None:
    raw = {"name": name, "result": result, "detail": detail if detail is not None else {"errors": [], "failures": [], "warnings": []}}
    session.add(TaskResult(
        task_id=new_uuid(), run_id=run_id, project_id=PROJECT, test_name=name, instance_uuid=str(new_uuid()),
        rtype="TEST", result=result, started_at=START, finished_at=START + timedelta(seconds=seconds),
        raw_payload=raw if payload == "default" else payload,
    ))


def _seeded_session() -> Any:
    _engine, session = build_in_memory_session()
    failure = {"extype": "AssertionError", "exargs": ["EXPECTED: 2\nFOUND: 1"], "traces": _frames(2, lines=3)}
    _add(session, name="t.test_b_passes", result="PASSED")
    _add(session, name="t.test_a_passes", result="PASSED")
    _add(session, name="t.test_skipped", result="SKIPPED")
    _add(session, name="t.test_unset", result="UNSET")
    _add(session, name="t.test_z_fails", result="FAILED", detail={"errors": [], "failures": [failure], "warnings": []}, seconds=1.25)
    _add(session, name="t.test_m_errors", result="ERRORED", detail={"errors": [{"extype": "RuntimeError", "exargs": ["boom"], "traces": []}], "failures": [], "warnings": []})
    _add(session, name="t.other_run_fails", result="FAILED", run_id=OTHER_RUN)
    session.commit()
    return session


def _call(session: Any, *, allowed: bool = True, run_exists: bool = True, **request_options: Any) -> Any:
    permission = create_module_patch(runs_routes.rbac_evaluator, "check_permission")
    permission.activate().configure(side_effect=lambda **kwargs: _Decision(allowed))
    finder = create_module_patch(runs_routes.run_repo, "find_run")
    finder.activate().configure(side_effect=lambda **kwargs: object() if run_exists else None)
    try:
        response = runs_routes.handle_list_run_results(_Request(session=session, **request_options))
    finally:
        finder.deactivate()
        permission.deactivate()
    return response.status_code, json.loads(response.body.decode("utf-8"))


def test_failing_tests_come_first_then_the_rest_by_name_and_only_this_runs_tests():
    """
    **Feature: run results (ORC-10)**
    **Property: the list puts failed and errored tests first, then skipped and
    unset, then passed, each group by name; another run's tests are absent; the
    meta counts every test in the run per result.**
    """
    status, body = _call(_seeded_session())

    testbase.assert_equal(
        (status, [item["test_name"] for item in body["items"]], body["meta"]["total"], body["meta"]["by_result"]),
        (
            200,
            ["t.test_m_errors", "t.test_z_fails", "t.test_skipped", "t.test_unset", "t.test_a_passes", "t.test_b_passes"],
            6,
            {"PASSED": 2, "SKIPPED": 1, "UNSET": 1, "FAILED": 1, "ERRORED": 1},
        ),
    )
    return


def test_a_failing_test_carries_its_exception_message_frames_and_duration():
    """
    **Feature: run results (ORC-10)**
    **Property: a failed test lists its problem with the exception type, the
    message, and each frame's file, line, scope and source lines, and its
    duration in seconds; a passing test lists no problems.**
    """
    _status, body = _call(_seeded_session(), query={"failed": "true"})
    failed = next(item for item in body["items"] if item["test_name"] == "t.test_z_fails")
    problem = failed["problems"][0]

    testbase.assert_equal(
        (failed["result"], failed["duration_seconds"], problem["kind"], problem["type"], problem["message"], problem["frames"][1]),
        (
            "FAILED", 1.25, "failure", "AssertionError", "EXPECTED: 2\nFOUND: 1",
            {"file": "/lab/test_1.py", "line": 2, "scope": "scope_1", "code": ["0: line", "1: line", "2: line"]},
        ),
    )
    return


def test_failed_true_leaves_out_quiet_results_and_paging_counts_what_is_left():
    """
    **Feature: run results (ORC-10)**
    **Property: ``failed=true`` returns only failed and errored tests; the
    total is the number left; ``per_page``/``page`` slice the ordered list; the
    meta still counts every result in the run.**
    """
    session = _seeded_session()
    _s1, only = _call(session, query={"failed": "true"})
    _s2, second = _call(session, query={"per_page": "2", "page": "2"})

    testbase.assert_equal(
        (
            [item["result"] for item in only["items"]], only["meta"]["total"], only["meta"]["by_result"]["PASSED"],
            [item["test_name"] for item in second["items"]], second["meta"]["total"], second["meta"]["page"], second["meta"]["per_page"],
        ),
        (["ERRORED", "FAILED"], 2, 2, ["t.test_skipped", "t.test_unset"], 6, 2, 2),
    )
    return


def test_pod_output_is_bounded_and_a_malformed_record_does_not_break_the_list():
    """
    **Feature: run results (ORC-10)**
    **Property: a message longer than the limit is cut, frames and source lines
    are capped, and a record whose detail is not the expected shape (text, a
    missing payload, a trace that is not a mapping) still lists the test.**
    """
    _engine, session = build_in_memory_session()
    huge = {"extype": "E", "exargs": ["x" * (task_results.MAX_MESSAGE_CHARS * 3)], "traces": _frames(task_results.MAX_FRAMES + 8, lines=task_results.MAX_CODE_LINES + 6)}
    _add(session, name="t.huge", result="FAILED", detail={"errors": [], "failures": [huge], "warnings": []})
    _add(session, name="t.detail_is_text", result="FAILED", detail="not a mapping")
    _add(session, name="t.no_payload", result="FAILED", payload=None)
    _add(session, name="t.bad_trace", result="FAILED", detail={"errors": [], "failures": [{"extype": "E", "exargs": None, "traces": ["nope", 7]}], "warnings": ["plain warning"]})
    session.commit()
    _status, body = _call(session)
    by_name = {item["test_name"]: item for item in body["items"]}
    huge_problem = by_name["t.huge"]["problems"][0]

    testbase.assert_equal(
        (
            len(huge_problem["message"]), len(huge_problem["frames"]), len(huge_problem["frames"][0]["code"]),
            by_name["t.detail_is_text"]["problems"], by_name["t.no_payload"]["problems"],
            [(problem["kind"], problem["message"], problem["frames"]) for problem in by_name["t.bad_trace"]["problems"]],
        ),
        (
            task_results.MAX_MESSAGE_CHARS, task_results.MAX_FRAMES, task_results.MAX_CODE_LINES,
            [], [],
            [("failure", "", []), ("warning", "plain warning", [])],
        ),
    )
    return


def test_the_endpoint_is_read_guarded_and_answers_problems_for_bad_requests():
    """
    **Feature: run results (ORC-10)**
    **Property: no principal answers 401, a denied permission 403, an unknown
    run 404, a non-numeric ``per_page`` 400 and a value over the limit 400.**
    """
    session = _seeded_session()
    statuses = (
        _call(session, principal=False)[0],
        _call(session, allowed=False)[0],
        _call(session, run_exists=False)[0],
        _call(session, query={"per_page": "abc"})[0],
        _call(session, query={"per_page": str(runs_routes.MAX_RESULTS_PAGE_SIZE + 1)})[0],
    )

    testbase.assert_equal(statuses, (401, 403, 404, 400, 400))
    return
