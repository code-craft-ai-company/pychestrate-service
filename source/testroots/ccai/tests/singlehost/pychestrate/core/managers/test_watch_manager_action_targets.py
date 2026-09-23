"""
.. module:: test_watch_manager_action_targets
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests that watch actions may only target the watch's own project

.. moduleauthor:: Code Craft AI LLC

A watch in one project must never start work in another. The watch's
source was already checked against its project; its actions (build,
infrastructure and test specifications, release pipelines) now are too,
both when a watch is created and when its actions are replaced.

**Feature: projects (PRJ-04 cross-project guard)**
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import uuid

from typing import Any, Dict, Tuple

import sqlalchemy as sa

from sqlalchemy.orm import sessionmaker

from ccai import testbase

from ccai.pychestrate.core.managers.watch_manager import (
    WatchAction,
    WatchActionConfig,
    WatchCondition,
    WatchCreateRequest,
    WatchManager,
    WatchUpdateRequest,
    WatchValidationError,
)
from ccai.pychestrate.core.orm import (
    Project,
    ProjectBuildSpec,
    ProjectRepository,
    PychestrateModelBase,
)


def _two_projects() -> Tuple[Any, Dict[str, int]]:
    """
        An in-memory database holding projects "alpha" and "beta", each
        with one repository and one build specification.
    """
    engine = sa.create_engine("sqlite://")
    PychestrateModelBase.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    owner = uuid.uuid4()
    ids: Dict[str, int] = {}
    for key in ("alpha", "beta"):
        project = Project(name=key, owner_id=owner, metadata_json={})
        session.add(project)
        session.flush()
        repository = ProjectRepository(
            project_id=project.id, name="repo-" + key,
            url="https://example.com/{}.git".format(key),
            auth_type="none", default_branch="main",
        )
        session.add(repository)
        session.flush()
        spec = ProjectBuildSpec(
            project_id=project.id, repository_id=repository.id, name="build-" + key,
            branch="main", steps_json=[], environment_json={}, timeout_minutes=60, version=1,
        )
        session.add(spec)
        session.flush()
        ids[key] = project.id
        ids[key + "_repo"] = repository.id
        ids[key + "_spec"] = spec.id
    session.commit()
    rtnval = (session, ids)
    return rtnval


def _create_request(*, source_id: int, target_id: int) -> WatchCreateRequest:
    rtnval = WatchCreateRequest(
        name="nightly",
        trigger_source="repository_commit",
        source_id=source_id,
        conditions=WatchCondition(branch_pattern="main"),
        actions=[WatchActionConfig(action=WatchAction.TRIGGER_BUILD, target_id=target_id)],
    )
    return rtnval


def test_create_watch_refuses_a_build_spec_from_another_project():
    """
    **Feature: projects (PRJ-04 cross-project guard)**
    **Property: creating a watch in project alpha whose trigger_build
    action names project beta's build specification is refused with
    TARGET_NOT_IN_PROJECT.**
    """
    session, ids = _two_projects()
    manager = WatchManager(session)
    error_code = None
    try:
        manager.create_watch(
            ids["alpha"], _create_request(source_id=ids["alpha_repo"], target_id=ids["beta_spec"]), "u-1",
        )
    except WatchValidationError as refusal:
        error_code = refusal.error_code
    testbase.assert_equal(error_code, "TARGET_NOT_IN_PROJECT")
    return


def test_create_watch_accepts_a_build_spec_from_its_own_project():
    """
    **Feature: projects (PRJ-04 cross-project guard)**
    **Property: a watch whose action names a build specification in its
    own project is created.**
    """
    session, ids = _two_projects()
    manager = WatchManager(session)
    watch = manager.create_watch(
        ids["alpha"], _create_request(source_id=ids["alpha_repo"], target_id=ids["alpha_spec"]), "u-1",
    )
    testbase.assert_equal(watch.project_id, ids["alpha"])
    return


def test_update_watch_refuses_actions_that_target_another_project():
    """
    **Feature: projects (PRJ-04 cross-project guard)**
    **Property: replacing a watch's actions with one that names another
    project's build specification is refused.**
    """
    session, ids = _two_projects()
    manager = WatchManager(session)
    watch = manager.create_watch(
        ids["alpha"], _create_request(source_id=ids["alpha_repo"], target_id=ids["alpha_spec"]), "u-1",
    )
    error_code = None
    try:
        manager.update_watch(
            watch.id,
            WatchUpdateRequest(actions=[
                WatchActionConfig(action=WatchAction.TRIGGER_BUILD, target_id=ids["beta_spec"]),
            ]),
            "u-1",
        )
    except WatchValidationError as refusal:
        error_code = refusal.error_code
    testbase.assert_equal(error_code, "TARGET_NOT_IN_PROJECT")
    return
