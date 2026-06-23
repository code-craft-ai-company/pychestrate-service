"""
.. module:: projects.repository
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Repository for :class:`Project` rows.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import List, Optional

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.webservice.projects.models import (
    Project,
    ProjectMemberBinding,
    ProjectState,
)


def insert_project(*, db_session: DbSession, project: Project) -> Project:
    """
        Insert a new project row.

        :param db_session: Active SQLAlchemy session.
        :param project: Fully-populated :class:`Project` instance.

        :returns: The same instance attached to the session.
    """
    db_session.add(project)
    db_session.flush()
    rtnval = project
    return rtnval


def get_project_by_slug(*, db_session: DbSession, slug: str) -> Optional[Project]:
    """
        Look up a project by its canonical slug.

        :param db_session: Active SQLAlchemy session.
        :param slug: Canonical slug.

        :returns: The :class:`Project` or None.
    """
    rtnval = db_session.query(Project).filter(Project.slug == slug).first()
    return rtnval


def get_project_by_id(*, db_session: DbSession, project_id: str) -> Optional[Project]:
    """
        Look up a project by its id.

        :param db_session: Active SQLAlchemy session.
        :param project_id: Target project id.

        :returns: The :class:`Project` or None.
    """
    rtnval = db_session.query(Project).filter(Project.project_id == project_id).first()
    return rtnval


def list_projects(
        *,
        db_session: DbSession,
        state: Optional[ProjectState],
        offset: int,
        limit: int
    ) -> List[Project]:
    """
        Return a page of projects filtered by state.

        :param db_session: Active SQLAlchemy session.
        :param state: Optional state filter; None returns all states.
        :param offset: Row offset.
        :param limit: Maximum rows to return.

        :returns: List of :class:`Project`.
    """
    query = db_session.query(Project).order_by(Project.created_at.asc())
    if state is not None:
        query = query.filter(Project.state == state)

    rtnval = query.offset(offset).limit(limit).all()
    return rtnval


def delete_project(*, db_session: DbSession, project: Project) -> None:
    """
        Hard-delete a project row (member bindings cascade).

        :param db_session: Active SQLAlchemy session.
        :param project: The project to delete.

        :returns: None.
    """
    db_session.delete(project)
    db_session.flush()
    return


def insert_member_binding(
        *,
        db_session: DbSession,
        binding: ProjectMemberBinding
    ) -> ProjectMemberBinding:
    """
        Persist a new :class:`ProjectMemberBinding` row.
    """
    db_session.add(binding)
    db_session.flush()
    rtnval = binding
    return rtnval


def get_member_binding(
        *,
        db_session: DbSession,
        project_id: str,
        user_id: str,
        role_name: str
    ) -> Optional[ProjectMemberBinding]:
    """
        Look up a member binding by its composite key.
    """
    rtnval = (
        db_session.query(ProjectMemberBinding)
        .filter(ProjectMemberBinding.project_id == project_id)
        .filter(ProjectMemberBinding.user_id == user_id)
        .filter(ProjectMemberBinding.role_name == role_name)
        .first()
    )
    return rtnval


def delete_member_binding(
        *,
        db_session: DbSession,
        binding: ProjectMemberBinding
    ) -> None:
    """
        Remove a member binding row.
    """
    db_session.delete(binding)
    db_session.flush()
    return


def list_member_bindings(
        *,
        db_session: DbSession,
        project_id: str
    ) -> List[ProjectMemberBinding]:
    """
        Return every binding for a project.
    """
    query = db_session.query(ProjectMemberBinding).filter(
        ProjectMemberBinding.project_id == project_id
    )
    query = query.order_by(ProjectMemberBinding.added_at.asc())
    rtnval = query.all()
    return rtnval


def count_role_holders(
        *,
        db_session: DbSession,
        project_id: str,
        role_name: str
    ) -> int:
    """
        Count the number of bindings holding a specific role on a project.
    """
    query = db_session.query(ProjectMemberBinding).filter(
        ProjectMemberBinding.project_id == project_id
    )
    query = query.filter(ProjectMemberBinding.role_name == role_name)
    rtnval = int(query.count())
    return rtnval


def delete_bindings_for_user(
        *,
        db_session: DbSession,
        user_id: str
    ) -> int:
    """
        Remove every binding targeting a given user id.

        :returns: Count of removed rows.
    """
    query = db_session.query(ProjectMemberBinding).filter(
        ProjectMemberBinding.user_id == user_id
    )
    removed = query.delete(synchronize_session=False)
    db_session.flush()
    rtnval = int(removed)
    return rtnval
