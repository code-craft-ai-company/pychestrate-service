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

from typing import Optional


DEFAULT_LOGIN = "admin"
DEFAULT_EMAIL = "admin@example.com"
DEFAULT_DISPLAY_NAME = "Admin"

ENV_LOGIN = "PYCHESTRATE_TEST_ADMIN_LOGIN"
ENV_PASSWORD = "PYCHESTRATE_TEST_ADMIN_PASSWORD"
ENV_EMAIL = "PYCHESTRATE_SEED_ADMIN_EMAIL"


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


def _upsert_admin(*, options: SeedAdminOptions) -> SeedAdminResult:
    """
        Create the modern + legacy admin user pair on a fresh database, or
        reset the password of an existing admin, then ensure the legacy row
        and the system-admin RBAC binding. Only the one admin user is
        touched; existing data is never wiped.

        Delegates to the shared
        :func:`identity.setup.testadmin_seeder.seed_or_reset_test_admin`
        so the standalone tool and the runtime ``PYCHESTRATE_TEST_MODE``
        hook share a single seeding implementation.

        :param options: The resolved seed-admin options.

        :returns: A :class:`SeedAdminResult` describing the outcome.

        :raises RuntimeError: If the database write fails.
    """
    from automojo.pychestrate.webservice.identity.setup.testadmin_seeder import (
        seed_or_reset_test_admin,
    )

    session_factory = _get_session_factory()
    seed_result = seed_or_reset_test_admin(
        session_factory=session_factory,
        login=options.login,
        email=options.email,
        password=options.password,
        display_name=options.display_name,
    )

    result = SeedAdminResult(
        user_id=seed_result.user_id,
        login=seed_result.login,
        email=seed_result.email,
        action=seed_result.action,
        legacy_written=seed_result.legacy_written,
    )
    rtnval = result
    return rtnval


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
