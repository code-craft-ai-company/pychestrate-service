"""
.. module:: identity.setup.setup_manager
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Pure-Python lifecycle manager for the initial-setup
               singleton row.

.. moduleauthor:: Automation Mojo LLC

The manager owns the database side of the first-run wizard.

* :meth:`InitialSetupManager.ensure_token_provisioned` is idempotent
  -- on first call it generates the token, hashes it, writes the
  cleartext to disk, and inserts the singleton row. On subsequent
  calls it is a no-op that returns the existing row.
* :meth:`is_complete` is the predicate the gate middleware reads on
  every request.
* :meth:`verify_token` performs a timing-safe sha256 compare against
  the stored hash.
* :meth:`mark_complete` stamps ``completed_at``, records the admin
  user id that finished setup, and deletes the token file. It
  refuses re-entry; setup completion is one-way.

The manager does not touch webworks request state. It is a
plain object exercised in unit tests against an in-memory SQLite
session.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import base64
import hashlib
import hmac
import logging
import os
import secrets
import uuid

from datetime import datetime, timezone
from typing import Callable, Optional

from sqlalchemy.orm import Session as DbSession

from automojo.errors.exceptions import ConfigurationError

from automojo.pychestrate.webservice.identity.setup.exceptions import (
    InvalidSetupTokenError,
    SetupAlreadyCompleteError,
    SetupNotInitializedError,
)
from automojo.pychestrate.webservice.identity.setup.models import (
    INITIAL_TOKEN_BYTE_LENGTH,
    InitialSetup,
    SINGLETON_KEY_VALUE,
)


_module_logger = logging.getLogger(__name__)


# Default leaf filename written under the configured runtime
# directory. Mirrors the Jenkins ``initialAdminPassword`` convention.
DEFAULT_TOKEN_FILENAME: str = "initial-admin-token"


# Mode used for the on-disk token file. 0600 keeps it readable only
# by the service user (and root). Other accounts on the box cannot
# read it.
TOKEN_FILE_MODE: int = 0o600


def _default_clock() -> datetime:
    """
        Return the current UTC time. Pulled out so the module-level
        default is a real ``def`` (importable) rather than an inline
        lambda; tests pass a fixed-time stub instead.

        :returns: Current UTC ``datetime``.
    """
    rtnval = datetime.now(timezone.utc)
    return rtnval


def _hash_token_bytes(*, plaintext: str) -> bytes:
    """
        Return the sha256 of a plaintext token, as raw 32 bytes.

        :param plaintext: Token string as submitted by the operator.

        :returns: 32-byte sha256 digest.
    """
    digest = hashlib.sha256(plaintext.encode("utf-8")).digest()
    rtnval = digest
    return rtnval


def _generate_token_plaintext() -> str:
    """
        Generate a high-entropy initial-admin token. Returns the
        url-safe base64 encoding of :data:`INITIAL_TOKEN_BYTE_LENGTH`
        random bytes; the encoded string is what the operator pastes
        into the unlock form.

        :returns: Token string suitable for paste-into-form use.
    """
    raw = secrets.token_bytes(INITIAL_TOKEN_BYTE_LENGTH)
    encoded = base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
    rtnval = encoded
    return rtnval


def _atomic_write_token_file(*, path: str, plaintext: str) -> None:
    """
        Write the cleartext token to ``path`` with mode 0600. The
        write is atomic: we write to a sibling ``.tmp`` file first
        and then ``os.rename`` into place so a partially written
        token is never visible to a reader.

        :param path: Absolute path of the destination file.
        :param plaintext: Token bytes to write (one line, no newline).

        :returns: None.
        :raises: ConfigurationError when the parent directory does
                 not exist or is not writable.
    """
    parent_dir = os.path.dirname(path)
    if len(parent_dir) > 0 and os.path.isdir(parent_dir) is False:
        err_msg_lines = ["Initial-setup runtime directory does not exist."]
        err_msg_lines.append("PATH: {}".format(parent_dir))
        err_msg_lines.append(
            "Create it with mode 0700 owned by the service user, e.g.:"
        )
        err_msg_lines.append(
            "    sudo install -d -m 0700 -o <service-user>"
            " -g <service-user> {}".format(parent_dir)
        )
        err_msg = os.linesep.join(err_msg_lines)
        raise ConfigurationError(err_msg)

    tmp_path = "{}.tmp".format(path)
    fd = os.open(
        tmp_path,
        os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
        TOKEN_FILE_MODE,
    )
    try:
        os.write(fd, plaintext.encode("utf-8"))
    finally:
        os.close(fd)

    # ``os.rename`` is atomic on POSIX when source and destination
    # live on the same filesystem -- which they do, since both are
    # in ``parent_dir``. This guarantees readers either see the old
    # file (or nothing) or the fully written new file, never a
    # partial write.
    os.rename(tmp_path, path)
    return


def _safe_delete_token_file(*, path: str) -> None:
    """
        Best-effort delete of the on-disk token file. Logs and
        swallows ``FileNotFoundError`` (the file may already be gone
        if the operator removed it manually) but lets every other
        OSError propagate -- a permission error here is a real
        misconfiguration that needs operator attention.

        :param path: Absolute path of the file to remove.

        :returns: None.
    """
    try:
        os.unlink(path)
    except FileNotFoundError:
        _module_logger.info(
            "pychestrate.setup.token_file.absent path=%s",
            path,
        )
    return


class InitialSetupManager:
    """
        Lifecycle manager for the ``system_initial_setup`` singleton
        row.

        :param db_session: Active SQLAlchemy session.
        :param runtime_dir: Directory where the cleartext token file
                            is created (typically
                            ``/var/lib/pychestrate``).
        :param token_filename: Leaf filename. Defaults to
                               ``initial-admin-token``.
        :param clock: Optional zero-arg callable returning the
                      current UTC datetime; tests pass a stub.
    """

    def __init__(
        self,
        *,
        db_session: DbSession,
        runtime_dir: str,
        token_filename: Optional[str] = None,
        clock: Optional[Callable[[], datetime]] = None,
    ) -> None:
        """
            Construct the manager.

            :param db_session: See class docstring.
            :param runtime_dir: See class docstring.
            :param token_filename: See class docstring.
            :param clock: See class docstring.
        """
        if runtime_dir is None or len(runtime_dir) == 0:
            raise ConfigurationError(
                "InitialSetupManager requires a non-empty runtime_dir"
            )

        if token_filename is None:
            resolved_filename = DEFAULT_TOKEN_FILENAME
        else:
            resolved_filename = token_filename

        if clock is None:
            resolved_clock: Callable[[], datetime] = _default_clock
        else:
            resolved_clock = clock

        self._db_session: DbSession = db_session
        self._runtime_dir: str = runtime_dir
        self._token_filename: str = resolved_filename
        self._clock: Callable[[], datetime] = resolved_clock
        self._token_path: str = os.path.join(
            runtime_dir, resolved_filename
        )
        return

    @property
    def token_path(self) -> str:
        """
            Absolute path the cleartext token file is (or was)
            written to. Useful for diagnostics and for the unlock
            page's "read the token from this file" instruction.

            :returns: Absolute filesystem path.
        """
        rtnval = self._token_path
        return rtnval

    def get_state(self) -> Optional[InitialSetup]:
        """
            Read the singleton row, or ``None`` if it has not been
            provisioned yet.

            :returns: :class:`InitialSetup` row or ``None``.
        """
        row = self._db_session.query(InitialSetup).filter(
            InitialSetup.singleton_key == SINGLETON_KEY_VALUE
        ).one_or_none()
        rtnval = row
        return rtnval

    def is_complete(self) -> bool:
        """
            Return whether the wizard has been finished. A missing
            row counts as "not complete" (callers should call
            :meth:`ensure_token_provisioned` first if they care).

            :returns: True iff the row exists and ``completed_at`` is
                      stamped.
        """
        row = self.get_state()
        if row is None:
            return False
        rtnval = row.completed_at is not None
        return rtnval

    def ensure_token_provisioned(self) -> InitialSetup:
        """
            Idempotent. On first call: generate a fresh token, write
            the cleartext to ``runtime_dir/token_filename`` mode
            0600, hash it, insert the singleton row, and return it.
            On subsequent calls: return the existing row unchanged
            (the token file is NOT regenerated).

            If the row already exists but the token file is missing
            -- e.g. an operator deleted it before completing setup --
            the file is recreated using a fresh token and the stored
            hash is updated. This recovers from "I lost the token"
            without a manual DB edit.

            :returns: The :class:`InitialSetup` singleton row.
            :raises: ConfigurationError on filesystem misconfig.
        """
        row = self.get_state()
        if row is not None and row.completed_at is not None:
            # Wizard is already finished. Do not regenerate anything.
            rtnval = row
            return rtnval

        if row is None:
            plaintext = _generate_token_plaintext()
            token_hash = _hash_token_bytes(plaintext=plaintext)
            _atomic_write_token_file(
                path=self._token_path, plaintext=plaintext
            )
            row = InitialSetup(
                setup_id=uuid.uuid4(),
                singleton_key=SINGLETON_KEY_VALUE,
                token_hash=token_hash,
                token_path=self._token_path,
                created_at=self._clock(),
                completed_at=None,
                completed_by_user_id=None,
            )
            self._db_session.add(row)
            self._db_session.flush()
            _module_logger.info(
                "pychestrate.setup.token_provisioned path=%s setup_id=%s",
                self._token_path,
                str(row.setup_id),
            )
            rtnval = row
            return rtnval

        # Row exists but setup is still pending. If the operator lost
        # the token, regenerate; otherwise leave the existing token
        # in place.
        if os.path.exists(self._token_path) is False:
            plaintext = _generate_token_plaintext()
            new_hash = _hash_token_bytes(plaintext=plaintext)
            _atomic_write_token_file(
                path=self._token_path, plaintext=plaintext
            )
            row.token_hash = new_hash
            row.token_path = self._token_path
            self._db_session.flush()
            _module_logger.warning(
                "pychestrate.setup.token_regenerated path=%s setup_id=%s"
                " reason=token_file_missing",
                self._token_path,
                str(row.setup_id),
            )

        rtnval = row
        return rtnval

    def verify_token(self, *, plaintext: str) -> bool:
        """
            Timing-safe compare of a submitted plaintext token
            against the stored sha256 hash.

            :param plaintext: Operator-supplied token string.

            :returns: True on match, False otherwise.
            :raises: SetupNotInitializedError when no setup row has
                     been provisioned.
                     SetupAlreadyCompleteError when setup has already
                     been finished (callers should not be invoking
                     verify on a completed wizard).
        """
        if plaintext is None or len(plaintext) == 0:
            return False

        row = self.get_state()
        if row is None:
            raise SetupNotInitializedError(
                "system_initial_setup row is missing; the runtime"
                " bootstrap did not call ensure_token_provisioned"
            )
        if row.completed_at is not None:
            raise SetupAlreadyCompleteError(
                "verify_token refused: setup is already complete"
            )

        candidate_hash = _hash_token_bytes(plaintext=plaintext)
        rtnval = hmac.compare_digest(candidate_hash, bytes(row.token_hash))
        return rtnval

    def mark_complete(self, *, completed_by_user_id: uuid.UUID) -> None:
        """
            Stamp ``completed_at`` on the singleton row, record which
            user finished the wizard, and remove the on-disk token
            file. One-way: re-entry raises
            :class:`SetupAlreadyCompleteError`.

            :param completed_by_user_id: ``identity_users.user_id``
                                         of the just-created admin.

            :returns: None.
            :raises: SetupNotInitializedError when no row exists.
                     SetupAlreadyCompleteError when ``completed_at``
                     is already set.
        """
        if completed_by_user_id is None:
            raise ConfigurationError(
                "mark_complete requires a non-null completed_by_user_id"
            )

        row = self.get_state()
        if row is None:
            raise SetupNotInitializedError(
                "system_initial_setup row is missing; cannot complete"
            )
        if row.completed_at is not None:
            raise SetupAlreadyCompleteError(
                "setup is already complete; refusing to re-stamp"
            )

        row.completed_at = self._clock()
        row.completed_by_user_id = completed_by_user_id
        self._db_session.flush()

        _safe_delete_token_file(path=self._token_path)

        _module_logger.info(
            "pychestrate.setup.completed setup_id=%s completed_by=%s",
            str(row.setup_id),
            str(completed_by_user_id),
        )
        return


__all__ = [
    "DEFAULT_TOKEN_FILENAME",
    "InitialSetupManager",
    "TOKEN_FILE_MODE",
]
