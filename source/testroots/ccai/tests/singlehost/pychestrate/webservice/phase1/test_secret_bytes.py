"""
.. module:: test_secret_bytes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for 1-secrets-vault SecretBytes + SecretsAspects + kek_loader.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import shutil
import tempfile

from typing import Optional

from ccai import testbase

from ccai.errors.exceptions import ConfigurationError

from ccai.pychestrate.webservice.secrets.kek_loader import KekHandle, load_kek_at_startup
from ccai.pychestrate.webservice.secrets.secret_bytes import REDACTED_TOKEN, SecretBytes
from ccai.pychestrate.webservice.secrets.secrets_aspects import (
    LogVerbosity,
    SecretsAspects,
    build_default_aspects,
)


def test_secret_bytes_redacts_repr_and_str():
    """
    **Feature: 1-secrets-vault**
    **Property: SecretBytes.__repr__ and __str__ return '<redacted>'.**
    """
    sb = SecretBytes(b"hunter2")
    testbase.assert_equal(repr(sb), REDACTED_TOKEN)
    testbase.assert_equal(str(sb), REDACTED_TOKEN)
    return


def test_secret_bytes_reveal_returns_underlying():
    """
    **Feature: 1-secrets-vault**
    **Property: SecretBytes.reveal returns the raw bytes unchanged.**
    """
    sb = SecretBytes(b"hunter2")
    testbase.assert_equal(sb.reveal(), b"hunter2")
    return


def test_secret_bytes_close_zeroizes_and_blocks_reveal():
    """
    **Feature: 1-secrets-vault**
    **Property: close() zeroizes and subsequent reveal raises RuntimeError.**
    """
    sb = SecretBytes(b"hunter2")
    sb.close()
    raised = False
    try:
        sb.reveal()
    except RuntimeError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_build_default_aspects_has_sync_true_and_no_mutable_defaults():
    """
    **Feature: 1-secrets-vault**
    **Property: build_default_aspects returns a frozen dataclass with
    sane defaults (sync=True, retry_budget=3, timeout=5.0s).**
    """
    a = build_default_aspects()
    testbase.assert_equal(isinstance(a, SecretsAspects), True)
    testbase.assert_equal(a.sync, True)
    testbase.assert_equal(a.timeout_seconds, 5.0)
    testbase.assert_equal(a.retry_budget, 3)
    testbase.assert_equal(a.log_verbosity, LogVerbosity.NORMAL)
    return


def test_kek_loader_file_source_loads_material():
    """
    **Feature: 1-secrets-vault**
    **Property: load_kek_at_startup('file') returns a KekHandle wrapping
    the file bytes in a SecretBytes.**
    """
    fd, path = tempfile.mkstemp(prefix="phase1-kek-test-")
    os.close(fd)
    try:
        with open(path, "wb") as handle:
            handle.write(b"X" * 32)

        kek = load_kek_at_startup(
            source="file",
            file_path=path,
            env_var=None,
            kek_id="test-kek",
        )

        testbase.assert_equal(kek.kek_id, "test-kek")
        testbase.assert_equal(kek.source, "file")
        testbase.assert_equal(kek.key_material.reveal(), b"X" * 32)
    finally:
        os.remove(path)
    return


def test_kek_loader_file_missing_raises():
    """
    **Feature: 1-secrets-vault**
    **Property: Missing KEK file raises ConfigurationError.**
    """
    raised = False
    try:
        load_kek_at_startup(
            source="file",
            file_path="/nonexistent/path/for/phase1-test",
            env_var=None,
            kek_id="test-kek",
        )
    except ConfigurationError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_kek_loader_rejects_short_material():
    """
    **Feature: 1-secrets-vault**
    **Property: KEK material shorter than 32 bytes raises ConfigurationError.**
    """
    fd, path = tempfile.mkstemp(prefix="phase1-kek-short-")
    os.close(fd)
    try:
        with open(path, "wb") as handle:
            handle.write(b"tooshort")

        raised = False
        try:
            load_kek_at_startup(
                source="file",
                file_path=path,
                env_var=None,
                kek_id="test-kek",
            )
        except ConfigurationError:
            raised = True
        testbase.assert_equal(raised, True)
    finally:
        os.remove(path)
    return


def test_kek_loader_unsupported_source_raises():
    """
    **Feature: 1-secrets-vault**
    **Property: An unsupported KEK source raises ConfigurationError.**
    """
    raised = False
    try:
        load_kek_at_startup(
            source="kms",
            file_path=None,
            env_var=None,
            kek_id="test-kek",
        )
    except ConfigurationError:
        raised = True
    testbase.assert_equal(raised, True)
    return


# ---------------------------------------------------------------------------
# KEK file permissions. The operator runbook promises that the runtime
# refuses a KEK file anyone but the service user can access; these tests
# pin that promise on POSIX hosts.
# ---------------------------------------------------------------------------


_PERM_TEST_KEK_MATERIAL: bytes = b"K" * 32


def _write_kek_file_with_mode(*, directory: str, mode: int) -> str:
    """
        Write 32 bytes of KEK material into ``directory`` and set the
        file's mode.

        :param directory: Directory that receives the key file.
        :param mode: Permission bits to apply after writing.

        :returns: The key file path.
    """
    path = os.path.join(directory, "active.kek")
    with open(path, "wb") as handle:
        handle.write(_PERM_TEST_KEK_MATERIAL)
    os.chmod(path, mode)
    rtnval = path
    return rtnval


def _load_kek_or_capture_error(*, path: str) -> Optional[ConfigurationError]:
    """
        Run the loader against ``path`` and return the configuration
        error it raised, or ``None`` when it loaded the key.

        :param path: KEK file path.

        :returns: The raised :class:`ConfigurationError`, or ``None``.
    """
    try:
        kek = load_kek_at_startup(
            source="file",
            file_path=path,
            env_var=None,
            kek_id="perm-test-kek",
        )
    except ConfigurationError as xcpt:
        return xcpt
    testbase.assert_equal(isinstance(kek, KekHandle), True)
    return None


def test_kek_loader_refuses_world_readable_key_file():
    """
    **Feature: 1-secrets-vault (KEK file permissions)**
    **Property: A KEK file other users can read (0644) is refused with
    a ConfigurationError.**
    """
    workdir = tempfile.mkdtemp(prefix="kek-perm-")
    try:
        path = _write_kek_file_with_mode(directory=workdir, mode=0o644)
        error = _load_kek_or_capture_error(path=path)
        testbase.assert_equal(error is not None, True)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    return


def test_kek_loader_refuses_group_readable_key_file():
    """
    **Feature: 1-secrets-vault (KEK file permissions)**
    **Property: A KEK file its group can read (0640) is refused with a
    ConfigurationError.**
    """
    workdir = tempfile.mkdtemp(prefix="kek-perm-")
    try:
        path = _write_kek_file_with_mode(directory=workdir, mode=0o640)
        error = _load_kek_or_capture_error(path=path)
        testbase.assert_equal(error is not None, True)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    return


def test_kek_loader_refuses_group_writable_key_file():
    """
    **Feature: 1-secrets-vault (KEK file permissions)**
    **Property: A KEK file its group could replace (0620) is refused
    with a ConfigurationError, even though the group cannot read it.**
    """
    workdir = tempfile.mkdtemp(prefix="kek-perm-")
    try:
        path = _write_kek_file_with_mode(directory=workdir, mode=0o620)
        error = _load_kek_or_capture_error(path=path)
        testbase.assert_equal(error is not None, True)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    return


def test_kek_loader_accepts_owner_read_write_key_file():
    """
    **Feature: 1-secrets-vault (KEK file permissions)**
    **Property: A 0600 KEK file loads and yields the file's bytes.**
    """
    workdir = tempfile.mkdtemp(prefix="kek-perm-")
    try:
        path = _write_kek_file_with_mode(directory=workdir, mode=0o600)
        kek = load_kek_at_startup(
            source="file",
            file_path=path,
            env_var=None,
            kek_id="perm-test-kek",
        )
        testbase.assert_equal(kek.key_material.reveal(), _PERM_TEST_KEK_MATERIAL)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    return


def test_kek_loader_accepts_owner_read_only_key_file():
    """
    **Feature: 1-secrets-vault (KEK file permissions)**
    **Property: A 0400 KEK file loads without error.**
    """
    workdir = tempfile.mkdtemp(prefix="kek-perm-")
    try:
        path = _write_kek_file_with_mode(directory=workdir, mode=0o400)
        error = _load_kek_or_capture_error(path=path)
        testbase.assert_equal(error is None, True)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    return


def test_kek_permission_error_names_path_mode_and_fix():
    """
    **Feature: 1-secrets-vault (KEK file permissions)**
    **Property: The refusal message names the key file, the mode that
    was found, and the chmod command that fixes it.**
    """
    workdir = tempfile.mkdtemp(prefix="kek-perm-")
    try:
        path = _write_kek_file_with_mode(directory=workdir, mode=0o644)
        error = _load_kek_or_capture_error(path=path)
        testbase.assert_equal(error is not None, True)
        message = str(error)
        testbase.assert_equal(path in message, True)
        testbase.assert_equal("0644" in message, True)
        testbase.assert_equal("chmod 0600 {}".format(path) in message, True)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    return


def test_kek_permission_check_judges_the_symlink_target():
    """
    **Feature: 1-secrets-vault (KEK file permissions)**
    **Property: A symlink to an owner-only key file loads -- the check
    reads the mode of the file that holds the key, not the link's own
    (always 0777) mode.**
    """
    workdir = tempfile.mkdtemp(prefix="kek-perm-")
    try:
        target = _write_kek_file_with_mode(directory=workdir, mode=0o600)
        link_path = os.path.join(workdir, "current.kek")
        os.symlink(target, link_path)
        error = _load_kek_or_capture_error(path=link_path)
        testbase.assert_equal(error is None, True)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    return
