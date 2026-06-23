"""
.. module:: identity.users.user_service
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Public internal API for the 1-user-management feature.

.. moduleauthor:: Code Craft AI LLC

Implements the M1 skeleton of ``create_user`` / ``read_user`` per the
``1-user-management`` spec. Every mutation stages an outbox entry that
the session's after-commit hook publishes onto the in-process bus.
Downstream consumers (``1-audit-log``) register their subscribers against
the topic constants in :mod:`events`.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from ccai.errors.exceptions import SemanticError

from ccai.pychestrate.core.defaults import new_uuid, utc_now

from ccai.pychestrate.webservice.identity.users.events import UserEventTopics
from ccai.pychestrate.webservice.identity.users.exceptions import (
    UserAlreadyExistsError,
    UserNotFoundError,
)
from ccai.pychestrate.webservice.identity.users.models import IdentityUser, UserStatus
from ccai.pychestrate.webservice.identity.users.repositories import user_repository
from ccai.pychestrate.webservice.messaging.event_bus import EntityEvent
from ccai.pychestrate.webservice.messaging.outbox import enqueue_event


def create_user(
        *,
        db_session: DbSession,
        login_name: str,
        primary_email: str,
        display_name: str,
        timezone: str,
        provisioning_source: str,
        external_id: Optional[str],
        actor_user_id: Optional[str]
    ) -> IdentityUser:
    """
        Create a new identity user record.

        :param db_session: Active SQLAlchemy session.
        :param login_name: Unique account login; normalized to lower case.
        :param primary_email: RFC-5321 email address; normalized to lower case.
        :param display_name: Human-facing name.
        :param timezone: IANA timezone name.
        :param provisioning_source: Source name; ``"local"`` for admin-created.
        :param external_id: Stable id from the external source, if any.
        :param actor_user_id: Acting principal for audit attribution.

        :returns: The newly created :class:`IdentityUser`.
        :raises: UserAlreadyExistsError, SemanticError
    """
    if login_name is None or len(login_name.strip()) == 0:
        raise SemanticError("create_user requires a non-empty login_name")

    if primary_email is None or len(primary_email.strip()) == 0:
        raise SemanticError("create_user requires a non-empty primary_email")

    normalized_login = login_name.strip().lower()
    normalized_email = primary_email.strip().lower()

    existing_login = user_repository.get_by_login_name(
        db_session=db_session, login_name=normalized_login
    )
    if existing_login is not None:
        _raise_already_exists(login_name=normalized_login, conflict_field="login_name")

    existing_email = user_repository.get_by_email(
        db_session=db_session, primary_email=normalized_email
    )
    if existing_email is not None:
        _raise_already_exists(login_name=normalized_login, conflict_field="primary_email")

    now = utc_now()
    user = IdentityUser(
        user_id=new_uuid(),
        login_name=normalized_login,
        primary_email=normalized_email,
        display_name=display_name,
        status=UserStatus.ACTIVE,
        provisioning_source=provisioning_source,
        external_id=external_id,
        timezone=timezone,
        created_at=now,
        updated_at=now,
    )

    try:
        user_repository.insert(db_session=db_session, user=user)
    except IntegrityError as xcpt:
        _raise_already_exists(
            login_name=normalized_login, conflict_field="login_name_or_email"
        )

    event_payload = {
        "user_id": user.user_id,
        "login_name": user.login_name,
        "provisioning_source": user.provisioning_source,
        "actor_user_id": actor_user_id,
        "created_at": user.created_at.isoformat(),
    }
    event = EntityEvent(
        topic=UserEventTopics.USER_CREATED,
        payload=event_payload,
        source_event_id=new_uuid(),
    )
    enqueue_event(db_session=db_session, event=event)

    db_session.commit()

    rtnval = user
    return rtnval


def read_user(*, db_session: DbSession, user_id: str) -> IdentityUser:
    """
        Return the identity user with the given id.

        :param db_session: Active SQLAlchemy session.
        :param user_id: Target user id.

        :returns: The :class:`IdentityUser`.
        :raises: UserNotFoundError
    """
    user = user_repository.get_by_id(db_session=db_session, user_id=user_id)
    if user is None:
        err_msg_lines = ["Cannot read user — record not found."]
        err_msg_lines.append("USER_ID: {}".format(user_id))
        err_msg = os.linesep.join(err_msg_lines)
        raise UserNotFoundError(err_msg) from None

    rtnval = user
    return rtnval


def _raise_already_exists(*, login_name: str, conflict_field: str) -> None:
    """
        Construct and raise a multi-line UserAlreadyExistsError.

        :param login_name: The login that collided.
        :param conflict_field: Which unique column reported the conflict.

        :returns: None — never returns.
        :raises: UserAlreadyExistsError
    """
    err_msg_lines = ["Cannot create user — conflict with existing record."]
    err_msg_lines.append("LOGIN_NAME: {}".format(login_name))
    err_msg_lines.append("CONFLICT_FIELD: {}".format(conflict_field))
    err_msg = os.linesep.join(err_msg_lines)
    raise UserAlreadyExistsError(err_msg) from None
