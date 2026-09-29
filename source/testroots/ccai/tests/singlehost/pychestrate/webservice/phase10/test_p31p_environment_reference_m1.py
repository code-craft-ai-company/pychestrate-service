"""
.. module:: test_p31p_environment_reference_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The environment variable reference describes exactly the
               variables the service and its scripts read (DOC-19).

.. moduleauthor:: Code Craft AI LLC

An audit found 21 of 47 ``PYCHESTRATE_*`` variables documented nowhere:
the enrollment CA, the envelope signing key, the presign and embed
secrets, the presence directory, the backup locations and more. The
runbook covers what a production installation sets; the reference page
(``userguide/21-00-environment-reference.rst``) lists every variable.
These tests keep it complete and free of variables that no longer exist:
adding a variable to the code without describing it, or removing one
without removing its description, fails here.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import re

from typing import Dict, List, Set

from ccai import testbase

from ccai.pychestrate.webservice.configdocs.domains import (
    ConfigDocumentDomain,
    env_var_for_domain,
)


REFERENCE: str = os.path.join("userguide", "21-00-environment-reference.rst")

#: A variable name: not the tail of a longer word (so the
#: ``X-Pychestrate-Peer-Address`` header, spelled with underscores in
#: WSGI, is not a variable) and ending in a letter or digit (so the
#: ``PYCHESTRATE_KEK_`` half of a formatted name is not one either).
NAME = re.compile(r"(?<![A-Za-z0-9_])PYCHESTRATE_[A-Z0-9_]*[A-Z0-9]")

#: Where variables are read: the service, its packages, and the scripts
#: and units that start and configure it.
CODE_ROOTS = (os.path.join("source", "site"), os.path.join("source", "packages"))
SCRIPT_ROOTS = ("deployment", "development")
SCRIPT_FILES = ("Makefile",)

SKIPPED_DIRECTORIES = ("__pycache__", "node_modules", ".cache", ".venv", "tests", "static")

MINIMUM_VARIABLES_FOUND: int = 40

_CACHE: Dict[str, Set[str]] = {}


def _repo_root() -> str:
    current = os.path.dirname(os.path.abspath(__file__))
    while not os.path.isdir(os.path.join(current, "userguide")) and current != os.path.dirname(current):
        current = os.path.dirname(current)
    return current


def _names_in(path: str) -> Set[str]:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            text = handle.read()
    except (UnicodeDecodeError, OSError):
        return set()
    return set(NAME.findall(text))


def _walk(root: str, *, suffixes: tuple) -> List[str]:
    found: List[str] = []
    for directory, subdirectories, files in os.walk(root):
        subdirectories[:] = [name for name in subdirectories if name not in SKIPPED_DIRECTORIES]
        for name in files:
            if len(suffixes) == 0 or name.endswith(suffixes):
                found.append(os.path.join(directory, name))
    return found


def _read_by_the_code() -> Set[str]:
    """
        Every variable name the service, its packages, the scripts, the
        systemd unit and the Makefile mention, plus the four document
        path variables the configuration resolver builds from its
        domains.
    """
    if "code" not in _CACHE:
        root = _repo_root()
        names: Set[str] = set()
        for base in CODE_ROOTS:
            for path in _walk(os.path.join(root, base), suffixes=(".py",)):
                names |= _names_in(path)
        for base in SCRIPT_ROOTS:
            for path in _walk(os.path.join(root, base), suffixes=()):
                names |= _names_in(path)
        for name in SCRIPT_FILES:
            names |= _names_in(os.path.join(root, name))
        for domain in ConfigDocumentDomain:
            names.add(env_var_for_domain(domain=domain))
        _CACHE["code"] = names
    return _CACHE["code"]


def _reference_text() -> str:
    with open(os.path.join(_repo_root(), REFERENCE), "r", encoding="utf-8") as handle:
        rtnval = handle.read()
    return rtnval


def test_the_scan_finds_the_variables_it_should():
    """
    **Feature: environment reference (DOC-19)**
    **Property: the scan sees at least forty variables, including the
    ones the audit found undocumented, so a broken scan cannot make the
    other tests pass by finding nothing.**
    """
    names = _read_by_the_code()
    expected = {
        "PYCHESTRATE_ENROLLMENT_CA_SOURCE",
        "PYCHESTRATE_ENVELOPE_SIGNING_KEY_FILE_PATH",
        "PYCHESTRATE_RESULT_PRESIGN_SECRET",
        "PYCHESTRATE_EMBED_SIGNING_SECRET",
        "PYCHESTRATE_PRESENCE_DIR",
        "PYCHESTRATE_BACKUP_ROOT",
        "PYCHESTRATE_DEV_MODE",
        "PYCHESTRATE_CONFIG_LANDSCAPE_PATH",
    }
    testbase.assert_equal(
        (len(names) >= MINIMUM_VARIABLES_FOUND, sorted(expected - names)),
        (True, []),
    )
    return


def test_every_variable_the_code_reads_is_described():
    """
    **Feature: environment reference (DOC-19)**
    **Property: each variable the service, its scripts or its unit
    mention appears in the reference page.**
    """
    text = _reference_text()
    missing = sorted(name for name in _read_by_the_code() if name not in text)
    testbase.assert_equal(missing, [])
    return


def test_every_variable_the_reference_describes_exists():
    """
    **Feature: environment reference (DOC-19)**
    **Property: each variable the reference page names is one the code
    or the scripts still mention, so a removed variable leaves no
    description behind.**
    """
    described = set(NAME.findall(_reference_text()))
    code = _read_by_the_code()
    stale = sorted(name for name in described if name not in code)
    testbase.assert_equal(stale, [])
    return
