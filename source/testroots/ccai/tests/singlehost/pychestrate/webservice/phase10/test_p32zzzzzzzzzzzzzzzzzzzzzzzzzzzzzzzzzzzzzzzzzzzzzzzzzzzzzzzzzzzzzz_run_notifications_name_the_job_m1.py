"""
.. module:: test_p32zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz_run_notifications_name_the_job_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: A run notification says what ran, who started it and where to open it (audit ORG-F08).

.. moduleauthor:: Code Craft AI LLC

A failed-run message said "Run 48f18a78-8155-470e-b6cb-965f409f1964 failed in lab-project" and nothing else a reader could act on at a glance. It now names the job, says who started it and links the
run when the service has a public URL; an event with none of that known keeps the plain message.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import uuid

from ccai import testbase

from ccai.pychestrate.webservice.identity.users.models import IdentityUser
from ccai.pychestrate.webservice.jobs.run.state import repository as run_repo
from ccai.pychestrate.webservice.notifications import run_notifier
from ccai.pychestrate.webservice.notifications.extensions.run_failed_template import RunFailedTemplate
from ccai.pychestrate.webservice.notifications.extensions.run_succeeded_template import RunSucceededTemplate
from ccai.pychestrate.webservice.orchestration.rpa.models import RpaExecutionMode, RpaJob, RpaJobStatus
from ccai.pychestrate.webservice.orchestration.test.models import TestRun
from ccai.pychestrate.webservice.projects.models import Project
from ccai.pychestrate.webservice.runs.restapi.v1 import runs_routes

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import build_in_memory_session


RUN = "48f18a78-8155-470e-b6cb-965f409f1964"


def test_the_templates_name_the_job_who_started_it_and_the_link_when_known():
    """
    **Feature: run notifications (ORG-F08)**
    **Property: with a job name the subject is "<job> (<first 8 of the run id>) failed in <project>" (or "completed in"), and the body has Job, Run id, Project, Triggered by, Reason (Note on
    success) and Open lines, each only when known; with none of them it is the plain "Run <id> failed in <project>" message with Run id, Project and Reason.**
    """
    full = {"run_id": RUN, "project_slug": "lab", "reason": "RPA job exited with code 1: the ledger is unreachable", "job_name": "tasker-bad", "triggered_by": "Ada Lovelace",
            "run_url": "https://pyc.example.test/runs/" + RUN}
    plain = {"run_id": RUN, "project_slug": "lab", "reason": "boom"}
    failed_full, failed_plain = RunFailedTemplate.render(payload=full), RunFailedTemplate.render(payload=plain)
    done_full, done_plain = RunSucceededTemplate.render(payload=dict(full, reason="")), RunSucceededTemplate.render(payload=dict(plain, reason=""))

    testbase.assert_equal(
        (failed_full.subject, failed_full.body.split("\n"), failed_plain.subject, failed_plain.body.split("\n"), done_full.subject, done_full.body.split("\n"), done_plain.subject, done_plain.body.split("\n")),
        (
            "[Pychestrate] tasker-bad (48f18a78) failed in lab",
            ["Job: tasker-bad", "Run id: " + RUN, "Project: lab", "Triggered by: Ada Lovelace", "Reason: RPA job exited with code 1: the ledger is unreachable", "Open: https://pyc.example.test/runs/" + RUN],
            "[Pychestrate] Run {} failed in lab".format(RUN),
            ["Run id: " + RUN, "Project: lab", "Reason: boom"],
            "[Pychestrate] tasker-bad (48f18a78) completed in lab",
            ["Job: tasker-bad", "Run id: " + RUN, "Project: lab", "Triggered by: Ada Lovelace", "Open: https://pyc.example.test/runs/" + RUN],
            "[Pychestrate] Run {} completed in lab".format(RUN),
            ["Run id: " + RUN, "Project: lab"],
        ),
    )
    return


def test_the_payload_has_who_started_the_run_and_a_link_and_a_missing_run_is_still_described():
    """
    **Feature: run notifications (ORG-F08)**
    **Property: for a test run started by a user the payload built from a run event has that user's name (display name), the run's type and, when ``PYCHESTRATE_PUBLIC_BASE_URL`` is set, a link to
    ``/runs/<id>``; for an event whose run is unknown (or with no URL set) those are None and the message is still built.**
    """
    _engine, session = build_in_memory_session()
    project_id, user_id, run_id = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    session.add(Project(project_id=project_id, slug="lab-project", display_name="Lab"))
    session.add(IdentityUser(user_id=user_id, login_name="ada", primary_email="ada@example.test", display_name="Ada Lovelace"))
    run_repo.create_run(db_session=session, run_id=run_id, project_id=project_id, job_type="testbase")
    session.add(TestRun(run_id=run_id, project_id=project_id, catalog_entry_id=str(uuid.uuid4()), runner_kind="testbase", triggered_by=user_id))
    session.commit()

    saved = os.environ.get("PYCHESTRATE_PUBLIC_BASE_URL")
    try:
        os.environ["PYCHESTRATE_PUBLIC_BASE_URL"] = "https://pyc.example.test/"
        known = run_notifier.build_template_payload(db_session=session, event_payload={"run_id": run_id, "project_id": project_id, "to_state": "FAILED", "reason": "1 of 2 tests failed."})
        unknown = run_notifier.build_template_payload(db_session=session, event_payload={"run_id": str(uuid.uuid4()), "project_id": project_id, "to_state": "FAILED", "reason": ""})
        os.environ.pop("PYCHESTRATE_PUBLIC_BASE_URL", None)
        no_url = run_notifier.build_template_payload(db_session=session, event_payload={"run_id": run_id, "project_id": project_id, "to_state": "FAILED", "reason": ""})
    finally:
        if saved is None:
            os.environ.pop("PYCHESTRATE_PUBLIC_BASE_URL", None)
        else:
            os.environ["PYCHESTRATE_PUBLIC_BASE_URL"] = saved
    described = runs_routes.describe_run(db_session=session, run_id=run_id)

    testbase.assert_equal(
        (known["triggered_by"], known["job_type"], known["run_url"], known["project_slug"], unknown["triggered_by"], unknown["job_type"], no_url["run_url"], described["triggered_by"]),
        ("Ada Lovelace", "testbase", "https://pyc.example.test/runs/" + run_id, "lab-project", None, None, None, "Ada Lovelace"),
    )
    return


def test_an_rpa_run_is_named_by_its_specification_not_its_job_type():
    """
    **Feature: run notifications (ORG-F08)**
    **Property: an RPA run, which the envelope names "rpa:<job type>" for every specification, is named by the specification its job ran from (so a passing and a failing job of one type are told apart
    in the Runs list, the API and notifications); an RPA job with no specification name, and a run of another kind, keep the envelope's name.**
    """
    _engine, session = build_in_memory_session()
    project_id = str(uuid.uuid4())
    named, nameless, other = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    for run_id, job_type in ((named, "rpa-tasker"), (nameless, "rpa-process"), (other, "build-makefile")):
        run_repo.create_run(db_session=session, run_id=run_id, project_id=project_id, job_type=job_type)
    for run_id, spec_name in ((named, "nightly-ledger-import"), (nameless, "")):
        session.add(RpaJob(
            job_id=run_id, project_id=project_id, spec_id=None, spec_name=spec_name, type_id="tasker-demo", resolved_version="1.0.0", execution_mode=RpaExecutionMode.TASKER,
            status=RpaJobStatus.SUCCEEDED,
        ))
    session.commit()

    def _name(run_id: str, envelope_name: object) -> object:
        return runs_routes._rpa_spec_name_for(db_session=session, run_id=run_id, job_type=run_repo.get_run(db_session=session, run_id=run_id).job_type, job_name=envelope_name)

    testbase.assert_equal(
        (_name(named, "rpa:tasker-demo"), _name(nameless, "rpa:tasker-demo"), _name(other, "build:makefile")),
        ("nightly-ledger-import", "rpa:tasker-demo", "build:makefile"),
    )
    return
