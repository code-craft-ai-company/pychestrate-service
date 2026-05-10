"""
.. module:: identity.setup.setup_service
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Runtime-bootstrap glue for the initial-setup wizard.

.. moduleauthor:: Automation Mojo LLC

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

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import logging
import os
import threading

from typing import Callable, Optional

from sqlalchemy.orm import Session as DbSession

from automojo.errors.exceptions import ConfigurationError

from automojo.pychestrate.webservice.identity.setup.setup_manager import (
    DEFAULT_TOKEN_FILENAME,
    InitialSetupManager,
)


SessionFactory = Callable[[], DbSession]


_module_logger = logging.getLogger(__name__)


# Operator-facing env var. Operators set this in the systemd unit's
# ``Environment=`` block; ``dev-up`` defaults it to a per-checkout
# directory under ``.cache/runtime``.
ENV_RUNTIME_DIR: str = "PYCHESTRATE_RUNTIME_DIR"


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


def _read_env_runtime_dir() -> str:
    """
        Resolve :data:`ENV_RUNTIME_DIR`. Refuses an unset / empty
        value -- the deployment must be explicit about where runtime
        state lives.

        :returns: Absolute path string.
        :raises: ConfigurationError when the env var is unset.
    """
    raw = os.environ.get(ENV_RUNTIME_DIR, None)
    if raw is None or len(raw) == 0:
        err_msg_lines = [
            "{} is required to bootstrap the initial-setup wizard.".format(
                ENV_RUNTIME_DIR
            )
        ]
        err_msg_lines.append(
            "Set it in the systemd unit (production) or in dev-up"
            " (development) to the directory that should hold runtime"
            " state."
        )
        err_msg_lines.append(
            "PRODUCTION DEFAULT: /var/lib/pychestrate"
        )
        err_msg = os.linesep.join(err_msg_lines)
        raise ConfigurationError(err_msg)

    rtnval = os.path.abspath(raw)
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
    runtime_dir = _read_env_runtime_dir()
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
            runtime_dir=_runtime_dir_or_placeholder(),
        )
        complete = manager.is_complete()
    finally:
        db_session.close()

    if complete is True:
        _set_complete_flag(value=True)
    rtnval = complete
    return rtnval


def _runtime_dir_or_placeholder() -> str:
    """
        Read :data:`ENV_RUNTIME_DIR` if set; otherwise return a
        harmless placeholder. Used by the read-only path of
        :func:`is_setup_complete` -- the manager constructor demands
        a non-empty runtime_dir, but no file operation is performed
        on the instance built there.

        :returns: A path string, never empty.
    """
    raw = os.environ.get(ENV_RUNTIME_DIR, None)
    if raw is None or len(raw) == 0:
        return "/tmp"
    rtnval = raw
    return rtnval


__all__ = [
    "DEFAULT_TOKEN_FILENAME",
    "ENV_RUNTIME_DIR",
    "RUNTIME_DIR_MODE",
    "bootstrap_setup_state",
    "is_setup_complete",
    "mark_setup_complete_in_process_cache",
    "reset_complete_flag_for_testing",
]
