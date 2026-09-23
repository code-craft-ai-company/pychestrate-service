"""
.. module:: test_build_manager_spec_delete
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests that build specifications can be deleted with their
               history, and that repositories can be removed.

.. moduleauthor:: Code Craft AI LLC

``BuildManager.delete_spec`` deleted the specification row and relied on
a cascade that does not exist, so on a database that enforces foreign
keys a specification that had ever run a build could not be deleted.
``RepositoryManager.remove_repository`` "disabled" watches through an
attribute the model does not have and left them pointing at the
repository. These tests run on an in-memory SQLite database with foreign
keys enforced.

**Feature: projects (PRJ-18 build specification edit and delete)**
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import uuid

from typing import Any, Dict

import sqlalchemy as sa

from sqlalchemy.orm import sessionmaker

from ccai import testbase

from ccai.pychestrate.core.managers.build_manager import (
    BuildManager,
    BuildSpecHasActiveBuildsError,
    BuildSpecInUseError,
    BuildSpecUpdateRequest,
)
from ccai.pychestrate.core.managers.repository_manager import RepositoryManager
from ccai.pychestrate.core.orm import (
    Project,
    ProjectBuild,
    ProjectBuildArtifact,
    ProjectBuildSpec,
    ProjectRepository,
    ProjectTestJob,
    ProjectTestSpec,
    ProjectWatch,
    PychestrateModelBase,
    User,
)


def _scenario(*, build_status: str = "succeeded") -> Dict[str, Any]:
    """
        A project with a repository, a build specification that ran one
        build (with an artifact), a test specification naming the build
        specification and a test job that ran against the build.
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
    session.flush()

    def add(row: Any) -> Any:
        session.add(row)
        session.flush()
        return row

    project = add(Project(name="alpha", owner_id=owner.id, metadata_json={}))
    repository = add(ProjectRepository(
        project_id=project.id, name="repo", url="https://example.invalid/r.git", auth_type="none",
    ))
    spec = add(ProjectBuildSpec(project_id=project.id, repository_id=repository.id, name="nightly"))
    build = add(ProjectBuild(
        project_id=project.id, spec_id=spec.id, spec_version=1, branch="main", commit_sha="abc1234",
        status=build_status, trigger_type="manual", triggered_by_id=owner.id,
    ))
    add(ProjectBuildArtifact(build_id=build.id, name="app.tgz", path="/nonexistent/app.tgz", size_bytes=1, checksum="00"))
    test_spec = add(ProjectTestSpec(
        project_id=project.id, name="smoke", framework="pytest", test_command="pytest", build_ref=spec.id,
    ))
    test_job = add(ProjectTestJob(
        project_id=project.id, spec_id=test_spec.id, spec_version=1, build_id=build.id,
        status="succeeded", triggered_by_id=owner.id,
    ))
    session.commit()
    rtnval = {
        "session": session, "owner": str(owner.id), "project": project.id, "repository": repository.id,
        "spec": spec.id, "build": build.id, "test_spec": test_spec.id, "test_job": test_job.id,
    }
    return rtnval


def _add_watch(scenario: Dict[str, Any], *, name: str, trigger: str, source_id: int, target_id: int) -> None:
    session = scenario["session"]
    session.add(ProjectWatch(
        project_id=scenario["project"], name=name, trigger_source=trigger, source_id=source_id,
        repository_id=scenario["repository"] if trigger != "build_completion" else None,
        conditions_json={}, actions_json=[{"action": "trigger_build", "target_id": target_id, "parameters": {}}],
        enabled=True, trigger_count=0,
    ))
    session.commit()
    return


def test_a_specification_with_builds_is_deleted_with_them():
    """
    **Feature: projects (PRJ-18 build specification delete)**
    **Property: deleting a specification that ran a build removes the
    specification, the build and its artifact on a database that
    enforces foreign keys, and reports how many builds went.**
    """
    scenario = _scenario()
    session = scenario["session"]

    deleted = BuildManager(session).delete_spec(scenario["spec"], scenario["owner"])

    left = (
        session.query(ProjectBuildSpec).count(),
        session.query(ProjectBuild).count(),
        session.query(ProjectBuildArtifact).count(),
    )
    testbase.assert_equal((deleted, left), ({"builds": 1}, (0, 0, 0)))
    return


