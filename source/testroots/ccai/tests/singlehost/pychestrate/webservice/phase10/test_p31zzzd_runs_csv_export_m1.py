"""
.. module:: test_p31zzzd_runs_csv_export_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The runs list downloads as a spreadsheet-safe CSV (ORG-F22).

.. moduleauthor:: Code Craft AI LLC

There was no export anywhere for a manager or an auditor. ``GET /api/v1/runs?
format=csv`` returns the whole filtered list (not one page) as a CSV
attachment: run id, project, job name and type, state, outcome, the three
times, the duration and the pod. Every cell is written so that a spreadsheet
cannot read it as a formula (a job name is chosen by whoever wrote the job).
The handler runs here against a real in-memory database.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import csv
import io
import uuid

from typing import Any, Dict, List, Optional

from ccai import testbase
from ccai.testbase.mocking import create_module_patch

from ccai.pychestrate.webservice.csv_export import render_csv, spreadsheet_safe
from ccai.pychestrate.webservice.jobs.run.state import repository as run_repo
from ccai.pychestrate.webservice.jobs.run.state.enums import RunState
from ccai.pychestrate.webservice.runs.restapi.v1 import runs_routes

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import build_in_memory_session


PROJECT_A = "00000000-0000-4000-8000-0000000000a1"
PROJECT_B = "00000000-0000-4000-8000-0000000000b2"


class _Query:
    def __init__(self, values: Dict[str, str]) -> None:
        self._values = values

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        return self._values.get(key, default)


class _Request:
    def __init__(self, *, db_session: Any, query: Dict[str, str]) -> None:
        self.path = "/api/v1/runs"
        self.path_params: Dict[str, Any] = {}
        self.query_params = _Query(query)
        self.db_session = db_session
        self.auth_principal = type("Principal", (), {"user_id": "user-1"})()


class _Allowed:
    allowed = True
    reason = ""


def _export(session: Any, **query: str) -> Any:
    patch = create_module_patch(runs_routes.rbac_evaluator, "check_permission")
    mock = patch.activate()
    mock.configure(side_effect=lambda **kwargs: _Allowed())
    try:
        rtnval = runs_routes.handle_list_runs(_Request(db_session=session, query=dict({"format": "csv"}, **query)))
    finally:
        patch.deactivate()
    return rtnval


def _rows(response: Any) -> List[Dict[str, str]]:
    return list(csv.DictReader(io.StringIO(response.body.decode("utf-8"))))


def _seed() -> Any:
    _engine, session = build_in_memory_session()
    for project, job_type, state in (
        (PROJECT_A, "testbase", RunState.PENDING),
        (PROJECT_A, "build-makefile", RunState.PENDING),
        (PROJECT_B, "testbase", RunState.PENDING),
    ):
        run_repo.create_run(db_session=session, run_id=str(uuid.uuid4()), project_id=project, job_type=job_type, initial_state=state)
    session.commit()
    return session


def test_a_cell_that_would_be_a_formula_is_written_as_text():
    """
    **Feature: CSV export (ORG-F22)**
    **Property: a value starting with =, +, - or @ (or a tab) is written with
    a leading apostrophe; ordinary text, numbers and empty cells are left
    alone.**
    """
    cells = [spreadsheet_safe(value) for value in ("=cmd|' /C calc'!A0", "+1+1", "-2", "@SUM(A1)", "\tx", "nightly", 12, None)]

    testbase.assert_equal(
        cells,
        ["'=cmd|' /C calc'!A0", "'+1+1", "'-2", "'@SUM(A1)", "'\tx", "nightly", "12", ""],
    )
    return


def test_a_dangerous_job_name_survives_the_round_trip_as_text():
    """
    **Feature: CSV export (ORG-F22)**
    **Property: a job name of ``=HYPERLINK(...)`` comes back from a CSV
    parser with the apostrophe in front, so a spreadsheet shows it and does not
    run it.**
    """
    body = render_csv(columns=["job_name", "state"], rows=[{"job_name": '=HYPERLINK("http://x","y")', "state": "failed"}])
    parsed = list(csv.DictReader(io.StringIO(body.decode("utf-8"))))

    testbase.assert_equal(parsed, [{"job_name": "'=HYPERLINK(\"http://x\",\"y\")", "state": "failed"}])
    return


def test_the_export_is_the_whole_filtered_list_as_an_attachment():
    """
    **Feature: CSV export (ORG-F22)**
    **Property: ``format=csv`` answers 200 ``text/csv`` with an attachment
    name, a header row of the documented columns, one row per run (paging does
    not apply), and ``project_id`` and ``state`` narrow it.**
    """
    session = _seed()
    everything = _export(session, per_page="1")
    one_project = _export(session, project_id=PROJECT_B)
    none = _export(session, state="completed")

    testbase.assert_equal(
        (
            everything.status_code,
            everything.headers["Content-Type"].split(";")[0],
            everything.headers["Content-Disposition"].startswith('attachment; filename="pychestrate-runs-'),
            list(_rows(everything)[0].keys()) == list(runs_routes.CSV_EXPORT_COLUMNS),
            len(_rows(everything)),
            [row["project_id"] for row in _rows(one_project)],
            len(_rows(none)),
            "X-Export-Truncated" in everything.headers,
        ),
        (200, "text/csv", True, True, 3, [PROJECT_B], 0, False),
    )
    return


def test_an_export_past_the_row_limit_is_cut_and_says_so():
    """
    **Feature: CSV export (ORG-F22)**
    **Property: with more runs than the row limit the file holds the limit's
    worth and carries ``X-Export-Truncated: true``.**
    """
    session = _seed()
    original = runs_routes.CSV_EXPORT_MAX_ROWS
    runs_routes.CSV_EXPORT_MAX_ROWS = 2
    try:
        response = _export(session)
    finally:
        runs_routes.CSV_EXPORT_MAX_ROWS = original

    testbase.assert_equal((len(_rows(response)), response.headers.get("X-Export-Truncated")), (2, "true"))
    return
