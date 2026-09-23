"""
.. module:: test_project_manager_delete_project
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for ProjectManager.delete_project

.. moduleauthor:: Code Craft AI LLC

Deleting a project must take everything that belongs to it along, in
one transaction, and a deleted project's id must never be handed to a
new project (rows that refer to projects by id without a foreign key,
such as RPA specifications, would otherwise be inherited).

**Feature: projects (PRJ-19 project deletion)**
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import uuid

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
    PychestrateModelBase,
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
