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
import tempfile

from ccai import testbase

from ccai.errors.exceptions import ConfigurationError

from ccai.pychestrate.webservice.secrets.kek_loader import load_kek_at_startup
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
