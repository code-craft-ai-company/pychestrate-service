"""
.. module:: test_p30d_shell_storage_and_color_invariants_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Static checks for the site shell's two documented
               invariants: browser storage holds per-viewer
               preferences only, and the shell stylesheet keeps its
               colors in the token block.

.. moduleauthor:: Code Craft AI LLC

``userguide/17-00-site-shell.rst`` promises that the web interface
writes exactly two ``localStorage`` keys -- the viewer's theme and the
sidebar's collapsed state -- and never uses ``sessionStorage`` or
IndexedDB, and that ``pyc-site-shell.css`` defines colors only in its
``:root`` token block. The Node scanner that once enforced the storage
rule was retired with the Node test harness; these tests enforce both
rules over the JavaScript and templates the service serves (every
``pyc-*`` bundle, built ``index.js`` files included; the vendored
``pyc-mj-lib`` component library is out of scope).

A change that needs another stored value adds its key to
:data:`ALLOWED_LOCAL_STORAGE_KEYS`, with the reason, in the same change.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import re

from typing import Dict, List, Set, Tuple

from ccai import testbase

import ccai.pychestrate.webservice.webinterface as webinterface_package


#: Every ``localStorage`` key the web interface may write, and why.
ALLOWED_LOCAL_STORAGE_KEYS: Dict[str, str] = {
    "pychestrate.ui.theme": "the viewer's light/dark choice from the header's Theme control",
    "pyc-site-shell.nav-collapsed": "whether the viewer collapsed the sidebar",
}

_WEBINTERFACE_DIR: str = os.path.dirname(os.path.abspath(webinterface_package.__file__))
_JAVASCRIPT_DIR: str = os.path.join(_WEBINTERFACE_DIR, "static", "javascript")
_VENDORED_BUNDLES: Tuple[str, ...] = ("pyc-mj-lib",)
_SHELL_STYLESHEET: str = os.path.join(_JAVASCRIPT_DIR, "pyc-site-shell", "pyc-site-shell.css")

_LOCAL_STORAGE_WRITE = re.compile(r"localStorage\s*\.\s*setItem\s*\(\s*([^,\s)]+)")
_LOCAL_STORAGE_OTHER_MUTATION = re.compile(
    r"localStorage\s*(\.\s*(clear|removeItem)\s*\(|\[[^\]]*\]\s*=[^=]|\.\s*[A-Za-z_$][\w$]*\s*=[^=])"
)
_FORBIDDEN_STORES = re.compile(r"\b(sessionStorage|indexedDB)\b")
_STRING_LITERAL = re.compile(r"""^(["'`])(.*)\1$""")
_CONSTANT_TEMPLATE = r"""\b(?:const|let|var)\s+{name}\s*=\s*(["'`])([^"'`]*)\1"""
_COLOR_LITERAL = re.compile(r"#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?)\s*\(")


def _served_sources() -> List[str]:
    """
        List the JavaScript files and templates the service serves,
        excluding the vendored component library.

        :returns: Absolute paths, sorted.
    """
    paths: List[str] = []
    for root, dirs, files in os.walk(_WEBINTERFACE_DIR):
        dirs[:] = [name for name in dirs if name not in _VENDORED_BUNDLES]
        for name in files:
            if name.endswith(".js") or name.endswith(".html"):
                paths.append(os.path.join(root, name))
    rtnval = sorted(paths)
    return rtnval


def _read(path: str) -> str:
    """
        Read a UTF-8 text file.

        :param path: File path.

        :returns: The file's text.
    """
    with open(path, "r", encoding="utf-8") as handle:
        rtnval = handle.read()
    return rtnval


def _resolve_key(*, argument: str, source: str) -> str:
    """
        Resolve a ``setItem`` key argument: a string literal, or a
        constant defined as one in the same file.

        :param argument: The first ``setItem`` argument, as written.
        :param source: The whole file, for constant lookup.

        :returns: The key, or ``<unresolved NAME>`` when it cannot be
                  determined statically (which the test reports).
    """
    literal = _STRING_LITERAL.match(argument)
    if literal is not None:
        return literal.group(2)
    constant = re.search(_CONSTANT_TEMPLATE.format(name=re.escape(argument)), source)
    if constant is not None:
        return constant.group(2)
    rtnval = "<unresolved {}>".format(argument)
    return rtnval


def _written_local_storage_keys() -> Dict[str, Set[str]]:
    """
        Map every ``localStorage.setItem`` key found in the served
        sources to the files that write it.

        :returns: ``{key: {relative path, ...}}``.
    """
    written: Dict[str, Set[str]] = {}
    for path in _served_sources():
        source = _read(path)
        for match in _LOCAL_STORAGE_WRITE.finditer(source):
            key = _resolve_key(argument=match.group(1), source=source)
            written.setdefault(key, set()).add(os.path.relpath(path, _WEBINTERFACE_DIR))
    rtnval = written
    return rtnval


def test_web_interface_writes_only_allowlisted_local_storage_keys():
    """
    **Feature: site-shell invariants (userguide 17-00)**
    **Property: every localStorage.setItem in the served JavaScript and
    templates writes one of the allowlisted per-viewer preference
    keys.**
    """
    written = _written_local_storage_keys()
    unexpected = {key: sorted(paths) for key, paths in written.items() if key not in ALLOWED_LOCAL_STORAGE_KEYS}
    testbase.assert_equal(unexpected, {}, "localStorage keys outside the allowlist: {}".format(unexpected))
    return


def test_web_interface_mutates_local_storage_only_through_set_item():
    """
    **Feature: site-shell invariants (userguide 17-00)**
    **Property: nothing clears localStorage, removes keys from it, or
    assigns to it directly; the allowlist check above sees every
    write.**
    """
    offenders: List[str] = []
    for path in _served_sources():
        source = _read(path)
        for match in _LOCAL_STORAGE_OTHER_MUTATION.finditer(source):
            offenders.append("{}: {}".format(os.path.relpath(path, _WEBINTERFACE_DIR), match.group(0)))
    testbase.assert_equal(offenders, [], "unexpected localStorage mutations: {}".format(offenders))
    return


def test_web_interface_never_uses_session_storage_or_indexeddb():
    """
    **Feature: site-shell invariants (userguide 17-00)**
    **Property: the served JavaScript and templates never reference
    sessionStorage or IndexedDB.**
    """
    offenders: List[str] = []
    for path in _served_sources():
        for match in _FORBIDDEN_STORES.finditer(_read(path)):
            offenders.append("{}: {}".format(os.path.relpath(path, _WEBINTERFACE_DIR), match.group(0)))
    testbase.assert_equal(offenders, [], "sessionStorage / IndexedDB references: {}".format(offenders))
    return


def test_every_allowlisted_local_storage_key_is_still_written():
    """
    **Feature: site-shell invariants (userguide 17-00)**
    **Property: the allowlist carries no stale keys -- each one is
    still written somewhere, so the documented list stays exact.**
    """
    written = _written_local_storage_keys()
    stale = sorted(key for key in ALLOWED_LOCAL_STORAGE_KEYS if key not in written)
    testbase.assert_equal(stale, [], "allowlisted keys nothing writes any more: {}".format(stale))
    return


def test_shell_stylesheet_keeps_color_literals_in_the_root_token_block():
    """
    **Feature: site-shell invariants (userguide 17-00)**
    **Property: pyc-site-shell.css has no color literal (hex, rgb(),
    hsl()) outside its :root token block.**
    """
    stylesheet = _read(_SHELL_STYLESHEET)
    without_comments = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), stylesheet, flags=re.DOTALL)
    root_block = re.search(r":root\s*\{[^}]*\}", without_comments)
    testbase.assert_equal(root_block is not None, True, "no :root token block in pyc-site-shell.css")
    outside = without_comments[:root_block.start()] + "\n" * root_block.group(0).count("\n") + without_comments[root_block.end():]
    offenders: List[str] = []
    for line_number, line in enumerate(outside.splitlines(), start=1):
        if _COLOR_LITERAL.search(line) is not None:
            offenders.append("{}: {}".format(line_number, line.strip()))
    testbase.assert_equal(offenders, [], "color literals outside :root: {}".format(offenders))
    return
