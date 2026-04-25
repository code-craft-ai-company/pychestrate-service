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


from datetime import datetime
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.webservice.identity.users.models import (
    IdentityEmailVerification,
    IdentityUser,
    UserStatus,
)


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


def list_with_filters(
        *,
        db_session: DbSession,
        status: Optional[UserStatus],
        provisioning_source: Optional[str],
        login_prefix: Optional[str],
        cursor: Optional[Tuple[datetime, str]],
        limit: int
    ) -> List[IdentityUser]:
    """
        Return rows newer than the cursor matching every supplied
        filter. The cursor is a ``(created_at, user_id)`` pair so
        rows are stably orderable across pages.

        :param db_session: Active SQLAlchemy session.
        :param status: Optional :class:`UserStatus` filter.
        :param provisioning_source: Optional source filter.
        :param login_prefix: Case-insensitive login_name prefix
                             filter; ignored when None or empty.
        :param cursor: ``(created_at, user_id)`` exclusive lower
                       bound; ``None`` for the first page.
        :param limit: Maximum rows to return.

        :returns: List of :class:`IdentityUser`.
    """
    query = db_session.query(IdentityUser)
    if status is not None:
        query = query.filter(IdentityUser.status == status)
    if provisioning_source is not None and len(provisioning_source) > 0:
        query = query.filter(
            IdentityUser.provisioning_source == provisioning_source,
        )
    if login_prefix is not None and len(login_prefix) > 0:
        normalized_prefix = login_prefix.lower()
        like_clause = "{}%".format(normalized_prefix)
        query = query.filter(IdentityUser.login_name.like(like_clause))
    if cursor is not None:
        cursor_created, cursor_user_id = cursor
        # Strictly greater than the (created_at, user_id) tuple so
        # the cursor row is excluded from the next page.
        query = query.filter(
            (IdentityUser.created_at > cursor_created)
            | (
                (IdentityUser.created_at == cursor_created)
                & (IdentityUser.user_id > cursor_user_id)
            ),
        )
    query = query.order_by(
        IdentityUser.created_at.asc(), IdentityUser.user_id.asc(),
    )
    rtnval = query.limit(limit).all()
    return rtnval


def update_status(
        *,
        db_session: DbSession,
        user_id: str,
        status: UserStatus,
        updated_at: datetime
    ) -> IdentityUser:
    """
        Flip the row's status + bump ``updated_at``.

        :raises: ValueError when the row is not in the session.
    """
    row = (
        db_session.query(IdentityUser)
        .filter(IdentityUser.user_id == user_id)
        .first()
    )
    if row is None:
        err_msg = "Cannot update status — user_id {!r} not found.".format(
            user_id,
        )
        raise ValueError(err_msg) from None
    row.status = status
    row.updated_at = updated_at
    db_session.flush()
    return row


def update_email(
        *,
        db_session: DbSession,
        user_id: str,
        new_email: str,
        updated_at: datetime
    ) -> IdentityUser:
    """
        Replace the user's primary_email with the verified value
        and bump ``updated_at``.
    """
    row = (
        db_session.query(IdentityUser)
        .filter(IdentityUser.user_id == user_id)
        .first()
    )
    if row is None:
        err_msg = "Cannot update email — user_id {!r} not found.".format(
            user_id,
        )
        raise ValueError(err_msg) from None
    row.primary_email = new_email
    row.updated_at = updated_at
    db_session.flush()
    return row


def insert_email_verification(
        *,
        db_session: DbSession,
        verification: IdentityEmailVerification
    ) -> IdentityEmailVerification:
    """
        Persist an :class:`IdentityEmailVerification` row.
    """
    db_session.add(verification)
    db_session.flush()
    return verification


def find_email_verification_by_token(
        *,
        db_session: DbSession,
        token_hash: bytes
    ) -> Optional[IdentityEmailVerification]:
    """
        Find a verification row by its hashed token.
    """
    rtnval = (
        db_session.query(IdentityEmailVerification)
        .filter(IdentityEmailVerification.token_hash == token_hash)
        .first()
    )
    return rtnval


def delete_email_verifications_for_user(
        *,
        db_session: DbSession,
        user_id: str
    ) -> int:
    """
        Drop every pending verification for ``user_id``. Returns
        the number of rows deleted.
    """
    rows = (
        db_session.query(IdentityEmailVerification)
        .filter(IdentityEmailVerification.user_id == user_id)
        .all()
    )
    deleted = 0
    for row in rows:
        db_session.delete(row)
        deleted = deleted + 1
    db_session.flush()
    return deleted


def list_active_users_for_directory(
        *,
        db_session: DbSession,
        provisioning_source: str
    ) -> List[IdentityUser]:
    """
        Return every row owned by ``provisioning_source``,
        regardless of status. Used by the directory sync to
        compute the diff against the source's authoritative list.
    """
    rows = (
        db_session.query(IdentityUser)
        .filter(IdentityUser.provisioning_source == provisioning_source)
        .order_by(IdentityUser.external_id.asc())
        .all()
    )
    rtnval = list(rows)
    return rtnval
