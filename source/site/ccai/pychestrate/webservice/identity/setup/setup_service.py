"""
.. module:: identity.setup.setup_service
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Runtime-bootstrap glue for the initial-setup wizard.

.. moduleauthor:: Code Craft AI LLC

Two responsibilities, kept separate from :class:`InitialSetupManager`
so the manager stays a pure DB / filesystem object:

* :func:`bootstrap_setup_state` -- called once from the runtime
  bootstrap. Reads :data:`ENV_RUNTIME_DIR`, creates the directory
  (mode 0700) when missing, opens a short-lived session, and calls
  :meth:`InitialSetupManager.ensure_token_provisioned`. Logs the
  token path so operators see it in journald immediately.

* :func:`is_setup_complete` -- per-request predicate the gate
  middleware reads. Maintains a process-level fast-path flag so the
  hot path is one boolean read once the wizard is done. While the
  flag is False, the function falls back to a DB query (so a
  completion in another worker becomes visible the next time the
  flag is consulted from this worker). The flag is one-way: once
  True, it stays True for the life of the process.

The fast-path flag races benignly across gunicorn workers. Worst
case after completion: a worker still holding the stale ``False``
issues one more DB query before flipping its flag. The query
returns ``True`` and the worker is then on the fast path forever.
No incorrect routing decisions.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import logging
import os
import threading

from typing import Callable, Optional

from sqlalchemy.orm import Session as DbSession

from ccai.errors.exceptions import ConfigurationError

from ccai.pychestrate.webservice.identity.setup.setup_manager import (
    DEFAULT_TOKEN_FILENAME,
    InitialSetupManager,
)


SessionFactory = Callable[[], DbSession]


_module_logger = logging.getLogger(__name__)


# Operator-facing env var. Operators set this in the systemd unit's
# ``Environment=`` block; ``dev-up`` defaults it to a per-checkout
# directory under ``.cache/runtime``.
#
# Resolution now goes through the persona presence directory --
# whatever was passed to ``establish_webapp_persona(presence_dir=...)``
# at process boot. The entrypoint resolves that value from CLI flag
# / ``PYCHESTRATE_PRESENCE_DIR`` env var / pychestrate default.
# This constant is preserved for backward compatibility of imports
# only; the manager-construction path reads from
# ``PersonaVariables.AM_PRESENCE_DIR``.
ENV_RUNTIME_DIR: str = "PYCHESTRATE_PRESENCE_DIR"


# Mode applied to the runtime directory when the bootstrap creates
# it. 0700 keeps the token file (and any future runtime state) out
# of reach of other accounts on the box.
RUNTIME_DIR_MODE: int = 0o700


# Fast-path flag. Once True, :func:`is_setup_complete` returns True
# without touching the database. Guarded by ``_completion_lock`` so
# the flip is visible across threads in the same process. Workers
# in different processes maintain independent flags, which is fine
# (see module docstring -- worst case is one extra DB query per
# worker-after-completion).
_setup_complete_flag: bool = False
_completion_lock: threading.Lock = threading.Lock()


def _read_persona_presence_dir() -> str:
    """
        Resolve the presence directory from the persona singleton.

        The presence directory is fixed at
        ``establish_webapp_persona`` time (see
        :mod:`pychestrate_presence` for the resolution chain --
        CLI flag, ``PYCHESTRATE_PRESENCE_DIR`` env var,
        pychestrate default ``~/pychestrate``). This function
        reads through the canonical this_app accessor so any
        downstream override
        (``ThisApplicationSingleton().override_variable_value(...)``)
        is honored.

        :returns: Absolute path string.
        :raises: SemanticError when the persona singleton has not
                 been established yet -- the entrypoint must have
                 called ``establish_webapp_persona`` before the
                 wizard bootstrap runs.
    """
    from ccai.thisapp.personavariables import PersonaVariables

    raw = PersonaVariables.AM_PRESENCE_DIR
    expanded = os.path.expanduser(raw)
    rtnval = os.path.abspath(expanded)
    return rtnval


def _ensure_runtime_dir(*, runtime_dir: str) -> None:
    """
        Create ``runtime_dir`` mode 0700 when missing. No-op when
        the directory already exists. Refuses to create a path
        whose parent does not exist -- an operator explicitly
        chose ``/var/lib/pychestrate``; we do not invent
        ``/var/lib`` for them.

        :param runtime_dir: Absolute path to ensure.

        :returns: None.
        :raises: ConfigurationError when the parent directory is
                 missing or the path exists but is not a directory.
    """
    if os.path.exists(runtime_dir) is True:
        if os.path.isdir(runtime_dir) is False:
            err_msg_lines = [
                "{} points at a non-directory.".format(ENV_RUNTIME_DIR)
            ]
            err_msg_lines.append("PATH: {}".format(runtime_dir))
            err_msg = os.linesep.join(err_msg_lines)
            raise ConfigurationError(err_msg)
        return

    parent_dir = os.path.dirname(runtime_dir)
    if len(parent_dir) > 0 and os.path.isdir(parent_dir) is False:
        err_msg_lines = [
            "Parent of {} does not exist; refusing to create.".format(
                ENV_RUNTIME_DIR
            )
        ]
        err_msg_lines.append("RUNTIME_DIR: {}".format(runtime_dir))
        err_msg_lines.append("PARENT: {}".format(parent_dir))
        err_msg_lines.append(
            "Create the parent (or pick an existing parent) and re-run."
        )
        err_msg = os.linesep.join(err_msg_lines)
        raise ConfigurationError(err_msg)

    os.makedirs(runtime_dir, mode=RUNTIME_DIR_MODE, exist_ok=True)
    # ``os.makedirs`` honors the umask, which can strip our 0700
    # request. Reapply the mode explicitly so the resulting directory
    # is always exactly 0700.
    os.chmod(runtime_dir, RUNTIME_DIR_MODE)
    _module_logger.info(
        "pychestrate.setup.runtime_dir_created path=%s mode=0o700",
        runtime_dir,
    )
    return


def bootstrap_setup_state(*, session_factory: SessionFactory) -> str:
    """
        Provision the initial-setup state at runtime-bootstrap time.

        Reads :data:`ENV_RUNTIME_DIR`, ensures the directory exists
        with mode 0700, opens a short-lived session via
        ``session_factory``, runs
        :meth:`InitialSetupManager.ensure_token_provisioned`, and
        commits. Returns the absolute path of the token file so the
        caller can log it.

        Idempotent. Safe to call on every boot regardless of whether
        the wizard has already completed.

        :param session_factory: Zero-arg callable that returns a
                                fresh SQLAlchemy session.

        :returns: Absolute path of the token file (whether newly
                  written or pre-existing).
        :raises: ConfigurationError on env / filesystem misconfig.
    """
    runtime_dir = _read_persona_presence_dir()
    _ensure_runtime_dir(runtime_dir=runtime_dir)

    db_session = session_factory()
    try:
        manager = InitialSetupManager(
            db_session=db_session,
            runtime_dir=runtime_dir,
        )
        row = manager.ensure_token_provisioned()
        token_path = manager.token_path
        if row.completed_at is None:
            _module_logger.info(
                "pychestrate.setup.pending token_path=%s",
                token_path,
            )
            # Seed the fast-path flag from the DB. We know it is
            # False at this point but be explicit -- a re-bootstrap
            # after completion (e.g. via ``systemctl restart``)
            # should land on True without one extra request hitting
            # the DB.
            _set_complete_flag(value=False)
        else:
            _module_logger.info(
                "pychestrate.setup.already_complete setup_id=%s",
                str(row.setup_id),
            )
            _set_complete_flag(value=True)
        db_session.commit()
    except BaseException:
        db_session.rollback()
        raise
    finally:
        db_session.close()

    rtnval = token_path
    return rtnval


def mark_setup_complete_for_test_admin(
        *,
        session_factory: SessionFactory,
        completed_by_user_id: str
    ) -> None:
    """
        Provision the initial-setup row if absent and stamp it complete so
        the setup-gate middleware lets ``/login`` and the rest of the app
        through. Used ONLY by the runtime ``PYCHESTRATE_TEST_MODE`` hook
        after it seeds the test admin -- an injected credential is useless
        if the wizard gate still redirects every request to
        ``/setup/unlock``.

        Idempotent: when the row is already complete it only re-flips the
        process fast-path flag.

        :param session_factory: Zero-arg callable that returns a fresh
                                SQLAlchemy session.
        :param completed_by_user_id: ``identity_users.user_id`` of the
                                     seeded admin (UUID string).

        :returns: None.
        :raises: ConfigurationError on env / filesystem misconfig.
    """
    import uuid as _uuid

    runtime_dir = _read_persona_presence_dir()
    _ensure_runtime_dir(runtime_dir=runtime_dir)

    db_session = session_factory()
    try:
        manager = InitialSetupManager(
            db_session=db_session,
            runtime_dir=runtime_dir,
        )
        manager.ensure_token_provisioned()
        if manager.is_complete() is False:
            completed_uuid = _uuid.UUID(completed_by_user_id)
            manager.mark_complete(completed_by_user_id=completed_uuid)
            _module_logger.info(
                "pychestrate.setup.completed_by_test_mode completed_by=%s",
                completed_by_user_id,
            )
        db_session.commit()
    except BaseException:
        db_session.rollback()
        raise
    finally:
        db_session.close()

    _set_complete_flag(value=True)
    return


def _set_complete_flag(*, value: bool) -> None:
    """
        Update the process-level fast-path flag under the lock.

        :param value: New flag value.

        :returns: None.
    """
    global _setup_complete_flag
    with _completion_lock:
        _setup_complete_flag = value
    return


def mark_setup_complete_in_process_cache() -> None:
    """
        Flip the in-process fast-path flag to True. Called by the
        setup blueprint immediately after a successful admin
        creation so subsequent requests on this worker skip the DB
        check entirely.

        :returns: None.
    """
    _set_complete_flag(value=True)
    return


def reset_complete_flag_for_testing() -> None:
    """
        Reset the process-level fast-path flag to False. Tests use
        this between cases so a previous test's completion doesn't
        leak into the next test.

        Production code MUST NOT call this -- there is no operator
        path that reverses setup completion.

        :returns: None.
    """
    _set_complete_flag(value=False)
    return


def is_setup_complete(*, session_factory: SessionFactory) -> bool:
    """
        Return whether the initial-setup wizard has been finished.
        Cheap fast path on the True branch (flag read only). On the
        False branch, opens a short-lived session and consults the
        DB, then promotes the flag to True if the DB says so.

        Returning False from this function while the DB row is
        missing is correct -- the gate middleware should redirect to
        the unlock page in that case (the bootstrap should have
        provisioned the row, so a missing row indicates a partially
        booted process).

        :param session_factory: Zero-arg callable returning a fresh
                                SQLAlchemy session.

        :returns: True iff setup has completed.
    """
    if _setup_complete_flag is True:
        return True

    db_session = session_factory()
    try:
        manager = InitialSetupManager(
            db_session=db_session,
            # The runtime dir is irrelevant for read-only ops, but
            # the manager constructor demands a non-empty value.
            # Use a placeholder; we never call the file-writing
            # methods on this short-lived instance.
            runtime_dir=_read_persona_presence_dir(),
        )
        complete = manager.is_complete()
    finally:
        db_session.close()

    if complete is True:
        _set_complete_flag(value=True)
    rtnval = complete
    return rtnval


def create_initial_admin(
        *,
        session_factory: SessionFactory,
        login_name: str,
        primary_email: str,
        password: str,
        display_name: str,
    ) -> str:
    """
        Seed the first administrator. Mirrors the e2e harness's
        ``_seed_user_pair`` exactly: inserts a modern
        :class:`IdentityUser`, an :class:`AuthLocalCredentials` row
        carrying the password hash, and a legacy
        :class:`core.orm.User` row with ``roles="admin"`` so the
        legacy check_permission path resolves to admin until the
        RBAC cut-over lands.

        Refuses to run when an :class:`IdentityUser` with the
        requested ``login_name`` already exists, OR when ANY user
        already exists in the modern table -- the latter guard
        is what keeps the wizard from being abused as a back door
        to mint a second admin once the first deploy is up. The
        gate-middleware + the ``completed_at`` flag are the primary
        defences; this is belt-and-suspenders.

        :param session_factory: Zero-arg session factory.
        :param login_name: Desired admin login.
        :param primary_email: Desired admin email.
        :param password: Cleartext password (hashed before storage
                         via ``local_flow.hash_password``).
        :param display_name: Desired admin display name.

        :returns: Newly created user id (UUID string).
        :raises: ConfigurationError on validation failure or when
                 a user already exists.
    """
    # Lazy imports to keep this module importable in unit tests
    # that don't run the full Phase-1 stack.
    import uuid as _uuid

    from ccai.pychestrate.core.orm import User as _LegacyUser
    from ccai.pychestrate.webservice.identity.users.models import (
        IdentityUser,
        UserStatus,
    )
    from ccai.pychestrate.webservice.security.auth import local_flow
    from ccai.pychestrate.webservice.security.auth.models import (
        AuthLocalCredentials,
    )

    if login_name is None or len(login_name) == 0:
        raise ConfigurationError(
            "create_initial_admin requires a non-empty login_name"
        )
    if primary_email is None or len(primary_email) == 0:
        raise ConfigurationError(
            "create_initial_admin requires a non-empty primary_email"
        )
    if password is None or len(password) == 0:
        raise ConfigurationError(
            "create_initial_admin requires a non-empty password"
        )

    db_session = session_factory()
    try:
        existing_count = db_session.query(IdentityUser).count()
        if existing_count > 0:
            raise ConfigurationError(
                "create_initial_admin refused: identity_users is not empty"
            )

        admin_user_id = _uuid.uuid4()

        # Modern half.
        modern_user = IdentityUser(
            user_id=admin_user_id,
            login_name=login_name,
            primary_email=primary_email,
            display_name=display_name,
            status=UserStatus.ACTIVE,
            provisioning_source="local",
            external_id=None,
            timezone="UTC",
        )
        db_session.add(modern_user)
        db_session.flush()

        encoded_hash, algo_params = local_flow.hash_password(
            password=password
        )
        credentials = AuthLocalCredentials(
            user_id=admin_user_id,
            argon2id_hash=encoded_hash,
            algo_params=algo_params,
        )
        db_session.add(credentials)

        # Legacy half: ``check_permission`` still reads the legacy
        # ``user.roles`` CSV -> ``system_roles`` -> ``permissions``
        # chain. ``roles="admin"`` mirrors the e2e harness's
        # ``ensure_seeded_admin`` exactly.
        #
        # The legacy ``user`` table comes from migrations 001-003
        # (``PychestrateModelBase``). When the operator runs with
        # ``PYCHESTRATE_AUTO_CREATE_SCHEMA=true`` (dev-up only --
        # production uses alembic), only the modern Phase-1 tables
        # are created and the legacy ``user`` table is absent. We
        # try the insert and fall back to a savepoint rollback so
        # the modern half (which IS the auth source of truth) still
        # commits cleanly.
        from sqlalchemy.exc import OperationalError as _OpError

        legacy_user = _LegacyUser(
            id=admin_user_id,
            first_name="",
            last_name="",
            display_name=display_name,
            email=primary_email,
            login=login_name,
            ownertag="initial-setup",
            status="active",
            roles="admin",
            authtype="internal",
        )
        legacy_savepoint = db_session.begin_nested()
        try:
            db_session.add(legacy_user)
            db_session.flush()
            legacy_savepoint.commit()
        except _OpError as op_exc:
            legacy_savepoint.rollback()
            _module_logger.warning(
                "pychestrate.setup.legacy_user_skipped reason=%s",
                str(op_exc).split(os.linesep)[0],
            )

        # Modern RBAC half: seed the ``system-admin`` role row
        # and a ``RbacRoleBinding`` linking this admin to it at
        # SYSTEM scope. The legacy ``user.roles="admin"`` CSV
        # above is for the legacy ``check_permission`` path; the
        # modern ``rbac_evaluator.check_permission`` joins
        # ``rbac_role_bindings`` -> ``rbac_roles`` and looks the
        # grants up in the in-memory catalog
        # (:class:`SystemAdminRole`). Without this binding, the
        # site shell's ``/api/v1/me/permissions`` returns an
        # empty array for the seeded admin and the Admin
        # sidebar group does not render.
        from ccai.pychestrate.webservice.security.rbac.seeding import (
            ensure_system_admin_binding_for_user,
        )
        ensure_system_admin_binding_for_user(
            db_session=db_session,
            user_id=str(admin_user_id),
            actor_user_id=None,
        )

        db_session.commit()
        _module_logger.info(
            "pychestrate.setup.initial_admin_created user_id=%s login=%s",
            str(admin_user_id),
            login_name,
        )
        rtnval = str(admin_user_id)
        return rtnval
    except BaseException:
        db_session.rollback()
        raise
    finally:
        db_session.close()


__all__ = [
    "DEFAULT_TOKEN_FILENAME",
    "ENV_RUNTIME_DIR",
    "RUNTIME_DIR_MODE",
    "bootstrap_setup_state",
    "create_initial_admin",
    "is_setup_complete",
    "mark_setup_complete_for_test_admin",
    "mark_setup_complete_in_process_cache",
    "reset_complete_flag_for_testing",
]
