"""
.. module:: test_p32zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz_run_triggered_by_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The runs API says who started a run (ORC-11).

.. moduleauthor:: Code Craft AI LLC

A test run records the user who triggered it and a build records its actor, but the runs API never returned either, so no page could say who started a run. ``triggered_by`` is now
that user's name (display name, else login); a run started by something else, or by a user who no longer exists, has none.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import uuid

from ccai import testbase

from ccai.pychestrate.webservice.identity.users.models import IdentityUser
from ccai.pychestrate.webservice.jobs.run.state import repository as run_repo
from ccai.pychestrate.webservice.orchestration.build.models import BuildRun
from ccai.pychestrate.webservice.orchestration.test.models import TestRun
from ccai.pychestrate.webservice.runs.restapi.v1 import runs_routes

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import build_in_memory_session


PROJECT = "00000000-0000-4000-8000-0000000000d1"


def _user(session: object, *, login: str, display_name: str) -> str:
    user_id = str(uuid.uuid4())
    session.add(IdentityUser(user_id=user_id, login_name=login, primary_email="{}@example.test".format(login), display_name=display_name))
    session.flush()
    return user_id


def _run(session: object, *, job_type: str) -> str:
    run_id = str(uuid.uuid4())
    run_repo.create_run(db_session=session, run_id=run_id, project_id=PROJECT, job_type=job_type)
    return run_id


def _test_run(session: object, *, triggered_by: object) -> str:
    run_id = _run(session, job_type="testbase")
    session.add(TestRun(run_id=run_id, project_id=PROJECT, catalog_entry_id=str(uuid.uuid4()), runner_kind="testbase", triggered_by=triggered_by))
    session.flush()
    return run_id


def _build_run(session: object, *, actor_id: object, pipeline_run_id: object = None) -> str:
    run_id = _run(session, job_type="build-makefile")
    session.add(BuildRun(run_id=run_id, project_id=PROJECT, runner_kind="makefile", actor_id=actor_id, pipeline_run_id=pipeline_run_id))
    session.flush()
    return run_id


def _name(session: object, run_id: str) -> object:
    return runs_routes._triggered_by_name(db_session=session, run_id=run_id)


def test_a_run_is_triggered_by_the_user_named_on_its_test_run_or_build():
    """
    **Feature: who triggered a run (ORC-11)**
    **Property: a test run's ``triggered_by`` and a build's ``actor_id`` name the user: the display name when they have one, their login when not; a run no feature table
    knows, a build started by a pipeline (no actor), a run with no recorded user and a run whose user no longer exists have no name.**
    """
    _engine, session = build_in_memory_session()
    ada = _user(session, login="ada", display_name="Ada Lovelace")
    grace = _user(session, login="grace", display_name="")
    gone = str(uuid.uuid4())
    runs = {
        "test": _test_run(session, triggered_by=ada),
        "build": _build_run(session, actor_id=grace),
        "pipeline": _build_run(session, actor_id=None, pipeline_run_id=str(uuid.uuid4())),
        "nobody": _test_run(session, triggered_by=None),
        "removed": _test_run(session, triggered_by=gone),
        "unknown": str(uuid.uuid4()),
    }
    session.commit()

    testbase.assert_equal(
        {key: _name(session, run_id) for key, run_id in runs.items()},
        {"test": "Ada Lovelace", "build": "grace", "pipeline": None, "nobody": None, "removed": None, "unknown": None},
    )
    return


def test_the_run_the_api_returns_carries_the_name():
    """
    **Feature: who triggered a run (ORC-11)**
    **Property: the run as the API serializes it (list rows and the single read use the same function) has ``triggered_by``, ``null`` when nobody is recorded.**
    """
    _engine, session = build_in_memory_session()
    ada = _user(session, login="ada", display_name="Ada Lovelace")
    started = _test_run(session, triggered_by=ada)
    unattended = _test_run(session, triggered_by=None)
    session.commit()

    def _api_value(run_id: str) -> object:
        row = run_repo.get_run(db_session=session, run_id=run_id)
        return runs_routes._run_to_dict(row=row, db_session=session)["triggered_by"]

    testbase.assert_equal((_api_value(started), _api_value(unattended)), ("Ada Lovelace", None))
    return


def test_the_csv_export_has_the_column_last():
    """
    **Feature: who triggered a run (ORC-11)**
    **Property: the spreadsheet export gains ``triggered_by`` as its last column, so a script reading the earlier columns by position still works.**
    """
    testbase.assert_equal((runs_routes.CSV_EXPORT_COLUMNS[-1], runs_routes.CSV_EXPORT_COLUMNS[-2]), ("triggered_by", "pod_id"))
    return