def test_test_history_survives_a_deleted_specification():
    """
    **Feature: projects (PRJ-18 build specification delete)**
    **Property: the test job that ran against a deleted build and the
    test specification that named the build specification remain, with
    the links cleared.**
    """
    scenario = _scenario()
    session = scenario["session"]

    BuildManager(session).delete_spec(scenario["spec"], scenario["owner"])

    job = session.query(ProjectTestJob).filter(ProjectTestJob.id == scenario["test_job"]).one()
    spec = session.query(ProjectTestSpec).filter(ProjectTestSpec.id == scenario["test_spec"]).one()
    testbase.assert_equal((job.build_id, spec.build_ref), (None, None))
    return


def test_a_specification_with_a_running_build_is_not_deleted():
    """
    **Feature: projects (PRJ-18 build specification delete)**
    **Property: a specification whose build is still running is refused
    and kept.**
    """
    scenario = _scenario(build_status="running")
    session = scenario["session"]

    refused = False
    try:
        BuildManager(session).delete_spec(scenario["spec"], scenario["owner"])
    except BuildSpecHasActiveBuildsError:
        refused = True

    testbase.assert_equal((refused, session.query(ProjectBuildSpec).count()), (True, 1))
    return


def test_a_specification_that_watches_use_is_not_deleted_and_they_are_named():
    """
    **Feature: projects (PRJ-18 build specification delete)**
    **Property: a specification that a watch runs is refused with a
    message naming the watch, and kept.**
    """
    scenario = _scenario()
    session = scenario["session"]
    _add_watch(scenario, name="build-on-push", trigger="repository_commit",
               source_id=scenario["repository"], target_id=scenario["spec"])

    message = None
    try:
        BuildManager(session).delete_spec(scenario["spec"], scenario["owner"])
    except BuildSpecInUseError as refusal:
        message = refusal.message

    testbase.assert_equal(
        ("build-on-push" in (message or ""), session.query(ProjectBuildSpec).count()), (True, 1)
    )
    return


def test_spec_usage_counts_builds_and_names_watches():
    """
    **Feature: projects (PRJ-18 build specification delete)**
    **Property: spec_usage reports the builds that would be deleted and
    the watches (started by the specification or running it) that block
    deletion.**
    """
    scenario = _scenario()
    _add_watch(scenario, name="after-nightly", trigger="build_completion",
               source_id=scenario["spec"], target_id=999)

    usage = BuildManager(scenario["session"]).spec_usage(scenario["spec"])

    testbase.assert_equal(usage, {"builds": 1, "active_builds": 0, "watches": ["after-nightly"]})
    return


def test_editing_a_specification_saves_a_new_version():
    """
    **Feature: projects (PRJ-18 build specification edit)**
    **Property: update_spec saves the changes as the next version.**
    """
    scenario = _scenario()
    session = scenario["session"]

    updated = BuildManager(session).update_spec(
        scenario["spec"], BuildSpecUpdateRequest(branch="release", timeout_minutes=90), scenario["owner"],
    )

    testbase.assert_equal((updated.version, updated.branch, updated.timeout_minutes), (2, "release", 90))
    return


def test_removing_a_repository_disables_and_detaches_its_watches():
    """
    **Feature: projects (PRJ-18 repository removal)**
    **Property: removing a repository disables its watches and detaches
    them (the watch rows used to keep the foreign key, so the removal
    failed, and the "disable" set an attribute the model does not
    have).**
    """
    scenario = _scenario()
    session = scenario["session"]
    BuildManager(session).delete_spec(scenario["spec"], scenario["owner"])
    _add_watch(scenario, name="on-push", trigger="repository_commit",
               source_id=scenario["repository"], target_id=1)

    RepositoryManager(session).remove_repository(scenario["repository"], scenario["owner"])

    watch = session.query(ProjectWatch).one()
    testbase.assert_equal(
        (session.query(ProjectRepository).count(), watch.enabled, watch.repository_id), (0, False, None)
    )
    return
