"""
.. module:: test_project_manager_access
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for how ProjectManager combines project membership
               with global project roles

.. moduleauthor:: Code Craft AI LLC

Project access comes from membership (the Members page) and from global
roles that apply to every project (resolved by the web layer and handed
in as ``access_resolver``). The strongest role wins; without either the
user has no access.

**Feature: projects (PRJ-17 project access)**
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import uuid

from typing import Any, Dict, Optional

import sqlalchemy as sa

from sqlalchemy.orm import sessionmaker

from ccai import testbase

from ccai.pychestrate.core.managers.project_manager import (
    ProjectManager,
    ProjectRole,
)
from ccai.pychestrate.core.orm import (
    Project,
    ProjectMember,
    PychestrateModelBase,
)


MEMBER = str(uuid.UUID("11111111-1111-4111-8111-111111111111"))
OUTSIDER = str(uuid.UUID("22222222-2222-4222-8222-222222222222"))


def _session_with_projects() -> Any:
    """
        Projects "alpha" (MEMBER is a viewer) and "beta" (no members).

        :returns: Tuple of (session, {name: project_id}).
    """
    engine = sa.create_engine("sqlite://")
    PychestrateModelBase.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    ids: Dict[str, int] = {}
    for name in ("alpha", "beta"):
        project = Project(name=name, owner_id=uuid.uuid4(), metadata_json={})
        session.add(project)
        session.flush()
        ids[name] = project.id
    session.add(ProjectMember(project_id=ids["alpha"], user_id=uuid.UUID(MEMBER), role="viewer"))
    session.commit()
    rtnval = (session, ids)
    return rtnval


def _resolver(roles: Dict[str, ProjectRole]) -> Any:
    def _resolve(user_id: str) -> Optional[ProjectRole]:
        return roles.get(user_id, None)
    return _resolve


def test_a_global_role_gives_access_to_a_project_the_user_is_not_a_member_of():
    """
    **Feature: projects (PRJ-17 project access)**
    **Property: a user whose global role is developer may trigger work
    ("developer") in a project they are not a member of.**
    """
    session, ids = _session_with_projects()
    manager = ProjectManager(session, access_resolver=_resolver({OUTSIDER: ProjectRole.DEVELOPER}))

    testbase.assert_equal(manager.check_permission(ids["beta"], OUTSIDER, "developer"), True)
    return


def test_the_stronger_of_membership_and_global_role_applies():
    """
    **Feature: projects (PRJ-17 project access)**
    **Property: a viewer member whose global role is developer has the
    developer role on that project.**
    """
    session, ids = _session_with_projects()
    manager = ProjectManager(session, access_resolver=_resolver({MEMBER: ProjectRole.DEVELOPER}))

    testbase.assert_equal(manager.get_effective_role(ids["alpha"], MEMBER), ProjectRole.DEVELOPER)
    return


def test_a_global_role_does_not_lower_a_stronger_membership():
    """
    **Feature: projects (PRJ-17 project access)**
    **Property: an owner member whose global role is only viewer keeps
    the owner role on that project.**
    """
    session, ids = _session_with_projects()
    session.add(ProjectMember(project_id=ids["beta"], user_id=uuid.UUID(OUTSIDER), role="owner"))
    session.commit()
    manager = ProjectManager(session, access_resolver=_resolver({OUTSIDER: ProjectRole.VIEWER}))

    testbase.assert_equal(manager.check_permission(ids["beta"], OUTSIDER, "owner"), True)
    return


def test_without_membership_or_global_role_there_is_no_access():
    """
    **Feature: projects (PRJ-17 project access)**
    **Property: a user who is neither a member nor holds a global role
    cannot view the project.**
    """
    session, ids = _session_with_projects()
    manager = ProjectManager(session, access_resolver=_resolver({}))

    testbase.assert_equal(manager.check_permission(ids["alpha"], OUTSIDER, "view"), False)
    return


def test_a_failing_resolver_denies_rather_than_grants():
    """
    **Feature: projects (PRJ-17 project access)**
    **Property: if resolving global roles fails, the user gets no global
    access (checks fail closed).**
    """
    session, ids = _session_with_projects()

    def _broken(user_id: str) -> Optional[ProjectRole]:
        raise RuntimeError("rbac tables unavailable")

    manager = ProjectManager(session, access_resolver=_broken)

    testbase.assert_equal(manager.check_permission(ids["beta"], OUTSIDER, "view"), False)
    return


def test_list_projects_shows_every_project_to_a_global_role_holder():
    """
    **Feature: projects (PRJ-17 project access)**
    **Property: list_projects returns every project for a user with a
    global role, even with no memberships.**
    """
    session, ids = _session_with_projects()
    manager = ProjectManager(session, access_resolver=_resolver({OUTSIDER: ProjectRole.VIEWER}))

    names = [project.name for project in manager.list_projects(OUTSIDER).projects]

    testbase.assert_equal(names, ["alpha", "beta"])
    return


def test_list_projects_shows_only_member_projects_otherwise():
    """
    **Feature: projects (PRJ-17 project access)**
    **Property: without a global role, list_projects returns only the
    projects the user is a member of.**
    """
    session, ids = _session_with_projects()
    manager = ProjectManager(session, access_resolver=_resolver({}))

    names = [project.name for project in manager.list_projects(MEMBER).projects]

    testbase.assert_equal(names, ["alpha"])
    return


def test_has_any_project_access_for_a_member():
    """
    **Feature: projects (PRJ-17 project access)**
    **Property: a member of one project has project access (so the
    Projects area is shown to them).**
    """
    session, _ids = _session_with_projects()
    manager = ProjectManager(session, access_resolver=_resolver({}))

    testbase.assert_equal(manager.has_any_project_access(MEMBER), True)
    return


def test_has_any_project_access_is_false_for_an_outsider():
    """
    **Feature: projects (PRJ-17 project access)**
    **Property: a user with no membership and no global role has no
    project access.**
    """
    session, _ids = _session_with_projects()
    manager = ProjectManager(session, access_resolver=_resolver({}))

    testbase.assert_equal(manager.has_any_project_access(OUTSIDER), False)
    return
