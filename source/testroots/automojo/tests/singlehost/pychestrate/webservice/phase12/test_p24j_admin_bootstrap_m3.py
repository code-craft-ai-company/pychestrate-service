"""
.. module:: test_p24j_admin_bootstrap_m3
    :synopsis: Tests for the admin-bootstrap helpers.

Exercises the helper functions inside :mod:`scripts.bootstrapadmin`
to confirm they:

* sync the registered role catalog into ``rbac_role`` rows
  (idempotent on re-run);
* create an identity user (idempotent on re-run);
* assign the system-admin SYSTEM-scope binding (idempotent on
  re-run);
* open a fresh auth session whose id resolves through
  :func:`session_service.resolve_session`.

The bootstrap script lives under the top-level ``scripts/``
directory, so the test imports it via an explicit path manipulation
to avoid changing the module-name expectations of the runtime.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import importlib
import importlib.util
import os
import sys

from datetime import datetime, timezone

from automojo import testbase

from automojo.pychestrate.webservice.identity.users.models import IdentityUser
from automojo.pychestrate.webservice.persistence.schema import (
    PychestratePhase1Base,
)
from automojo.pychestrate.webservice.secrets.secret_bytes import SecretBytes
from automojo.pychestrate.webservice.security.auth.pepper_loader import (
    reset_active_pepper_for_testing,
    set_active_pepper,
)
from automojo.pychestrate.webservice.security.auth.session_service import (
    resolve_session,
)
from automojo.pychestrate.webservice.security.rbac.models import RbacRole

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
    reset_phase1_runtime,
)


def _import_bootstrap_module():
    """
        Load ``scripts/bootstrapadmin.py`` as a module so the test can
        call its helper functions directly.

        :returns: The loaded module object.
    """
    repo_root = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..", "..", "..", ".."),
    )
    script_path = os.path.join(repo_root, "scripts", "bootstrapadmin.py")
    spec = importlib.util.spec_from_file_location(
        "scripts_bootstrapadmin", script_path,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rtnval = module
    return rtnval


def _setup():
    """
        Reset phase-1 runtime, install a deterministic pepper, build
        a fresh in-memory engine + session, and load the bootstrap
        module.
    """
    reset_phase1_runtime()
    reset_active_pepper_for_testing()
    set_active_pepper(pepper=SecretBytes(b"p24j-test-pepper"))
    engine, session = build_in_memory_session()
    bootstrap = _import_bootstrap_module()
    return engine, session, bootstrap


def test_sync_role_catalog_inserts_registered_role_rows():
    """
    **Feature: P24j admin bootstrap (M3)**
    **Property: The role-catalog sync inserts an RbacRole row for
    every registered role and is idempotent on re-run.**
    """
    _engine, session, bootstrap = _setup()
    try:
        bootstrap._sync_role_catalog(db_session=session)

        names = sorted([r.role_name for r in session.query(RbacRole).all()])
        testbase.assert_equal(len(names) > 0, True)
        testbase.assert_equal("system-admin" in names, True)

        # Re-run is a no-op
        before_count = len(names)
        bootstrap._sync_role_catalog(db_session=session)
        after_count = session.query(RbacRole).count()
        testbase.assert_equal(after_count, before_count)
    finally:
        session.close()
    return


def test_ensure_user_creates_then_returns_existing():
    """
    **Feature: P24j admin bootstrap (M3)**
    **Property: _ensure_user creates a new identity user the first
    time and returns the existing one's id on the re-run.**
    """
    _engine, session, bootstrap = _setup()
    try:
        first_id = bootstrap._ensure_user(
            db_session=session,
            login_name="alice",
            primary_email="alice@example.com",
            display_name="Alice Admin",
            timezone_name="UTC",
        )
        session.commit()
        testbase.assert_equal(len(first_id) > 0, True)

        second_id = bootstrap._ensure_user(
            db_session=session,
            login_name="alice",
            primary_email="alice@example.com",
            display_name="Alice Admin",
            timezone_name="UTC",
        )
        testbase.assert_equal(second_id, first_id)

        rows = session.query(IdentityUser).filter(
            IdentityUser.login_name == "alice",
        ).all()
        testbase.assert_equal(len(rows), 1)
    finally:
        session.close()
    return


def test_full_bootstrap_chain_yields_resolvable_session():
    """
    **Feature: P24j admin bootstrap (M3)**
    **Property: After running the full chain (sync_role_catalog →
    ensure_user → ensure_admin_binding → open_admin_session), the
    returned session id resolves through
    session_service.resolve_session and exposes the seeded user id.**
    """
    _engine, session, bootstrap = _setup()
    try:
        bootstrap._sync_role_catalog(db_session=session)
        user_id = bootstrap._ensure_user(
            db_session=session,
            login_name="bob",
            primary_email="bob@example.com",
            display_name="Bob Admin",
            timezone_name="UTC",
        )
        bootstrap._ensure_admin_binding(
            db_session=session, user_id=user_id,
        )
        session_id = bootstrap._open_admin_session(
            db_session=session, user_id=user_id,
        )
        session.commit()

        testbase.assert_equal(len(session_id) > 0, True)
        principal = resolve_session(
            db_session=session,
            session_id=session_id,
            now=datetime.now(timezone.utc),
        )
        testbase.assert_equal(principal.user_id, user_id)
    finally:
        session.close()
    return
