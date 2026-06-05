#!/usr/bin/env python3
"""
    Idempotent seed/reset tool for a known-credential test administrator.

    This standalone script CREATES (on a fresh database) or RESETS THE
    PASSWORD OF (on an existing database) a single test admin user with a
    known login and password. It writes BOTH the modern identity records
    (``identity_users`` + ``auth_local_credentials``) AND the legacy
    ``user`` row (``roles="admin"``), and binds the ``system-admin`` RBAC
    role at SYSTEM scope so the admin actually has permissions under the
    modern ``rbac_evaluator``.

    It is designed to run as a SEPARATE PROCESS from the webservice,
    against the SAME database the running service uses, by relying on the
    persona-derived ``PYCHESTRATE_DATABASE_URL`` default and the shared
    KEK/pepper files (see ``development/seed-test-admin.sh``).

    The script ONLY upserts the one admin user. It never deletes, wipes,
    or otherwise mutates other rows.

    Usage (env vars are supplied by ``development/seed-test-admin.sh``)::

        development/seed-test-admin.sh \
            --login admin \
            --email admin@example.com \
            --password 's3cr3t' \
            --display-name 'Admin'
"""

import argparse
import os
import sys
import uuid

from typing import Optional, Tuple


DEFAULT_LOGIN = "admin"
DEFAULT_EMAIL = "admin@example.com"
DEFAULT_DISPLAY_NAME = "Admin"

ENV_LOGIN = "PYCHESTRATE_TEST_ADMIN_LOGIN"
ENV_PASSWORD = "PYCHESTRATE_TEST_ADMIN_PASSWORD"
ENV_EMAIL = "PYCHESTRATE_SEED_ADMIN_EMAIL"

LEGACY_ADMIN_ROLE = "admin"


class SeedAdminOptions:
    """
        Container for the resolved seed-admin input options.
    """

    def __init__(
            self,
            *,
            login: str,
            email: str,
            password: str,
            display_name: str
        ) -> None:
        """
            Initialize the resolved option set.

            :param login: The admin login name.
            :param email: The admin primary email address.
            :param password: The plaintext password to set.
            :param display_name: The admin display name.
        """
        self.login = login
        self.email = email
        self.password = password
        self.display_name = display_name
        return


class SeedAdminResult:
    """
        Outcome of a seed-admin operation.
    """

    def __init__(
            self,
            *,
            user_id: str,
            login: str,
            email: str,
            action: str,
            legacy_written: bool
        ) -> None:
        """
            Initialize the result record.

            :param user_id: The user UUID as a string.
            :param login: The admin login name.
            :param email: The admin primary email address.
            :param action: Either ``"created"`` or ``"reset"``.
            :param legacy_written: Whether the legacy user row was written.
        """
        self.user_id = user_id
        self.login = login
        self.email = email
        self.action = action
        self.legacy_written = legacy_written
        return


def _build_arg_parser() -> argparse.ArgumentParser:
    """
        Construct the argument parser for the seed-admin CLI.

        :returns: A configured :class:`argparse.ArgumentParser`.
    """
    parser = argparse.ArgumentParser(
        prog="seed_test_admin",
        description=(
            "Create or reset a known-credential test admin user in the "
            "live pychestrate database (modern identity + legacy + RBAC)."
        ),
    )
    parser.add_argument(
        "--login",
        dest="login",
        default=None,
        help="Admin login name (env {} or default '{}').".format(
            ENV_LOGIN, DEFAULT_LOGIN
        ),
    )
    parser.add_argument(
        "--email",
        dest="email",
        default=None,
        help="Admin primary email (env {} or default '{}').".format(
            ENV_EMAIL, DEFAULT_EMAIL
        ),
    )
    parser.add_argument(
        "--password",
        dest="password",
        default=None,
        help="Admin plaintext password (env {}; REQUIRED, no default).".format(
            ENV_PASSWORD
        ),
    )
    parser.add_argument(
        "--display-name",
        dest="display_name",
        default=None,
        help="Admin display name (default '{}').".format(DEFAULT_DISPLAY_NAME),
    )

    rtnval = parser
    return rtnval


