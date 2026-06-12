"""
.. module:: identity.setup.testadmin_seeder
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Idempotent create-or-reset of a known-credential test
               administrator, shared by the runtime test-mode hook and
               the standalone ``development/seed_test_admin.py`` tool.

.. moduleauthor:: Code Craft AI LLC

Unlike :func:`identity.setup.setup_service.create_initial_admin` -- which
refuses to run once any user exists (the setup-wizard one-shot guard) --
:func:`seed_or_reset_test_admin` is deliberately idempotent: it CREATES the
admin on a fresh database or RESETS THE PASSWORD of the existing admin on a
populated one. That make-the-credential-true-no-matter-what behavior is what
``PYCHESTRATE_TEST_MODE`` and the live-deploy test suites need so a known
login/password pair always authenticates.

The function touches three stores, mirroring ``create_initial_admin`` exactly:

* modern identity (``identity_users`` + ``auth_local_credentials``),
* the legacy ``user`` row (``roles="admin"``) -- wrapped in a savepoint so a
  missing legacy table under ``PYCHESTRATE_AUTO_CREATE_SCHEMA`` does not abort
  the modern commit,
* the modern ``system-admin`` RBAC binding at SYSTEM scope.

Only the single named admin user is ever touched. No other rows are read,
mutated, or deleted.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import logging
import os
import uuid

from dataclasses import dataclass
from typing import Callable

from sqlalchemy.orm import Session as DbSession


SessionFactory = Callable[[], DbSession]


LEGACY_ADMIN_ROLE = "admin"


_module_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TestAdminSeedResult:
    """
        Outcome of a :func:`seed_or_reset_test_admin` call.

        :param user_id: The admin user UUID as a string.
        :param login: The admin login name.
        :param email: The admin primary email address.
        :param action: Either ``"created"`` or ``"reset"``.
        :param legacy_written: Whether the legacy ``user`` row was
                               written (``False`` when the legacy table
                               is absent under auto-create-schema).
    """
    user_id: str
    login: str
    email: str
    action: str
    legacy_written: bool


def _write_legacy_admin_row(
        *,
        db_session: DbSession,
        user_id: uuid.UUID,
        login: str,
        email: str,
        display_name: str
    ) -> bool:
    """
        Idempotently upsert the legacy ``user`` row with ``roles="admin"``,
        wrapped in a savepoint so a missing legacy table (the
        ``PYCHESTRATE_AUTO_CREATE_SCHEMA`` dev case) does not abort the modern
        commit.

        :param db_session: The active SQLAlchemy session.
        :param user_id: The shared user UUID.
        :param login: The admin login name.
        :param email: The admin primary email address.
        :param display_name: The admin display name.

        :returns: ``True`` if the legacy row was written / ensured, else
                  ``False`` (legacy table absent).
    """
    from sqlalchemy.exc import OperationalError as _OpError
    from ccai.pychestrate.core.orm import User as _LegacyUser

    legacy_savepoint = db_session.begin_nested()
    legacy_written = False
    try:
        existing_legacy = (
            db_session.query(_LegacyUser)
            .filter(_LegacyUser.id == user_id)
            .first()
        )
        if existing_legacy is not None:
            existing_legacy.email = email
            existing_legacy.login = login
            existing_legacy.display_name = display_name
            existing_legacy.status = "active"
            existing_legacy.authtype = "internal"
            existing_roles = existing_legacy.roles
            if existing_roles is None or len(existing_roles) == 0:
                existing_legacy.roles = LEGACY_ADMIN_ROLE
            else:
                role_parts = [part.strip() for part in existing_roles.split(",")]
                if LEGACY_ADMIN_ROLE not in role_parts:
                    role_parts.append(LEGACY_ADMIN_ROLE)
                    existing_legacy.roles = ",".join(role_parts)
        else:
            legacy_user = _LegacyUser(
                id=user_id,
                first_name="",
                last_name="",
                display_name=display_name,
                email=email,
                login=login,
                ownertag="test-mode-admin",
                status="active",
                roles=LEGACY_ADMIN_ROLE,
                authtype="internal",
            )
            db_session.add(legacy_user)

        db_session.flush()
        legacy_savepoint.commit()
        legacy_written = True
    except _OpError as op_exc:
        legacy_savepoint.rollback()
        first_line = str(op_exc).split(os.linesep)[0]
        _module_logger.warning(
            "pychestrate.testmode.legacy_user_skipped reason=%s",
            first_line,
        )
        legacy_written = False

    rtnval = legacy_written
    return rtnval


def _bind_system_admin_role(
        *,
        db_session: DbSession,
        user_id: uuid.UUID
    ) -> None:
    """
        Ensure the modern ``system-admin`` RBAC role exists and is bound to
        the user at SYSTEM scope, then invalidate any cached denials so the
        binding takes effect immediately.

        :param db_session: The active SQLAlchemy session.
        :param user_id: The shared user UUID.

        :returns: None.
    """
    from ccai.pychestrate.webservice.security.rbac.seeding import (
        ensure_system_admin_binding_for_user,
    )
    from ccai.pychestrate.webservice.security.rbac import cache as rbac_cache

    user_id_str = str(user_id)
    ensure_system_admin_binding_for_user(
        db_session=db_session,
        user_id=user_id_str,
        actor_user_id=None,
    )

    invalidate_helper = getattr(rbac_cache, "invalidate_principal", None)
    if invalidate_helper is not None:
        invalidate_helper(principal_id=user_id_str)

    return


def seed_or_reset_test_admin(
        *,
        session_factory: SessionFactory,
        login: str,
        email: str,
        password: str,
        display_name: str
    ) -> TestAdminSeedResult:
    """
        Create the modern + legacy admin user pair on a fresh database, or
        reset the password of the existing admin, then ensure the legacy row
        and the ``system-admin`` RBAC binding. Only the one admin user is
        touched; existing data is never wiped.

        Requires that the Phase-1 runtime is already bootstrapped (the KEK
        and password pepper installed) so ``local_flow.hash_password``
        succeeds. The standalone tool and the runtime test-mode hook both
        satisfy that precondition before calling.

        :param session_factory: Zero-arg SQLAlchemy session factory.
        :param login: The admin login name.
        :param email: The admin primary email address.
        :param password: The cleartext password to set (hashed before
                         storage).
        :param display_name: The admin display name.

        :returns: A :class:`TestAdminSeedResult` describing the outcome.

        :raises ValueError: If any required field is empty.
        :raises RuntimeError: If the database write fails.
    """
    from ccai.pychestrate.webservice.security.auth import local_flow
    from ccai.pychestrate.webservice.identity.users.models import (
        IdentityUser,
        UserStatus,
    )
    from ccai.pychestrate.webservice.security.auth.models import (
        AuthLocalCredentials,
    )

    if login is None or len(login) == 0:
        raise ValueError("seed_or_reset_test_admin requires a non-empty login")
    if email is None or len(email) == 0:
        raise ValueError("seed_or_reset_test_admin requires a non-empty email")
    if password is None or len(password) == 0:
        raise ValueError(
            "seed_or_reset_test_admin requires a non-empty password"
        )

    db_session = session_factory()
    try:
        existing_modern = (
            db_session.query(IdentityUser)
            .filter(IdentityUser.login_name == login)
            .first()
        )

        encoded_hash, algo_params = local_flow.hash_password(
            password=password
        )

        if existing_modern is not None:
            action = "reset"
            user_id = existing_modern.user_id
            if isinstance(user_id, str):
                user_id = uuid.UUID(user_id)

            existing_modern.primary_email = email
            existing_modern.display_name = display_name
            existing_modern.status = UserStatus.ACTIVE

            existing_credentials = (
                db_session.query(AuthLocalCredentials)
                .filter(AuthLocalCredentials.user_id == user_id)
                .first()
            )
            if existing_credentials is not None:
                existing_credentials.argon2id_hash = encoded_hash
                existing_credentials.algo_params = algo_params
            else:
                credentials = AuthLocalCredentials(
                    user_id=user_id,
                    argon2id_hash=encoded_hash,
                    algo_params=algo_params,
                )
                db_session.add(credentials)

            db_session.flush()
        else:
            action = "created"
            user_id = uuid.uuid4()

            modern_user = IdentityUser(
                user_id=user_id,
                login_name=login,
                primary_email=email,
                display_name=display_name,
                status=UserStatus.ACTIVE,
                provisioning_source="local",
                external_id=None,
                timezone="UTC",
            )
            db_session.add(modern_user)
            db_session.flush()

            credentials = AuthLocalCredentials(
                user_id=user_id,
                argon2id_hash=encoded_hash,
                algo_params=algo_params,
            )
            db_session.add(credentials)
            db_session.flush()

        legacy_written = _write_legacy_admin_row(
            db_session=db_session,
            user_id=user_id,
            login=login,
            email=email,
            display_name=display_name,
        )

        _bind_system_admin_role(
            db_session=db_session,
            user_id=user_id,
        )

        db_session.commit()

        result = TestAdminSeedResult(
            user_id=str(user_id),
            login=login,
            email=email,
            action=action,
            legacy_written=legacy_written,
        )
        rtnval = result
        return rtnval
    except Exception as commit_exc:
        db_session.rollback()
        err_msg_lines = ["Failed to seed/reset the test admin user."]
        err_msg_lines.append("LOGIN: {}".format(login))
        err_msg_lines.append("EMAIL: {}".format(email))
        err_msg_lines.append("CAUSE: {}".format(str(commit_exc)))
        err_msg = os.linesep.join(err_msg_lines)
        raise RuntimeError(err_msg) from commit_exc
    finally:
        try:
            db_session.close()
        except Exception:
            pass


__all__ = [
    "LEGACY_ADMIN_ROLE",
    "SessionFactory",
    "TestAdminSeedResult",
    "seed_or_reset_test_admin",
]
