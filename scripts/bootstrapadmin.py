"""
.. module:: scripts.bootstrapadmin
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Seed an admin user + system-admin binding + open session.

.. moduleauthor:: Automation Mojo LLC

First-use bring-up helper that prepares a DB so a developer can drive
the REST surface end-to-end. Steps:

1. Connects to the configured database.
2. Installs a password pepper (in-memory; the same pepper must be
   used by the running service).
3. Registers the Phase-1 built-in extensions and synchronizes the
   role catalog into ``rbac_role`` rows (idempotent).
4. Creates an identity user from the supplied flags / env.
5. Assigns the ``system-admin`` system-scope binding to that user.
6. Opens a fresh auth session and prints the cookie value.

Usage::

    PYCHESTRATE_DATABASE_URL=sqlite:///./pychestrate.db \\
        PYCHESTRATE_ADMIN_PEPPER=dev-pepper \\
        python scripts/bootstrapadmin.py \\
            --login alice --email alice@example.com \\
            --display-name 'Alice Admin'

The printed cookie value is what callers paste into
``-H "Cookie: pychestrate_session=<value>"``.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import argparse
import os
import sys

from datetime import datetime, timezone
from typing import Optional

import sqlalchemy as sa

from sqlalchemy.orm import sessionmaker

from automojo.pychestrate.core.defaults import new_uuid

from automojo.pychestrate.webservice.extensions.bootstrap import (
    register_phase1_builtin_extensions,
)
from automojo.pychestrate.webservice.identity.users import user_service
from automojo.pychestrate.webservice.identity.users.exceptions import (
    UserAlreadyExistsError,
)
from automojo.pychestrate.webservice.identity.users.models import IdentityUser
from automojo.pychestrate.webservice.persistence.schema import (
    PychestratePhase1Base,
)
from automojo.pychestrate.webservice.secrets.secret_bytes import SecretBytes
from automojo.pychestrate.webservice.security.auth.cookies import (
    SESSION_COOKIE_NAME,
)
from automojo.pychestrate.webservice.security.auth.models import (
    AuthProviderKind,
)
from automojo.pychestrate.webservice.security.auth.pepper_loader import (
    reset_active_pepper_for_testing,
    set_active_pepper,
)
from automojo.pychestrate.webservice.security.auth.session_service import (
    RequestFingerprint,
    open_session,
)
from automojo.pychestrate.webservice.security.rbac import binding_service
from automojo.pychestrate.webservice.security.rbac.catalog import (
    load_catalog_from_registry,
)
from automojo.pychestrate.webservice.security.rbac.models import (
    BindingScope,
    PrincipalKind,
    RbacRole,
    RoleSource,
)


DATABASE_URL_ENV_VAR = "PYCHESTRATE_DATABASE_URL"
PEPPER_ENV_VAR = "PYCHESTRATE_ADMIN_PEPPER"
SYSTEM_ADMIN_ROLE_NAME = "system-admin"


def _resolve_database_url(*, cli_value: Optional[str]) -> str:
    """
        Resolve the DB URL preferring the CLI flag, then the env var.
    """
    if cli_value is not None:
        if len(cli_value.strip()) > 0:
            return cli_value
    env_value = os.environ.get(DATABASE_URL_ENV_VAR, None)
    if env_value is not None:
        if len(env_value.strip()) > 0:
            return env_value
    sys.stderr.write(
        "ERROR: database url not configured. "
        "Set --database-url or {0}.{1}".format(
            DATABASE_URL_ENV_VAR, os.linesep,
        ),
    )
    raise SystemExit(2)


def _resolve_pepper(*, cli_value: Optional[str]) -> str:
    """
        Resolve the password pepper preferring CLI flag, then env var.
    """
    if cli_value is not None:
        if len(cli_value.strip()) > 0:
            return cli_value
    env_value = os.environ.get(PEPPER_ENV_VAR, None)
    if env_value is not None:
        if len(env_value.strip()) > 0:
            return env_value
    sys.stderr.write(
        "ERROR: pepper not configured. "
        "Set --pepper or {0}.{1}".format(
            PEPPER_ENV_VAR, os.linesep,
        ),
    )
    raise SystemExit(2)


def _sync_role_catalog(*, db_session) -> None:
    """
        Insert :class:`RbacRole` rows for every role in the registry
        catalog. Idempotent — skips roles that already have a row.
    """
    catalog = load_catalog_from_registry()
    existing_names = {
        row.role_name
        for row in db_session.query(RbacRole).all()
    }
    inserted = 0
    for role_name in sorted(catalog.roles.keys()):
        if role_name in existing_names:
            continue
        role = RbacRole(
            role_id=new_uuid(),
            role_name=role_name,
            source=RoleSource.BUILTIN,
            source_name="phase1-bootstrap",
            description="",
        )
        db_session.add(role)
        inserted += 1
    if inserted > 0:
        db_session.commit()
    sys.stdout.write(
        "Role catalog synced: {0} new, {1} existing.{2}".format(
            inserted, len(existing_names), os.linesep,
        ),
    )
    return


def _ensure_user(
        *,
        db_session,
        login_name: str,
        primary_email: str,
        display_name: str,
        timezone_name: str,
    ) -> str:
    """
        Create the user (or return the existing one's id).
    """
    try:
        user = user_service.create_user(
            db_session=db_session,
            login_name=login_name,
            primary_email=primary_email,
            display_name=display_name,
            timezone=timezone_name,
            provisioning_source="bootstrap",
            external_id=None,
            actor_user_id=None,
        )
        sys.stdout.write(
            "Created identity user: {0}{1}".format(
                user.login_name, os.linesep,
            ),
        )
        rtnval = str(user.user_id)
        return rtnval
    except UserAlreadyExistsError:
        existing = (
            db_session.query(IdentityUser)
            .filter(IdentityUser.login_name == login_name)
            .first()
        )
        sys.stdout.write(
            "Identity user already exists: {0}{1}".format(
                login_name, os.linesep,
            ),
        )
        rtnval = str(existing.user_id)
        return rtnval


def _ensure_admin_binding(*, db_session, user_id: str) -> None:
    """
        Bind the user to ``system-admin`` at SYSTEM scope. Idempotent
        (``binding_service.assign_role`` returns the existing row when
        the binding already exists).
    """
    binding = binding_service.assign_role(
        db_session=db_session,
        role_name=SYSTEM_ADMIN_ROLE_NAME,
        principal_kind=PrincipalKind.USER,
        principal_id=user_id,
        scope_kind=BindingScope.SYSTEM,
        scope_id=None,
        inherits_into_project=False,
        actor_user_id=user_id,
    )
    sys.stdout.write(
        "system-admin binding ensured: {0}{1}".format(
            binding.binding_id, os.linesep,
        ),
    )
    return


def _open_admin_session(*, db_session, user_id: str) -> str:
    """
        Open a fresh auth session for ``user_id`` and return the
        session id (the value the cookie carries).
    """
    seated = open_session(
        db_session=db_session,
        user_id=user_id,
        provider_kind=AuthProviderKind.LOCAL,
        provider_name="local",
        mfa_method_name=None,
        access_token_payload=None,
        refresh_token_payload=None,
        request_fingerprint=RequestFingerprint(
            ip_fingerprint="bootstrap",
            user_agent_fingerprint="bootstrap-cli",
        ),
        idle_timeout_seconds=60 * 60 * 8,
        max_lifetime_seconds=60 * 60 * 24,
    )
    rtnval = str(seated.session_id)
    return rtnval


def main(*, argv: Optional[list] = None) -> int:
    """
        CLI entry point.
    """
    parser = argparse.ArgumentParser(
        description="Bootstrap an admin user, role binding, and session.",
    )
    parser.add_argument("--database-url", dest="database_url", default=None)
    parser.add_argument("--pepper", dest="pepper", default=None)
    parser.add_argument("--login", dest="login", default="admin")
    parser.add_argument(
        "--email", dest="email", default="admin@example.com",
    )
    parser.add_argument(
        "--display-name", dest="display_name", default="Bootstrap Admin",
    )
    parser.add_argument("--timezone", dest="timezone", default="UTC")
    parser.add_argument(
        "--create-schema",
        dest="create_schema",
        action="store_true",
        help="Run metadata.create_all before seeding (handy for a fresh SQLite file).",
    )
    args = parser.parse_args(argv)

    database_url = _resolve_database_url(cli_value=args.database_url)
    pepper_str = _resolve_pepper(cli_value=args.pepper)

    sys.stdout.write(
        "Connecting to: {0}{1}".format(database_url, os.linesep),
    )
    engine = sa.create_engine(database_url)
    if args.create_schema is True:
        PychestratePhase1Base.metadata.create_all(engine)
        sys.stdout.write(
            "Phase-1 schema created.{0}".format(os.linesep),
        )

    register_phase1_builtin_extensions()
    reset_active_pepper_for_testing()
    set_active_pepper(pepper=SecretBytes(pepper_str.encode("utf-8")))

    factory = sessionmaker(bind=engine)
    db_session = factory()
    try:
        _sync_role_catalog(db_session=db_session)
        user_id = _ensure_user(
            db_session=db_session,
            login_name=args.login,
            primary_email=args.email,
            display_name=args.display_name,
            timezone_name=args.timezone,
        )
        _ensure_admin_binding(db_session=db_session, user_id=user_id)
        session_id = _open_admin_session(
            db_session=db_session, user_id=user_id,
        )
        db_session.commit()
    finally:
        db_session.close()

    sys.stdout.write(
        "{0}Admin bootstrap complete.{0}".format(os.linesep),
    )
    sys.stdout.write(
        "  USER_ID: {0}{1}".format(user_id, os.linesep),
    )
    sys.stdout.write(
        "  SESSION_ID (cookie value): {0}{1}".format(
            session_id, os.linesep,
        ),
    )
    sys.stdout.write(
        "{0}Use the cookie like:{0}".format(os.linesep),
    )
    sys.stdout.write(
        "  curl -H \"Cookie: {0}={1}\" http://localhost:8080/api/v1/...{2}".format(
            SESSION_COOKIE_NAME, session_id, os.linesep,
        ),
    )

    rtnval = 0
    return rtnval


if __name__ == "__main__":
    raise SystemExit(main())