def _resolve_options(*, args: argparse.Namespace) -> SeedAdminOptions:
    """
        Resolve the effective options from CLI args with env fallbacks
        and safe defaults. The password has NO default and is required.

        :param args: Parsed argparse namespace.

        :returns: A :class:`SeedAdminOptions` instance.

        :raises ValueError: If no password is supplied via CLI or env.
    """
    login = args.login
    if login is None:
        login = os.environ.get(ENV_LOGIN, None)
    if login is None:
        login = DEFAULT_LOGIN

    email = args.email
    if email is None:
        email = os.environ.get(ENV_EMAIL, None)
    if email is None:
        email = DEFAULT_EMAIL

    display_name = args.display_name
    if display_name is None:
        display_name = DEFAULT_DISPLAY_NAME

    password = args.password
    if password is None:
        password = os.environ.get(ENV_PASSWORD, None)

    if password is None or len(password) == 0:
        err_msg_lines = ["A password is required but none was supplied."]
        err_msg_lines.append(
            "Pass --password <value> or set the {} environment variable.".format(
                ENV_PASSWORD
            )
        )
        err_msg = os.linesep.join(err_msg_lines)
        raise ValueError(err_msg)

    options = SeedAdminOptions(
        login=login,
        email=email,
        password=password,
        display_name=display_name,
    )

    rtnval = options
    return rtnval


def _establish_persona_if_needed() -> None:
    """
        Establish the webapp persona so config-loading precedence matches
        the webservice. Tolerates an already-established persona (idempotent
        across re-entry), mirroring the bootstrap sequence in SPEC[bootstrap].

        :returns: None.
    """
    from automojo.webworks.webapplication import (
        establish_webapp_persona,
        PersonaAlreadyEstablishedError,
    )
    from automojo.pychestrate.webservice.pychestrate_presence import (
        resolve_presence_dir,
    )

    presence_dir = resolve_presence_dir(argv=sys.argv[1:])

    try:
        establish_webapp_persona(
            name="pychestrate",
            logger_name="scms",
            log_basename="pychestrate",
            presence_dir=presence_dir,
        )
    except PersonaAlreadyEstablishedError:
        # A persona is already established in this process; reuse it.
        pass

    return


def _bootstrap_runtime() -> None:
    """
        Load config from the environment and bootstrap the runtime so the
        engine, session factory, KEK, and password pepper are ready and
        ``local_flow.hash_password`` will succeed (SPEC[bootstrap]).

        :returns: None.
    """
    from automojo.pychestrate.webservice.runtime_bootstrap import (
        load_config_from_environment,
        bootstrap_runtime,
    )

    runtime_config = load_config_from_environment()
    bootstrap_runtime(config=runtime_config)

    return


def _get_session_factory() -> object:
    """
        Retrieve the session factory published on ``SITE_SHARED_GLOBALS``
        by ``bootstrap_runtime`` (SPEC[bootstrap], Phase 3).

        :returns: The configured SQLAlchemy session factory callable.

        :raises RuntimeError: If the factory was not published.
    """
    from automojo.pychestrate.webservice.metadata import SITE_SHARED_GLOBALS

    session_factory = SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY
    if session_factory is None:
        err_msg_lines = ["The database session factory was not published."]
        err_msg_lines.append(
            "bootstrap_runtime() must run before acquiring the factory."
        )
        err_msg = os.linesep.join(err_msg_lines)
        raise RuntimeError(err_msg)

    rtnval = session_factory
    return rtnval


def _reset_login_backoff() -> None:
    """
        Reset exponential login backoff state so a fresh seed/reset is not
        rate-limited (SPEC[bootstrap], optional helper). Best-effort.

        :returns: None.
    """
    from automojo.pychestrate.webservice.security.auth import local_flow

    reset_helper = getattr(local_flow, "reset_backoff_for_testing", None)
    if reset_helper is not None:
        reset_helper()

    return


def _write_legacy_admin_row(
        *,
        db_session: object,
        user_id: uuid.UUID,
        login: str,
        email: str,
        display_name: str
    ) -> bool:
    """
        Idempotently upsert the legacy ``user`` row with ``roles="admin"``,
        wrapped in a savepoint so a missing legacy table (the
        AUTO_CREATE_SCHEMA dev case) does not abort the modern commit
        (mirrors ``create_initial_admin``'s fallback).

        :param db_session: The active SQLAlchemy session.
        :param user_id: The shared user UUID.
        :param login: The admin login name.
        :param email: The admin primary email address.
        :param display_name: The admin display name.

        :returns: ``True`` if the legacy row was written/ensured, else
                  ``False`` (legacy table absent).
    """
    from sqlalchemy.exc import OperationalError as _OpError
    from automojo.pychestrate.core.orm import User as _LegacyUser

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
                ownertag="seed-test-admin",
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
        print(
            "seed_test_admin: legacy user row skipped (table missing?): {}".format(
                first_line
            ),
            file=sys.stderr,
        )
        legacy_written = False

    rtnval = legacy_written
    return rtnval


