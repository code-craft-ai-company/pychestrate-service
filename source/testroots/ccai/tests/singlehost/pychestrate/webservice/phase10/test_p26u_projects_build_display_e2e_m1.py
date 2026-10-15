"""
.. module:: test_p26u_projects_build_display_e2e_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: End-to-end tests that the projects pages show builds,
               watch targets and RPA jobs accurately (PRJ-33).

.. moduleauthor:: Code Craft AI LLC

Cancelled builds read "Started: Pending" in failure red, builds without
a commit showed "HEAD", queued builds could not be cancelled or
filtered, watch actions named their target "#2", and the RPA job page
showed raw UUIDs for the user, pod and client.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import re
import uuid

from typing import Any, Dict

from ccai import testbase

from ccai.pychestrate.core.defaults import new_uuid
from ccai.tests.singlehost.pychestrate.webservice.phase10._e2e_harness import (
    drive_request,
    ensure_app,
    ensure_seeded_admin,
    logged_in_cookies,
)
from ccai.tests.singlehost.pychestrate.webservice.phase10._projects_ui_helpers import (
    create_project_via_ui,
    get_page,
    open_db_session,
)


def _setup(*, build_status: str, commit_sha: str = "HEAD") -> Dict[str, Any]:
    """
        A project with a repository, a build specification, one build in
        ``build_status`` and a watch that runs the specification.
    """
    from ccai.pychestrate.core.orm import (  # noqa: E402
        ProjectBuild, ProjectBuildSpec, ProjectRepository, ProjectWatch,
    )

    handle = ensure_app()
    cookies = logged_in_cookies(wsgi_app=handle.wsgi_app)
    project_id = create_project_via_ui(wsgi_app=handle.wsgi_app, cookies=cookies, prefix="prj33")
    db_session = open_db_session()
    try:
        repository = ProjectRepository(
            project_id=project_id, name="app", url="https://git.example.invalid/app.git",
            auth_type="none", default_branch="main",
        )
        db_session.add(repository)
        db_session.flush()
        spec = ProjectBuildSpec(project_id=project_id, repository_id=repository.id, name="nightly-build")
        db_session.add(spec)
        db_session.flush()
        build = ProjectBuild(
            project_id=project_id, spec_id=spec.id, spec_version=1, branch="main", commit_sha=commit_sha,
            status=build_status, trigger_type="manual", triggered_by_id=ensure_seeded_admin().user_id,
        )
        watch = ProjectWatch(
            project_id=project_id, name="build-on-push", trigger_source="repository_commit",
            source_id=repository.id, repository_id=repository.id, conditions_json={},
            actions_json=[{"action": "trigger_build", "target_id": spec.id, "parameters": {}}],
            enabled=True, trigger_count=0,
        )
        db_session.add(build)
        db_session.add(watch)
        db_session.commit()
        rtnval = {
            "wsgi_app": handle.wsgi_app, "cookies": cookies, "project_id": project_id,
            "build_id": build.id, "watch_id": watch.id,
        }
    finally:
        db_session.close()
    return rtnval


def _page(setup: Dict[str, Any], path: str) -> str:
    rtnval = get_page(wsgi_app=setup["wsgi_app"], path=path, cookies=setup["cookies"]).text
    return rtnval


def _build_row(page: str, build_id: int) -> str:
    match = re.search(r"<tr>\s*<td>\s*<a [^>]*>\s*#{}\s*</a>.*?</tr>".format(build_id), page, re.S)
    rtnval = match.group(0) if match else ""
    return rtnval


def test_a_cancelled_build_is_neutral_and_never_started():
    """
    **Feature: projects (PRJ-33 build display)**
    **Property: in the build list a cancelled build has a neutral
    "cancelled" badge and "Never started" (it read "Pending" in failure
    red).**
    """
    setup = _setup(build_status="cancelled")
    row = _build_row(_page(setup, "/projects/{}/builds".format(setup["project_id"])), setup["build_id"])

    testbase.assert_equal(
        ('badge-secondary">cancelled' in row, "Never started" in row, "Pending" in row),
        (True, True, False),
    )
    return


def test_a_build_without_a_commit_shows_the_branch():
    """
    **Feature: projects (PRJ-33 build display)**
    **Property: a build whose commit is not known yet shows "Latest on
    main" instead of "HEAD".**
    """
    setup = _setup(build_status="pending")
    row = _build_row(_page(setup, "/projects/{}/builds".format(setup["project_id"])), setup["build_id"])

    testbase.assert_equal(("Latest on main" in row, ">HEAD<" in row), (True, False))
    return


def test_a_queued_build_can_be_cancelled_and_filtered():
    """
    **Feature: projects (PRJ-33 build display)**
    **Property: a queued build's page offers Cancel, and the build list
    can be filtered to queued builds.**
    """
    setup = _setup(build_status="queued")
    detail = _page(setup, "/projects/{}/builds/{}".format(setup["project_id"], setup["build_id"]))
    listing = drive_request(
        wsgi_app=setup["wsgi_app"], method="GET", path="/projects/{}/builds".format(setup["project_id"]),
        query_string="status=queued", cookies=setup["cookies"],
    ).text

    testbase.assert_equal(
        ("/builds/{}/cancel".format(setup["build_id"]) in detail,
         '<option value="queued" selected>Queued</option>' in listing,
         _build_row(listing, setup["build_id"]) != ""),
        (True, True, True),
    )
    return


def test_a_watch_names_the_specification_it_runs():
    """
    **Feature: projects (PRJ-33 build display)**
    **Property: the watch page names the build specification its action
    runs instead of "Build specification #N".**
    """
    setup = _setup(build_status="succeeded", commit_sha="abc1234")
    page = _page(setup, "/projects/{}/watches/{}".format(setup["project_id"], setup["watch_id"]))

    testbase.assert_equal(("nightly-build</a>" in page, "Build specification #" in page), (True, False))
    return


def test_an_rpa_job_names_its_user_pod_and_client():
    """
    **Feature: projects (PRJ-33 build display)**
    **Property: the RPA job page shows who triggered the job and the pod
    and client that ran it by name, not UUID.**
    """
    from ccai.pychestrate.webservice.clients.models import Client  # noqa: E402
    from ccai.pychestrate.webservice.orchestration.rpa import repository as rpa_repository  # noqa: E402
    from ccai.pychestrate.webservice.orchestration.rpa.models import RpaExecutionMode  # noqa: E402
    from ccai.pychestrate.webservice.pods.models import PodDefinition  # noqa: E402
    from ccai.pychestrate.webservice.webinterface.blueprints.projects import routes_rpa  # noqa: E402

    setup = _setup(build_status="succeeded", commit_sha="abc1234")
    admin = ensure_seeded_admin()
    pod_id = uuid.uuid4()
    client_id = uuid.uuid4()
    type_id = "e2e-prj33-" + uuid.uuid4().hex[:6]
    db_session = open_db_session()
    try:
        db_session.add(PodDefinition(pod_id=pod_id, project_id=uuid.uuid4(), pod_name="lab-bench-7"))
        db_session.add(Client(client_id=client_id, project_id=uuid.uuid4(), pod_name="lab-bench-7"))
        rpa_repository.insert_job_type(
            db_session=db_session, type_id=type_id, display_name="E2E", description="",
            execution_mode=RpaExecutionMode.PROCESS, capability_requirements=[], packet_schema=None,
            secret_fields=[], created_by_id=None,
        )
        job = rpa_repository.insert_job(
            db_session=db_session, job_id=new_uuid(), project_id=routes_rpa._rpa_project_key(db_session=db_session, project_id=setup["project_id"]), spec_id=None,
            spec_name="ad hoc", spec_revision=1, type_id=type_id, resolved_version="1.0.0",
            execution_mode=RpaExecutionMode.PROCESS, work_packet={}, packet_digest="",
            triggered_by_id=admin.user_id, trigger_cause={}, idempotency_key="",
        )
        job.pod_id = pod_id
        job.client_id = client_id
        db_session.commit()
        job_id = str(job.job_id)
    finally:
        db_session.close()

    page = _page(setup, "/projects/{}/rpa/jobs/{}".format(setup["project_id"], job_id))
    details = page.split("Job Details", 1)[-1]

    testbase.assert_equal(
        ("lab-bench-7" in details, "client of lab-bench-7" in details, str(pod_id) + " /" in details),
        (True, True, False),
    )
    return
