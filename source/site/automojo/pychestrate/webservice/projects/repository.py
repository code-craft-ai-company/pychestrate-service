"""
.. module:: projects.repository
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Repository for :class:`Project` rows.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import uuid as _uuid

from typing import List, Optional

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.webservice.projects.models import (
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


def get_project_by_legacy_id(
        *,
        db_session: DbSession,
        legacy_proj_id: int
    ) -> Optional[Project]:
    """
        Look up a slug-:class:`Project` by the legacy ``proj_id``
        it is bridged to.

        :param db_session: Active SQLAlchemy session.
        :param legacy_proj_id: Legacy ``projects.proj_id`` BigInt.

        :returns: The :class:`Project` or None when no slug-Project
                  is bridged to that legacy id.
    """
    rtnval = (
        db_session.query(Project)
        .filter(Project.legacy_proj_id == legacy_proj_id)
        .first()
    )
    return rtnval


def _looks_like_uuid(*, candidate: str) -> bool:
    """
        Return True when ``candidate`` parses as a UUID.

        :param candidate: Candidate reference token.

        :returns: True when parseable as a UUID, else False.
    """
    try:
        _uuid.UUID(candidate)
    except (ValueError, AttributeError, TypeError):
        rtnval = False
        return rtnval
    rtnval = True
    return rtnval


def resolve_project(
        *,
        db_session: DbSession,
        slug: Optional[str] = None,
        uuid: Optional[str] = None,
        legacy_id: Optional[int] = None
    ) -> Optional[Project]:
    """
        Resolve the canonical slug-:class:`Project` from exactly one
        of three identity forms. This is the single entry point
        every project-scoped surface should use to translate a
        caller-supplied project reference into the canonical row
        (from which ``.project_id``, ``.slug``, and
        ``.legacy_proj_id`` are all readable).

        Exactly one of ``slug`` / ``uuid`` / ``legacy_id`` must be
        supplied. Supplying none or more than one is an API misuse
        and raises :class:`ValueError`.

        :param db_session: Active SQLAlchemy session.
        :param slug: Canonical project slug.
        :param uuid: New-model UUID ``project_id`` (string form).
        :param legacy_id: Legacy ``projects.proj_id`` BigInt.

        :returns: The :class:`Project` or None when unresolved.

        :raises ValueError: When not exactly one identity form is
                            supplied.
    """
    supplied = [
        value
        for value in (slug, uuid, legacy_id)
        if value is not None
    ]
    if len(supplied) != 1:
        err_msg_lines = [
            "resolve_project requires exactly one of slug / uuid /"
            " legacy_id.",
            "    slug: {}".format(slug),
            "    uuid: {}".format(uuid),
            "    legacy_id: {}".format(legacy_id),
        ]
        err_msg = os.linesep.join(err_msg_lines)
        raise ValueError(err_msg)

    if slug is not None:
        rtnval = get_project_by_slug(db_session=db_session, slug=slug)
        return rtnval

    if uuid is not None:
        rtnval = get_project_by_id(db_session=db_session, project_id=uuid)
        return rtnval

    rtnval = get_project_by_legacy_id(
        db_session=db_session, legacy_proj_id=legacy_id
    )
    return rtnval


def resolve_project_ref(
        *,
        db_session: DbSession,
        ref: str
    ) -> Optional[Project]:
    """
        Resolve a project from a single opaque reference token,
        sniffing its form: a parseable UUID resolves by
        ``project_id``; an all-digits token resolves by legacy
        ``proj_id``; anything else resolves by slug.

        :param db_session: Active SQLAlchemy session.
        :param ref: Project reference (slug | uuid | int as string).

        :returns: The :class:`Project` or None when unresolved.
    """
    if ref is None or len(ref) == 0:
        rtnval = None
        return rtnval

    if _looks_like_uuid(candidate=ref) is True:
        rtnval = resolve_project(db_session=db_session, uuid=ref)
        return rtnval

    if ref.isdigit() is True:
        rtnval = resolve_project(
            db_session=db_session, legacy_id=int(ref)
        )
        return rtnval

    rtnval = resolve_project(db_session=db_session, slug=ref)
    return rtnval


def resolve_legacy_proj_id(
        *,
        db_session: DbSession,
        ref: str
    ) -> Optional[int]:
    """
        Resolve a project reference to its bridged legacy
        ``proj_id``, for callers that must drive a legacy
        ``core/managers`` manager.

        :param db_session: Active SQLAlchemy session.
        :param ref: Project reference (slug | uuid | int as string).

        :returns: The legacy ``proj_id`` BigInt, or None when the
                  project is unresolved or has no legacy
                  counterpart.
    """
    project = resolve_project_ref(db_session=db_session, ref=ref)
    if project is None:
        rtnval = None
        return rtnval
    rtnval = project.legacy_proj_id
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
