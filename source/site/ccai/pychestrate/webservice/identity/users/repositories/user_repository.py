"""
.. module:: identity.users.repositories.user_repository
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Repository for IdentityUser rows.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import List, Optional, Tuple

from sqlalchemy import or_
from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.webservice.identity.users.models import IdentityUser


def insert(*, db_session: DbSession, user: IdentityUser) -> IdentityUser:
    """
        Insert a new identity user row and return the persistent instance.

        :param db_session: Active SQLAlchemy session.
        :param user: The fully-populated model instance to persist.

        :returns: The same instance, now attached to the session.
    """
    db_session.add(user)
    db_session.flush()
    rtnval = user
    return rtnval


def get_by_id(*, db_session: DbSession, user_id: str) -> Optional[IdentityUser]:
    """
        Return the row with the given user_id, or None when not found.

        :param db_session: Active SQLAlchemy session.
        :param user_id: Target user id.

        :returns: The :class:`IdentityUser` or None.
    """
    rtnval = db_session.query(IdentityUser).filter(IdentityUser.user_id == user_id).first()
    return rtnval


def get_by_login_name(*, db_session: DbSession, login_name: str) -> Optional[IdentityUser]:
    """
        Return the row whose login_name matches, or None when not found.

        :param db_session: Active SQLAlchemy session.
        :param login_name: Unique login value.

        :returns: The :class:`IdentityUser` or None.
    """
    normalized = login_name.lower()
    rtnval = db_session.query(IdentityUser).filter(IdentityUser.login_name == normalized).first()
    return rtnval


def get_by_email(*, db_session: DbSession, primary_email: str) -> Optional[IdentityUser]:
    """
        Return the row whose primary_email matches, or None when not found.

        :param db_session: Active SQLAlchemy session.
        :param primary_email: Email to match.

        :returns: The :class:`IdentityUser` or None.
    """
    normalized = primary_email.lower()
    rtnval = db_session.query(IdentityUser).filter(IdentityUser.primary_email == normalized).first()
    return rtnval


def list_page(
        *,
        db_session: DbSession,
        offset: int,
        limit: int
    ) -> List[IdentityUser]:
    """
        Return a page of identity users ordered by created_at.

        :param db_session: Active SQLAlchemy session.
        :param offset: Row offset.
        :param limit: Maximum rows to return.

        :returns: List of :class:`IdentityUser`.
    """
    query = db_session.query(IdentityUser).order_by(IdentityUser.created_at.asc())
    rtnval = query.offset(offset).limit(limit).all()
    return rtnval


def search_page(
        *,
        db_session: DbSession,
        text: str,
        offset: int,
        limit: int
    ) -> Tuple[List[IdentityUser], int]:
    """
        A page of identity users whose login name or display name contains ``text``
        (any user when it is empty), ordered by login name, and how many match.

        The text is matched literally: ``%`` and ``_`` are not wildcards.

        :param db_session: Active SQLAlchemy session.
        :param text: Substring to look for; empty matches every user.
        :param offset: Row offset.
        :param limit: Maximum rows to return.

        :returns: ``(rows, total matching)``.
    """
    query = db_session.query(IdentityUser)
    needle = text.strip()
    if len(needle) > 0:
        escaped = needle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = "%" + escaped + "%"
        query = query.filter(
            or_(
                IdentityUser.login_name.ilike(pattern, escape="\\"),
                IdentityUser.display_name.ilike(pattern, escape="\\"),
            )
        )
    total = query.count()
    rows = query.order_by(IdentityUser.login_name.asc()).offset(offset).limit(limit).all()
    return list(rows), int(total)
