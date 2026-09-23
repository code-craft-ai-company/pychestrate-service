"""
.. module:: test_p26b_projects_delete_e2e_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: End-to-end tests for deleting a project through the
               consumer UI.

.. moduleauthor:: Code Craft AI LLC

Drives ``POST /projects/{id}/delete`` on the real app and checks what is
left in the database afterwards.

* PRJ-19 -- a project's RPA specifications, revisions and jobs are
  removed with it, and a project with RPA jobs still running is not
  deleted.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Dict

from ccai import testbase

from ccai.pychestrate.core.defaults import new_uuid
from ccai.tests.singlehost.pychestrate.webservice.phase10._e2e_harness import (
    ensure_app,
    logged_in_cookies,
)
from ccai.tests.singlehost.pychestrate.webservice.phase10._projects_ui_helpers import (
    create_project_via_ui,
    open_db_session,
    post_form,
)


_RPA_JOB_TYPE_ID = "e2e-prj19-sync"


def _seed_rpa_spec_and_job(*, project_id: int, job_status: str) -> Dict[str, str]:
    """
        Give the project one RPA specification (with a revision) and one
        job in ``job_status``, the way the RPA pages store them: keyed by
        the project id as a string.
    """
    from ccai.pychestrate.webservice.orchestration.rpa import (  # noqa: E402
        repository as rpa_repository,
    )
    from ccai.pychestrate.webservice.orchestration.rpa.models import (  # noqa: E402
        RpaExecutionMode,
        RpaJobStatus,
    )

    db_session = open_db_session()
    try:
        if rpa_repository.find_job_type(db_session=db_session, type_id=_RPA_JOB_TYPE_ID) is None:
            rpa_repository.insert_job_type(
                db_session=db_session,
                type_id=_RPA_JOB_TYPE_ID,
                display_name="E2E sync",
                description="",
                execution_mode=RpaExecutionMode.PROCESS,
                capability_requirements=[],
                packet_schema=None,
                secret_fields=[],
                created_by_id=None,
            )
        spec = rpa_repository.insert_spec(
            db_session=db_session,
            project_id=str(project_id),
            name="nightly-sync",
            type_id=_RPA_JOB_TYPE_ID,
            version_selector="latest-active",
            default_packet={},
            target_pod_id=None,
            required_capabilities=[],
            timeout_minutes=None,
            description="",
            created_by_id=None,
        )
        rpa_repository.insert_spec_revision(
            db_session=db_session, spec_id=str(spec.spec_id), revision=1, snapshot={},
        )
        job = rpa_repository.insert_job(
            db_session=db_session,
            job_id=new_uuid(),
            project_id=str(project_id),
            spec_id=str(spec.spec_id),
            spec_name=spec.name,
            spec_revision=1,
            type_id=_RPA_JOB_TYPE_ID,
            resolved_version="1.0.0",
            execution_mode=RpaExecutionMode.PROCESS,
            work_packet={},
            packet_digest="",
            triggered_by_id=None,
            trigger_cause={},
            idempotency_key="",
        )
        job.status = RpaJobStatus(job_status)
        db_session.commit()
        rtnval = {"spec_id": str(spec.spec_id), "job_id": str(job.job_id)}
    finally:
        db_session.close()
    return rtnval


def _rpa_row_counts(*, project_id: int, spec_id: str) -> Dict[str, int]:
    from ccai.pychestrate.webservice.orchestration.rpa.models import (  # noqa: E402
        RpaJob,
        RpaSpec,
        RpaSpecRevision,
    )

    db_session = open_db_session()
    try:
        rtnval = {
            "specs": db_session.query(RpaSpec).filter(RpaSpec.project_id == str(project_id)).count(),
            "jobs": db_session.query(RpaJob).filter(RpaJob.project_id == str(project_id)).count(),
            "revisions": db_session.query(RpaSpecRevision).filter(RpaSpecRevision.spec_id == spec_id).count(),
        }
    finally:
        db_session.close()
    return rtnval


def _project_exists(*, project_id: int) -> bool:
    from ccai.pychestrate.core.orm import Project  # noqa: E402

    db_session = open_db_session()
    try:
        rtnval = db_session.query(Project).filter(Project.id == project_id).count() == 1
    finally:
        db_session.close()
    return rtnval


def _delete_project(*, wsgi_app: Any, cookies: Dict[str, str], project_id: int) -> Any:
    rtnval = post_form(
        wsgi_app=wsgi_app,
        path="/projects/{}/delete".format(project_id),
        cookies=cookies,
        fields={},
    )
    return rtnval


def test_deleting_a_project_removes_its_rpa_specs_revisions_and_jobs():
    """
    **Feature: projects deletion (PRJ-19)**
    **Property: after POST /projects/{id}/delete no RPA specification,
    revision or job of that project is left, so a later project that
    gets the same id cannot inherit them.**
    """
    handle = ensure_app()
    cookies = logged_in_cookies(wsgi_app=handle.wsgi_app)
    project_id = create_project_via_ui(
        wsgi_app=handle.wsgi_app, cookies=cookies, prefix="prj19-rpa"
    )
    seeded = _seed_rpa_spec_and_job(project_id=project_id, job_status="succeeded")

    _delete_project(wsgi_app=handle.wsgi_app, cookies=cookies, project_id=project_id)

    testbase.assert_equal(
        _rpa_row_counts(project_id=project_id, spec_id=seeded["spec_id"]),
        {"specs": 0, "jobs": 0, "revisions": 0},
    )
    return


def test_a_project_with_a_running_rpa_job_is_not_deleted():
    """
    **Feature: projects deletion (PRJ-19)**
    **Property: while one of the project's RPA jobs is running, POST
    /projects/{id}/delete leaves the project (and its RPA rows) in
    place.**
    """
    handle = ensure_app()
    cookies = logged_in_cookies(wsgi_app=handle.wsgi_app)
    project_id = create_project_via_ui(
        wsgi_app=handle.wsgi_app, cookies=cookies, prefix="prj19-busy"
    )
    _seed_rpa_spec_and_job(project_id=project_id, job_status="running")

    _delete_project(wsgi_app=handle.wsgi_app, cookies=cookies, project_id=project_id)

    testbase.assert_equal(_project_exists(project_id=project_id), True)
    return
