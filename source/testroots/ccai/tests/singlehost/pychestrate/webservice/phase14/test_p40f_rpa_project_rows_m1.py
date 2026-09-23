"""
.. module:: test_p40f_rpa_project_rows_m1
    :synopsis: Tests for removing a project's RPA rows when the project
               is deleted (PRJ-19).

RPA specifications and jobs refer to a project by id without a foreign
key. Deleting a project used to leave them behind, and on SQLite the
next project reused the id and showed the old project's specification.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Dict

from ccai import testbase

from ccai.pychestrate.core.defaults import new_uuid
from ccai.pychestrate.webservice.orchestration.rpa import models as _rpa_models  # noqa: F401
from ccai.pychestrate.webservice.orchestration.rpa import repository as rpa_repository
from ccai.pychestrate.webservice.orchestration.rpa.models import (
    RpaExecutionMode,
    RpaJob,
    RpaJobStatus,
    RpaSpec,
    RpaSpecRevision,
)

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
)


def _seed_project_rows(*, db_session: Any, project_id: str, job_status: RpaJobStatus) -> Dict[str, str]:
    """
        One specification (with a revision) and one job in the given
        status for ``project_id``.
    """
    if rpa_repository.find_job_type(db_session=db_session, type_id="sync-crm") is None:
        rpa_repository.insert_job_type(
            db_session=db_session,
            type_id="sync-crm",
            display_name="Sync CRM",
            description="",
            execution_mode=RpaExecutionMode.PROCESS,
            capability_requirements=[],
            packet_schema=None,
            secret_fields=[],
            created_by_id=None,
        )
    spec = rpa_repository.insert_spec(
        db_session=db_session,
        project_id=project_id,
        name="nightly-{}-{}".format(project_id, new_uuid()[:8]),
        type_id="sync-crm",
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
        project_id=project_id,
        spec_id=str(spec.spec_id),
        spec_name=spec.name,
        spec_revision=1,
        type_id="sync-crm",
        resolved_version="1.0.0",
        execution_mode=RpaExecutionMode.PROCESS,
        work_packet={},
        packet_digest="",
        triggered_by_id=None,
        trigger_cause={},
        idempotency_key="",
    )
    job.status = job_status
    db_session.commit()
    rtnval = {"spec_id": str(spec.spec_id), "job_id": str(job.job_id)}
    return rtnval


def _row_counts(*, db_session: Any, project_id: str, spec_id: str) -> Dict[str, int]:
    rtnval = {
        "specs": db_session.query(RpaSpec).filter(RpaSpec.project_id == project_id).count(),
        "jobs": db_session.query(RpaJob).filter(RpaJob.project_id == project_id).count(),
        "revisions": db_session.query(RpaSpecRevision).filter(RpaSpecRevision.spec_id == spec_id).count(),
    }
    return rtnval


def test_delete_project_rows_removes_the_projects_specs_revisions_and_jobs():
    """
    **Feature: RPA project deletion (PRJ-19)**
    **Property: delete_project_rows removes every specification,
    specification revision and job of the project.**
    """
    _engine, db_session = build_in_memory_session()
    seeded = _seed_project_rows(db_session=db_session, project_id="3", job_status=RpaJobStatus.SUCCEEDED)

    rpa_repository.delete_project_rows(db_session=db_session, project_id="3")
    db_session.commit()

    testbase.assert_equal(
        _row_counts(db_session=db_session, project_id="3", spec_id=seeded["spec_id"]),
        {"specs": 0, "jobs": 0, "revisions": 0},
    )
    return


def test_delete_project_rows_leaves_other_projects_alone():
    """
    **Feature: RPA project deletion (PRJ-19)**
    **Property: delete_project_rows for project 3 leaves project 4's
    specification, revision and job in place.**
    """
    _engine, db_session = build_in_memory_session()
    _seed_project_rows(db_session=db_session, project_id="3", job_status=RpaJobStatus.SUCCEEDED)
    other = _seed_project_rows(db_session=db_session, project_id="4", job_status=RpaJobStatus.SUCCEEDED)

    rpa_repository.delete_project_rows(db_session=db_session, project_id="3")
    db_session.commit()

    testbase.assert_equal(
        _row_counts(db_session=db_session, project_id="4", spec_id=other["spec_id"]),
        {"specs": 1, "jobs": 1, "revisions": 1},
    )
    return


def test_count_active_jobs_for_project_counts_only_unfinished_jobs():
    """
    **Feature: RPA project deletion (PRJ-19)**
    **Property: count_active_jobs_for_project counts the project's
    pending / dispatching / running jobs and ignores finished ones and
    other projects' jobs.**
    """
    _engine, db_session = build_in_memory_session()
    _seed_project_rows(db_session=db_session, project_id="3", job_status=RpaJobStatus.RUNNING)
    _seed_project_rows(db_session=db_session, project_id="3", job_status=RpaJobStatus.FAILED)
    _seed_project_rows(db_session=db_session, project_id="4", job_status=RpaJobStatus.PENDING)

    active = rpa_repository.count_active_jobs_for_project(db_session=db_session, project_id="3")

    testbase.assert_equal(active, 1)
    return
