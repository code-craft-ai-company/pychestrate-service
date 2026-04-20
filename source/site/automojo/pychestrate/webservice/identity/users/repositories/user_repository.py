"""
.. module:: identity.users.repositories.user_repository
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Repository for IdentityUser rows.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import List, Optional

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.webservice.identity.users.models import IdentityUser


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
