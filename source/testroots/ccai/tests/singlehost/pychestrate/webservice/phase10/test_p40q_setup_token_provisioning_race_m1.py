"""
.. module:: test_p40q_setup_token_provisioning_race_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Several workers provisioning the initial-setup token at once leave the token file and the stored hash in step.

.. moduleauthor:: Code Craft AI LLC

On the first start of a new deployment every gunicorn worker runs ``ensure_token_provisioned`` against an empty database at the
same moment. Each used to generate its own token and write the token file before inserting the singleton row; the worker that lost
the insert crashed with ``uq_system_initial_setup_singleton`` after having overwritten the winner's file, so the right token was
rejected by the setup wizard with a 401 (found by the runbook smoke test in CI, 2026-10-21, which passed or failed with the timing).

These tests give two managers independent connections to one SQLite file and recreate the interleaving: the second manager looks
for the row before the first has stored it.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import tempfile

import sqlalchemy as sa

from sqlalchemy.orm import sessionmaker

from ccai import testbase

from ccai.pychestrate.webservice.identity.setup import setup_manager as setup_manager_module
from ccai.pychestrate.webservice.identity.setup.models import InitialSetup
from ccai.pychestrate.webservice.identity.setup.setup_manager import (
    InitialSetupManager,
    TOKEN_FILE_MODE,
)
from ccai.pychestrate.webservice.persistence.schema import PychestratePhase1Base

# Registers the identity-users models so create_all can resolve the completed_by_user_id foreign key.
from ccai.pychestrate.webservice.identity.users import models as _identity_users_models  # noqa: F401


def _two_workers():
    """
        A SQLite file, a runtime directory, and two sessions on separate connections to the file (two workers).

        :returns: ``(engine, session_a, session_b, runtime_dir)``.
    """
    directory = tempfile.mkdtemp()
    engine = sa.create_engine("sqlite:///" + os.path.join(directory, "setup.db"))
    PychestratePhase1Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    runtime_dir = os.path.join(directory, "run")
    os.makedirs(runtime_dir, mode=0o700)
    rtnval = (engine, factory(), factory(), runtime_dir)
    return rtnval


def _read_token(manager: InitialSetupManager) -> str:
    with open(manager.token_path, encoding="utf-8") as handle:
        rtnval = handle.read().strip()
    return rtnval


def _look_for_the_row_only_after_the_other_worker_stored_it(manager: InitialSetupManager) -> None:
    """
        Make ``manager``'s first ``get_state`` report "no row" even though another worker has stored one since: the gap between the
        existence check and the insert, which is where the workers collide.
    """
    original = manager.get_state
    calls = {"count": 0}

    def get_state():
        calls["count"] += 1
        if calls["count"] == 1:
            return None
        return original()

    manager.get_state = get_state
    return


def test_a_worker_that_loses_the_insert_race_leaves_the_winners_token_alone():
    """
    **Feature: initial-setup-wizard**
    **Property: when a second worker checks for the setup row before the first has stored it, the second adopts the first's row without an
    error and without touching the token file, so the file's token is still the one the stored hash belongs to.**
    """
    engine, session_a, session_b, runtime_dir = _two_workers()
    try:
        winner = InitialSetupManager(db_session=session_a, runtime_dir=runtime_dir)
        winner.ensure_token_provisioned()
        session_a.commit()
        winners_token = _read_token(winner)

        loser = InitialSetupManager(db_session=session_b, runtime_dir=runtime_dir)
        _look_for_the_row_only_after_the_other_worker_stored_it(loser)
        row = loser.ensure_token_provisioned()
        session_b.commit()

        testbase.assert_equal(
            (_read_token(loser) == winners_token, loser.verify_token(plaintext=winners_token), row.singleton_key, session_b.query(InitialSetup).count()),
            (True, True, winner.get_state().singleton_key, 1),
        )
    finally:
        session_a.close()
        session_b.close()
        engine.dispose()
    return


def test_the_token_file_is_written_only_after_the_row_is_stored():
    """
    **Feature: initial-setup-wizard**
    **Property: when a worker writes the token file, its row is already inserted (flushed) in the open transaction, so a worker whose insert
    fails never reaches the file.**
    """
    engine, session, _unused, runtime_dir = _two_workers()
    seen = []
    original = setup_manager_module._atomic_write_token_file

    def recording_write(*, path, plaintext):
        seen.append(session.execute(sa.select(sa.func.count()).select_from(InitialSetup)).scalar())
        original(path=path, plaintext=plaintext)
        return

    setup_manager_module._atomic_write_token_file = recording_write
    try:
        InitialSetupManager(db_session=session, runtime_dir=runtime_dir).ensure_token_provisioned()
        session.commit()
    finally:
        setup_manager_module._atomic_write_token_file = original
        session.close()
        _unused.close()
        engine.dispose()
    testbase.assert_equal(seen, [1])
    return


def test_a_lost_token_file_is_regenerated_with_its_hash_stored_first():
    """
    **Feature: initial-setup-wizard**
    **Property: when the token file is lost and regenerated, the new hash is already stored (flushed) at the moment the file is written, so
    two workers regenerating together end with the last file and the last hash from the same worker.**
    """
    engine, session, _unused, runtime_dir = _two_workers()
    manager = InitialSetupManager(db_session=session, runtime_dir=runtime_dir)
    manager.ensure_token_provisioned()
    session.commit()
    os.remove(manager.token_path)

    stored = []
    original = setup_manager_module._atomic_write_token_file

    def recording_write(*, path, plaintext):
        stored.append(
            (session.execute(sa.select(InitialSetup.token_hash)).scalar(), setup_manager_module._hash_token_bytes(plaintext=plaintext))
        )
        original(path=path, plaintext=plaintext)
        return

    setup_manager_module._atomic_write_token_file = recording_write
    try:
        manager.ensure_token_provisioned()
        session.commit()
    finally:
        setup_manager_module._atomic_write_token_file = original
        session.close()
        _unused.close()
        engine.dispose()
    testbase.assert_equal([hash_in_database == hash_of_file for hash_in_database, hash_of_file in stored], [True])
    return


def test_the_token_file_keeps_its_owner_only_mode_after_a_race():
    """
    **Feature: initial-setup-wizard**
    **Property: the token file a worker adopts after losing the race is still mode 0600.**
    """
    engine, session_a, session_b, runtime_dir = _two_workers()
    try:
        winner = InitialSetupManager(db_session=session_a, runtime_dir=runtime_dir)
        winner.ensure_token_provisioned()
        session_a.commit()
        loser = InitialSetupManager(db_session=session_b, runtime_dir=runtime_dir)
        _look_for_the_row_only_after_the_other_worker_stored_it(loser)
        loser.ensure_token_provisioned()
        session_b.commit()
        mode = os.stat(loser.token_path).st_mode & 0o777
    finally:
        session_a.close()
        session_b.close()
        engine.dispose()
    testbase.assert_equal(mode, TOKEN_FILE_MODE)
    return
