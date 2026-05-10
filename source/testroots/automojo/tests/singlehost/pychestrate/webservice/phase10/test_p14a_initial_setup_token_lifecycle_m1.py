"""
.. module:: test_p14a_initial_setup_token_lifecycle_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Phase-10 tests for the initial-setup wizard's
               token + completion lifecycle in
               :class:`InitialSetupManager`.

.. moduleauthor:: Automation Mojo LLC

These tests exercise the manager directly against an in-memory
SQLite database (no flask, no webworks). They cover:

* token provisioning is idempotent (single row, single token file)
* the on-disk token file is mode 0600
* :meth:`verify_token` is timing-safe sha256 compare
* :meth:`mark_complete` stamps + deletes the token file + refuses
  re-entry
* losing the token file before completion regenerates the token
  (the operator can recover without a manual DB edit)
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import stat
import tempfile
import uuid

import sqlalchemy as sa

from sqlalchemy.orm import sessionmaker

from automojo import testbase

from automojo.pychestrate.webservice.identity.setup.exceptions import (
    InvalidSetupTokenError,
    SetupAlreadyCompleteError,
    SetupNotInitializedError,
)
from automojo.pychestrate.webservice.identity.setup.models import (
    InitialSetup,
    SINGLETON_KEY_VALUE,
)
from automojo.pychestrate.webservice.identity.setup.setup_manager import (
    DEFAULT_TOKEN_FILENAME,
    InitialSetupManager,
    TOKEN_FILE_MODE,
)
from automojo.pychestrate.webservice.persistence.schema import (
    PychestratePhase1Base,
)

# Importing the identity-users models registers them with
# PychestratePhase1Base.metadata so the FK on
# system_initial_setup.completed_by_user_id can be resolved by
# create_all. Without this import, sqlalchemy's metadata sorter
# fails with NoReferencedTableError.
from automojo.pychestrate.webservice.identity.users import models as _identity_users_models  # noqa: F401


def _build_session():
    """
        Build an in-memory SQLite engine with all Phase-1 tables
        (which now includes :class:`InitialSetup`) created, and
        return an open session bound to it.

        :returns: ``(engine, session)`` -- the test owns cleanup.
    """
    engine = sa.create_engine("sqlite://")
    PychestratePhase1Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    session = factory()
    rtnval = (engine, session)
    return rtnval


def test_ensure_token_provisioned_inserts_singleton_row():
    """
    **Feature: initial-setup-wizard**
    **Property: ensure_token_provisioned inserts exactly one row,
    keyed by SINGLETON_KEY_VALUE, when called against an empty
    database.**
    """
    engine, session = _build_session()
    runtime_dir = tempfile.mkdtemp()
    try:
        manager = InitialSetupManager(
            db_session=session, runtime_dir=runtime_dir
        )
        row = manager.ensure_token_provisioned()
        session.commit()

        testbase.assert_true(row is not None)
        testbase.assert_equal(row.singleton_key, SINGLETON_KEY_VALUE)
        testbase.assert_equal(row.completed_at, None)
        testbase.assert_equal(row.token_path, os.path.join(
            runtime_dir, DEFAULT_TOKEN_FILENAME
        ))

        rows = session.query(InitialSetup).all()
        testbase.assert_equal(len(rows), 1)
    finally:
        session.close()
        engine.dispose()
        _cleanup_runtime_dir(runtime_dir=runtime_dir)
    return


def test_ensure_token_provisioned_is_idempotent():
    """
    **Feature: initial-setup-wizard**
    **Property: Calling ensure_token_provisioned a second time on a
    pending row is a no-op -- returns the existing row, does not
    rewrite the token file, does not insert a second row.**
    """
    engine, session = _build_session()
    runtime_dir = tempfile.mkdtemp()
    try:
        manager = InitialSetupManager(
            db_session=session, runtime_dir=runtime_dir
        )
        row_first = manager.ensure_token_provisioned()
        token_path = manager.token_path
        first_hash_bytes = bytes(row_first.token_hash)
        first_mtime = os.stat(token_path).st_mtime_ns

        row_second = manager.ensure_token_provisioned()

        testbase.assert_equal(row_second.setup_id, row_first.setup_id)
        testbase.assert_equal(bytes(row_second.token_hash), first_hash_bytes)
        testbase.assert_equal(
            os.stat(token_path).st_mtime_ns, first_mtime
        )

        rows = session.query(InitialSetup).all()
        testbase.assert_equal(len(rows), 1)
    finally:
        session.close()
        engine.dispose()
        _cleanup_runtime_dir(runtime_dir=runtime_dir)
    return


def test_token_file_is_mode_0600():
    """
    **Feature: initial-setup-wizard**
    **Property: The on-disk token file is created with mode 0600
    (readable only by the service user) regardless of the process
    umask.**
    """
    engine, session = _build_session()
    runtime_dir = tempfile.mkdtemp()
    prior_umask = os.umask(0o000)
    try:
        manager = InitialSetupManager(
            db_session=session, runtime_dir=runtime_dir
        )
        manager.ensure_token_provisioned()

        mode_bits = stat.S_IMODE(os.stat(manager.token_path).st_mode)
        testbase.assert_equal(mode_bits, TOKEN_FILE_MODE)
    finally:
        os.umask(prior_umask)
        session.close()
        engine.dispose()
        _cleanup_runtime_dir(runtime_dir=runtime_dir)
    return


def test_verify_token_accepts_provisioned_token_and_rejects_wrong():
    """
    **Feature: initial-setup-wizard**
    **Property: verify_token returns True for the cleartext token
    written to disk and False for any other string (timing-safe
    sha256 compare).**
    """
    engine, session = _build_session()
    runtime_dir = tempfile.mkdtemp()
    try:
        manager = InitialSetupManager(
            db_session=session, runtime_dir=runtime_dir
        )
        manager.ensure_token_provisioned()

        with open(manager.token_path, "r", encoding="utf-8") as handle:
            real_token = handle.read()

        testbase.assert_equal(
            manager.verify_token(plaintext=real_token), True
        )
        testbase.assert_equal(
            manager.verify_token(plaintext="totally-wrong-token"),
            False,
        )
        testbase.assert_equal(
            manager.verify_token(plaintext=""),
            False,
        )
    finally:
        session.close()
        engine.dispose()
        _cleanup_runtime_dir(runtime_dir=runtime_dir)
    return


def test_mark_complete_stamps_row_and_removes_token_file():
    """
    **Feature: initial-setup-wizard**
    **Property: mark_complete stamps completed_at, records the
    user_id, and unlinks the on-disk token file.**
    """
    engine, session = _build_session()
    runtime_dir = tempfile.mkdtemp()
    try:
        manager = InitialSetupManager(
            db_session=session, runtime_dir=runtime_dir
        )
        manager.ensure_token_provisioned()
        token_path = manager.token_path
        testbase.assert_equal(os.path.exists(token_path), True)

        admin_id = uuid.uuid4()
        manager.mark_complete(completed_by_user_id=admin_id)
        session.commit()

        row = manager.get_state()
        testbase.assert_true(row.completed_at is not None)
        testbase.assert_equal(row.completed_by_user_id, admin_id)
        testbase.assert_equal(os.path.exists(token_path), False)
        testbase.assert_equal(manager.is_complete(), True)
    finally:
        session.close()
        engine.dispose()
        _cleanup_runtime_dir(runtime_dir=runtime_dir)
    return


def test_mark_complete_refuses_re_entry():
    """
    **Feature: initial-setup-wizard**
    **Property: A second mark_complete on the same row raises
    SetupAlreadyCompleteError -- setup completion is one-way.**
    """
    engine, session = _build_session()
    runtime_dir = tempfile.mkdtemp()
    try:
        manager = InitialSetupManager(
            db_session=session, runtime_dir=runtime_dir
        )
        manager.ensure_token_provisioned()
        first_admin = uuid.uuid4()
        manager.mark_complete(completed_by_user_id=first_admin)
        session.commit()

        raised = False
        try:
            manager.mark_complete(completed_by_user_id=uuid.uuid4())
        except SetupAlreadyCompleteError:
            raised = True
        testbase.assert_equal(raised, True)
    finally:
        session.close()
        engine.dispose()
        _cleanup_runtime_dir(runtime_dir=runtime_dir)
    return


def test_verify_token_after_completion_raises():
    """
    **Feature: initial-setup-wizard**
    **Property: verify_token raises SetupAlreadyCompleteError once
    the wizard is finished -- callers should not be invoking verify
    on a completed wizard.**
    """
    engine, session = _build_session()
    runtime_dir = tempfile.mkdtemp()
    try:
        manager = InitialSetupManager(
            db_session=session, runtime_dir=runtime_dir
        )
        manager.ensure_token_provisioned()
        manager.mark_complete(completed_by_user_id=uuid.uuid4())
        session.commit()

        raised = False
        try:
            manager.verify_token(plaintext="anything")
        except SetupAlreadyCompleteError:
            raised = True
        testbase.assert_equal(raised, True)
    finally:
        session.close()
        engine.dispose()
        _cleanup_runtime_dir(runtime_dir=runtime_dir)
    return


def test_verify_token_before_provisioning_raises():
    """
    **Feature: initial-setup-wizard**
    **Property: verify_token raises SetupNotInitializedError when
    the singleton row has not been provisioned yet -- a programming
    error in the runtime bootstrap.**
    """
    engine, session = _build_session()
    runtime_dir = tempfile.mkdtemp()
    try:
        manager = InitialSetupManager(
            db_session=session, runtime_dir=runtime_dir
        )

        raised = False
        try:
            manager.verify_token(plaintext="anything")
        except SetupNotInitializedError:
            raised = True
        testbase.assert_equal(raised, True)
    finally:
        session.close()
        engine.dispose()
        _cleanup_runtime_dir(runtime_dir=runtime_dir)
    return


def test_lost_token_file_is_regenerated_before_completion():
    """
    **Feature: initial-setup-wizard**
    **Property: If the token file is deleted while setup is still
    pending, ensure_token_provisioned regenerates it and updates
    the stored hash so the operator can recover without a manual
    DB edit.**
    """
    engine, session = _build_session()
    runtime_dir = tempfile.mkdtemp()
    try:
        manager = InitialSetupManager(
            db_session=session, runtime_dir=runtime_dir
        )
        manager.ensure_token_provisioned()
        token_path = manager.token_path
        original_hash = bytes(manager.get_state().token_hash)

        os.unlink(token_path)
        testbase.assert_equal(os.path.exists(token_path), False)

        manager.ensure_token_provisioned()
        session.commit()

        testbase.assert_equal(os.path.exists(token_path), True)
        new_hash = bytes(manager.get_state().token_hash)
        # Brand new random token, so the hash MUST differ.
        testbase.assert_not_equal(new_hash, original_hash)
    finally:
        session.close()
        engine.dispose()
        _cleanup_runtime_dir(runtime_dir=runtime_dir)
    return


def _cleanup_runtime_dir(*, runtime_dir: str) -> None:
    """
        Best-effort cleanup of a temp runtime dir created by a
        test. Removes the token file (if still present) and the
        directory itself.

        :param runtime_dir: Directory to remove.

        :returns: None.
    """
    token_path = os.path.join(runtime_dir, DEFAULT_TOKEN_FILENAME)
    if os.path.exists(token_path):
        try:
            os.unlink(token_path)
        except OSError:
            pass
    try:
        os.rmdir(runtime_dir)
    except OSError:
        pass
    return
