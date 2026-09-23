"""
.. module:: test_project_manager_delete_project
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for ProjectManager.delete_project

.. moduleauthor:: Code Craft AI LLC

Deleting a project must take everything that belongs to it along, in
one transaction, on databases that enforce foreign keys (PRJ-03), and a
deleted project's id must never be handed to a new project (rows that
refer to projects by id without a foreign key, such as RPA
specifications, would otherwise be inherited -- PRJ-19).

**Feature: projects (PRJ-03 / PRJ-19 project deletion)**
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import uuid

from datetime import datetime, timezone
from typing import Any, Dict, List

import sqlalchemy as sa

from sqlalchemy.orm import sessionmaker

from ccai import testbase

from ccai.pychestrate.core.managers.project_manager import (
    ProjectHasActiveJobsError,
    ProjectManager,
)
from ccai.pychestrate.core.orm import (
    Project,
    ProjectBuild,
    ProjectBuildArtifact,
    ProjectBuildSpec,
    ProjectCalendarEvent,
    ProjectChannelHistory,
    ProjectInfraJob,
    ProjectInfraSpec,
    ProjectMember,
    ProjectMergeEvent,
    ProjectPhaseEvent,
    ProjectPipelineRun,
    ProjectPullEvent,
    ProjectRelease,
    ProjectReleaseArtifact,
    ProjectReleaseBranch,
    ProjectReleaseChannel,
    ProjectReleaseEvent,
    ProjectReleasePipeline,
    ProjectReleaseSchedule,
    ProjectReleaseTemplate,
    ProjectRepository,
    ProjectRepositoryRef,
    ProjectStageRun,
    ProjectTestJob,
    ProjectTestResult,
    ProjectTestSpec,
    ProjectVariable,
    ProjectWatch,
    ProjectWatchTriggerLog,
    PychestrateModelBase,
    User,
)


def _session_with_projects(*names: str) -> Any:
    """
        A session on a fresh in-memory database (plain ``create_all``,
        exactly as a development instance builds its schema) holding one
        project per name.

        :returns: Tuple of (session, {name: project_id}).
    """
    engine = sa.create_engine("sqlite://")
    PychestrateModelBase.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    owner = uuid.uuid4()
    ids: Dict[str, int] = {}
    for name in names:
        project = Project(name=name, owner_id=owner, metadata_json={})
        session.add(project)
        session.flush()
        ids[name] = project.id
    session.commit()
    rtnval = (session, ids)
    return rtnval


def test_delete_project_runs_related_rows_cleanup_before_the_project_row_goes():
    """
    **Feature: projects (PRJ-19 project deletion)**
    **Property: delete_project calls related_rows_cleanup with its own
    session and the project id while the project row still exists, so
    rows other services keep for the project are removed in the same
    transaction as the project.**
    """
    session, ids = _session_with_projects("alpha")
    seen: List[Any] = []

    def _cleanup(db_session: Any, project_id: int) -> None:
        still_there = db_session.query(Project).filter(Project.id == project_id).count()
        seen.append((db_session is session, project_id, still_there))
        return

    ProjectManager(session).delete_project(
        ids["alpha"], "u-1", related_rows_cleanup=_cleanup
    )

    testbase.assert_equal(seen, [(True, ids["alpha"], 1)])
    return


def test_delete_project_keeps_the_project_when_related_rows_cleanup_refuses():
    """
    **Feature: projects (PRJ-19 project deletion)**
    **Property: when related_rows_cleanup raises (for example because
    RPA jobs are still running) the deletion is rolled back and the
    project still exists.**
    """
    session, ids = _session_with_projects("alpha")

    def _refuse(db_session: Any, project_id: int) -> None:
        raise ProjectHasActiveJobsError("1 RPA job is still running")

    try:
        ProjectManager(session).delete_project(
            ids["alpha"], "u-1", related_rows_cleanup=_refuse
        )
    except ProjectHasActiveJobsError:
        pass

    remaining = session.query(Project).filter(Project.id == ids["alpha"]).count()
    testbase.assert_equal(remaining, 1)
    return


def _fk_enforcing_session() -> Any:
    """
        A session on an in-memory SQLite database that enforces foreign
        keys (``PRAGMA foreign_keys=ON``), as PostgreSQL does, with one
        legacy user row to own projects.

        :returns: Tuple of (session, owner_id).
    """
    engine = sa.create_engine("sqlite://")

    @sa.event.listens_for(engine, "connect")
    def _enforce_foreign_keys(dbapi_connection: Any, _record: Any) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")
        return

    PychestrateModelBase.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    owner = User(
        id=uuid.uuid4(), first_name="Owner", last_name="One", display_name="Owner One",
        email="owner@example.invalid", login="owner-one", status="active", authtype="internal",
    )
    session.add(owner)
    session.commit()
    rtnval = (session, owner.id)
    return rtnval


def _populate_project(*, session: Any, owner_id: Any, name: str) -> int:
    """
        Create a project with a row in every table a project owns --
        including a finished build with an artifact, a test job pointing
        at that build, and a release that a pipeline run and a channel
        point back to -- and return its id.
    """
    now = datetime.now(timezone.utc)
    project = Project(name=name, owner_id=owner_id, metadata_json={})
    session.add(project)
    session.flush()
    pid = project.id

    def add(row: Any) -> Any:
        session.add(row)
        session.flush()
        return row

    add(ProjectMember(project_id=pid, user_id=owner_id, role="owner"))
    add(ProjectVariable(project_id=pid, name="REGION", value_json='"eu"', var_type="string"))
    repo = add(ProjectRepository(project_id=pid, name="repo", url="https://example.com/r.git", auth_type="none"))
    add(ProjectRepositoryRef(repository_id=repo.id, kind="branch", name="main", commit_sha="abc1234"))
    spec = add(ProjectBuildSpec(project_id=pid, repository_id=repo.id, name="nightly"))
    build = add(ProjectBuild(
        project_id=pid, spec_id=spec.id, spec_version=1, branch="main", commit_sha="abc1234",
        status="succeeded", trigger_type="manual", triggered_by_id=owner_id,
    ))
    add(ProjectBuildArtifact(build_id=build.id, name="app.tgz", path="/tmp/app.tgz", size_bytes=1, checksum="00"))
    infra_spec = add(ProjectInfraSpec(project_id=pid, name="stage", provider="docker"))
    infra_job = add(ProjectInfraJob(
        project_id=pid, spec_id=infra_spec.id, spec_version=1, action="provision",
        status="succeeded", triggered_by_id=owner_id,
    ))
    test_spec = add(ProjectTestSpec(
        project_id=pid, name="smoke", framework="pytest", test_command="pytest",
        build_ref=spec.id, infra_ref=infra_spec.id,
    ))
    test_job = add(ProjectTestJob(
        project_id=pid, spec_id=test_spec.id, spec_version=1, build_id=build.id,
        infra_job_id=infra_job.id, status="failed", triggered_by_id=owner_id,
    ))
    add(ProjectTestResult(job_id=test_job.id, name="test_ok", status="passed"))
    pipeline = add(ProjectReleasePipeline(project_id=pid, name="ship"))
    run = add(ProjectPipelineRun(
        pipeline_id=pipeline.id, pipeline_version=1, trigger_type="manual", triggered_by_id=owner_id,
    ))
    add(ProjectStageRun(pipeline_run_id=run.id, stage_name="build", stage_type="build"))
    schedule = add(ProjectReleaseSchedule(
        project_id=pid, name="weekly", cron_expression="0 0 * * 0", pipeline_id=pipeline.id,
    ))
    release = add(ProjectRelease(
        project_id=pid, version="1.0.0", name="first", pipeline_run_id=run.id, schedule_id=schedule.id,
    ))
    run.release_id = release.id
    add(ProjectReleaseArtifact(
        release_id=release.id, name="app", artifact_type="archive", size_bytes=1, checksum="00",
        storage_path="/tmp/app",
    ))
    channel = add(ProjectReleaseChannel(project_id=pid, name="stable", current_release_id=release.id))
    add(ProjectChannelHistory(channel_id=channel.id, release_id=release.id, published_by_id=owner_id))
    add(ProjectReleaseTemplate(project_id=pid, name="std"))
    add(ProjectCalendarEvent(project_id=pid, event_type="release", name="launch", start_time=now, end_time=now))
    release_event = add(ProjectReleaseEvent(
        project_id=pid, release_id=release.id, name="window", start_time=now, end_time=now,
    ))
    add(ProjectPhaseEvent(release_event_id=release_event.id, name="freeze", start_time=now, end_time=now, order=1))
    add(ProjectReleaseBranch(release_id=release.id, repository_id=repo.id, branch_name="release/1.0"))
    add(ProjectMergeEvent(
        project_id=pid, release_id=release.id, repository_id=repo.id, source_branch="a",
        target_branch="b", name="merge", scheduled_time=now,
    ))
    add(ProjectPullEvent(
        project_id=pid, release_id=release.id, repository_id=repo.id, source_branch="a",
        target_branch="b", name="pull", scheduled_time=now,
    ))
    watch = add(ProjectWatch(
        project_id=pid, name="on-push", trigger_source="repository_commit", source_id=repo.id,
        repository_id=repo.id, conditions_json={}, actions_json=[],
    ))
    add(ProjectWatchTriggerLog(watch_id=watch.id, trigger_event_json={}, success=True))
    session.commit()
    return pid


_OWNED_MODELS = (
    "ProjectMember", "ProjectVariable", "ProjectRepository", "ProjectBuildSpec", "ProjectBuild",
    "ProjectBuildArtifact", "ProjectInfraSpec", "ProjectInfraJob", "ProjectTestSpec", "ProjectTestJob",
    "ProjectTestResult", "ProjectReleasePipeline", "ProjectPipelineRun", "ProjectStageRun",
    "ProjectRelease", "ProjectReleaseArtifact", "ProjectReleaseChannel", "ProjectChannelHistory",
    "ProjectReleaseSchedule", "ProjectReleaseTemplate", "ProjectCalendarEvent", "ProjectReleaseEvent",
    "ProjectPhaseEvent", "ProjectReleaseBranch", "ProjectMergeEvent", "ProjectPullEvent",
    "ProjectWatch", "ProjectWatchTriggerLog", "ProjectRepositoryRef",
)


def _row_counts(session: Any) -> Dict[str, int]:
    from ccai.pychestrate.core import orm as core_orm  # noqa: E402

    rtnval = {"Project": session.query(Project).count()}
    for model_name in _OWNED_MODELS:
        rtnval[model_name] = session.query(getattr(core_orm, model_name)).count()
    return rtnval


def test_delete_project_removes_a_project_that_has_run_builds():
    """
    **Feature: projects (PRJ-03 project deletion)**
    **Property: a project whose build specification has builds (with
    artifacts, and a test job pointing at the build) is deleted on a
    database that enforces foreign keys -- it used to fail with an
    IntegrityError on ``UPDATE project_builds SET pbspec_id``.**
    """
    session, owner_id = _fk_enforcing_session()
    project_id = _populate_project(session=session, owner_id=owner_id, name="alpha")

    ProjectManager(session).delete_project(project_id, str(owner_id))

    remaining = session.query(Project).filter(Project.id == project_id).count()
    testbase.assert_equal(remaining, 0)
    return


def test_delete_project_leaves_no_row_the_project_owned():
    """
    **Feature: projects (PRJ-03 project deletion)**
    **Property: after delete_project, none of the rows the project owned
    remain in any project table (builds, jobs, releases, pipeline runs,
    calendar events, watches, ...).**
    """
    session, owner_id = _fk_enforcing_session()
    project_id = _populate_project(session=session, owner_id=owner_id, name="alpha")

    ProjectManager(session).delete_project(project_id, str(owner_id))

    leftovers = {name: count for name, count in _row_counts(session).items() if count != 0}
    testbase.assert_equal(leftovers, {})
    return


def test_delete_project_leaves_other_projects_untouched():
    """
    **Feature: projects (PRJ-03 project deletion)**
    **Property: deleting one project removes none of another project's
    rows.**
    """
    session, owner_id = _fk_enforcing_session()
    doomed = _populate_project(session=session, owner_id=owner_id, name="alpha")
    _populate_project(session=session, owner_id=owner_id, name="beta")
    before = _row_counts(session)

    ProjectManager(session).delete_project(doomed, str(owner_id))

    after = _row_counts(session)
    halved = {name: count // 2 for name, count in before.items()}
    testbase.assert_equal(after, halved)
    return


def test_a_new_project_never_reuses_a_deleted_projects_id():
    """
    **Feature: projects (PRJ-19 project deletion)**
    **Property: after the project with the highest id is deleted, the
    next project gets a new id. On SQLite the projects table is
    AUTOINCREMENT; without it the rowid of the deleted project was
    reused and the new project inherited the old one's RPA rows.**
    """
    session, ids = _session_with_projects("alpha", "beta")
    ProjectManager(session).delete_project(ids["beta"], "u-1")

    replacement = Project(name="gamma", owner_id=uuid.uuid4(), metadata_json={})
    session.add(replacement)
    session.commit()

    testbase.assert_true(replacement.id > ids["beta"])
    return