def _bind_system_admin_role(
        *,
        db_session: object,
        user_id: uuid.UUID
    ) -> None:
    """
        Ensure the modern ``system-admin`` RBAC role exists and is bound to
        the user at SYSTEM scope, then invalidate any cached denials so the
        binding takes effect immediately (SPEC[seedpair]).

        :param db_session: The active SQLAlchemy session.
        :param user_id: The shared user UUID.

        :returns: None.
    """
    from automojo.pychestrate.webservice.security.rbac.seeding import (
        ensure_system_admin_binding_for_user,
    )
    from automojo.pychestrate.webservice.security.rbac import cache as rbac_cache

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


def _upsert_admin(*, options: SeedAdminOptions) -> SeedAdminResult:
    """
        Create the modern + legacy admin user pair on a fresh database, or
        reset the password of an existing admin, then ensure the legacy row
        and the system-admin RBAC binding. Only the one admin user is
        touched; existing data is never wiped (SPEC[models]/[seedpair]).

        :param options: The resolved seed-admin options.

        :returns: A :class:`SeedAdminResult` describing the outcome.

        :raises RuntimeError: If the database write fails.
    """
    from automojo.pychestrate.webservice.security.auth import local_flow
    from automojo.pychestrate.webservice.identity.users.models import (
        IdentityUser,
        UserStatus,
    )
    from automojo.pychestrate.webservice.security.auth.models import (
        AuthLocalCredentials,
    )

    session_factory = _get_session_factory()
    db_session = session_factory()
    try:
        existing_modern = (
            db_session.query(IdentityUser)
            .filter(IdentityUser.login_name == options.login)
            .first()
        )

        encoded_hash, algo_params = local_flow.hash_password(
            password=options.password
        )

        if existing_modern is not None:
            action = "reset"
            user_id = existing_modern.user_id
            if isinstance(user_id, str):
                user_id = uuid.UUID(user_id)

            existing_modern.primary_email = options.email
            existing_modern.display_name = options.display_name
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
                login_name=options.login,
                primary_email=options.email,
                display_name=options.display_name,
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
            login=options.login,
            email=options.email,
            display_name=options.display_name,
        )

        _bind_system_admin_role(
            db_session=db_session,
            user_id=user_id,
        )

        db_session.commit()

        result = SeedAdminResult(
            user_id=str(user_id),
            login=options.login,
            email=options.email,
            action=action,
            legacy_written=legacy_written,
        )
        rtnval = result
        return rtnval
    except Exception as commit_exc:
        db_session.rollback()
        err_msg_lines = ["Failed to seed/reset the test admin user."]
        err_msg_lines.append("LOGIN: {}".format(options.login))
        err_msg_lines.append("EMAIL: {}".format(options.email))
        err_msg_lines.append("CAUSE: {}".format(str(commit_exc)))
        err_msg = os.linesep.join(err_msg_lines)
        raise RuntimeError(err_msg) from commit_exc
    finally:
        try:
            db_session.close()
        except Exception:
            pass


def _print_summary(*, result: SeedAdminResult) -> None:
    """
        Print a clear, password-free summary of the operation.

        :param result: The seed-admin outcome.

        :returns: None.
    """
    summary_lines = ["seed_test_admin: success"]
    summary_lines.append("    action:        {}".format(result.action))
    summary_lines.append("    login:         {}".format(result.login))
    summary_lines.append("    email:         {}".format(result.email))
    summary_lines.append("    user_id:       {}".format(result.user_id))
    summary_lines.append(
        "    legacy_row:    {}".format(
            "written" if result.legacy_written is True else "skipped"
        )
    )
    summary_lines.append("    rbac_binding:  system-admin @ SYSTEM scope")
    summary = os.linesep.join(summary_lines)
    print(summary)
    return


def main(*, argv: Optional[list] = None) -> int:
    """
        Entry point: parse args, bootstrap the runtime, and upsert the
        test admin user.

        :param argv: Optional argument vector; defaults to ``sys.argv[1:]``.

        :returns: Process exit code (0 on success, non-zero on failure).
    """
    if argv is None:
        argv = sys.argv[1:]

    parser = _build_arg_parser()
    args = parser.parse_args(args=argv)

    try:
        options = _resolve_options(args=args)

        _establish_persona_if_needed()
        _bootstrap_runtime()
        _reset_login_backoff()

        result = _upsert_admin(options=options)
        _print_summary(result=result)

        rtnval = 0
        return rtnval
    except Exception as run_exc:
        err_msg_lines = ["seed_test_admin: FAILED"]
        err_msg_lines.append(str(run_exc))
        err_msg = os.linesep.join(err_msg_lines)
        print(err_msg, file=sys.stderr)

        rtnval = 1
        return rtnval


if __name__ == "__main__":
    exit_code = main(argv=sys.argv[1:])
    sys.exit(exit_code)
