"""
.. module:: test_p40j_form_patterns_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests that every form ``pattern`` compiles in the browser and
               matches the rule the server enforces.

.. moduleauthor:: Code Craft AI LLC

Audit finding ADM-20. Browsers compile an input's ``pattern`` with the
RegExp ``v`` flag, which rejects an unescaped ``-`` that is not part of a
range (``[a-z0-9_-]``). An invalid pattern is ignored with only a console
warning, so the browser check never ran. The patterns now escape the
hyphen. The project-name pattern matches the server's rule, and the
server enforces the secret and scope name rule the forms state.

The ``v``-flag check is a small Python model of the character-class rules
the templates use, checked against the patterns Chromium rejected.

**Feature: forms (ADM-20 pattern attributes)**
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import re

from typing import List, Optional, Tuple

import sqlalchemy as sa

from sqlalchemy.orm import sessionmaker

from ccai import testbase

from ccai.pychestrate.core.managers.secret_manager import (
    SecretManager,
    SecretManagerError,
    SecretScopeCreateRequest,
)
from ccai.pychestrate.core.orm import PychestrateModelBase
from ccai.pychestrate.webservice.metadata import SITE_DIRECTORIES


# Characters the v flag reserves inside a class unless escaped.
_V_CLASS_RESERVED = set("()[]{}/|")
# Doubled punctuators the v flag reserves inside a class.
_V_DOUBLE_PUNCTUATORS = {c + c for c in "&!#$%*+,.:;<=>?@^`~"}


def v_flag_class_problem(pattern: str) -> Optional[str]:
    """
        The first character-class construct in ``pattern`` that the RegExp
        ``v`` flag rejects, or ``None``. Models the rules for the class
        syntax HTML ``pattern`` attributes use: escapes, ranges, reserved
        characters and doubled punctuators.
    """
    index = 0
    while index < len(pattern):
        char = pattern[index]
        if char == "\\":
            index += 2
            continue
        if char != "[":
            index += 1
            continue
        index += 1
        if index < len(pattern) and pattern[index] == "^":
            index += 1
        atoms: List[Tuple[str, bool]] = []
        while index < len(pattern) and pattern[index] != "]":
            if pattern[index] == "\\":
                atoms.append((pattern[index:index + 2], True))
                index += 2
                continue
            if pattern[index:index + 2] in _V_DOUBLE_PUNCTUATORS:
                return "doubled punctuator {!r}".format(pattern[index:index + 2])
            if pattern[index] in _V_CLASS_RESERVED:
                return "unescaped {!r} in a class".format(pattern[index])
            atoms.append((pattern[index], False))
            index += 1
        if index >= len(pattern):
            return "unterminated class"
        index += 1
        position = 0
        while position < len(atoms):
            text, escaped = atoms[position]
            if text == "-" and escaped is False:
                return "unescaped '-' that is not part of a range"
            following = atoms[position + 1] if position + 1 < len(atoms) else None
            if following is not None and following == ("-", False):
                if position + 2 >= len(atoms):
                    return "unescaped '-' that is not part of a range"
                position += 3
                continue
            position += 1
    return None


def _template_patterns() -> List[Tuple[str, str]]:
    """
        Every literal ``pattern="..."`` in the site templates, with its
        template path.
    """
    found: List[Tuple[str, str]] = []
    for root, _dirs, files in os.walk(SITE_DIRECTORIES.DIR_BLUEPRINTS):
        for fname in files:
            if fname.endswith(".html") is False:
                continue
            path = os.path.join(root, fname)
            with open(path, "r", encoding="utf-8") as fh:
                text = fh.read()
            for match in re.finditer(r'\bpattern="([^"]*)"', text):
                if "{{" in match.group(1):
                    continue
                found.append((os.path.relpath(path, SITE_DIRECTORIES.DIR_BLUEPRINTS), match.group(1)))
    return found


def test_the_checker_rejects_what_the_browser_rejected():
    """
    **Feature: forms (ADM-20 pattern attributes)**
    **Property: the v-flag model rejects the patterns Chromium refused
    (a trailing or leading unescaped hyphen in a class) and accepts their
    escaped forms.**
    """
    rejected = ["[a-zA-Z0-9][a-zA-Z0-9_-]{2,63}", "[a-zA-Z0-9_.-]+", "[a-z][a-z0-9-]{2,63}", "[-a-z]"]
    accepted = ["[a-zA-Z0-9][a-zA-Z0-9_\\-]{2,63}", "[a-z][a-z0-9\\-]{2,63}", "[a-zA-Z][a-zA-Z0-9_]*"]
    testbase.assert_equal(
        ([v_flag_class_problem(p) is not None for p in rejected], [v_flag_class_problem(p) for p in accepted]),
        ([True] * len(rejected), [None] * len(accepted)),
    )
    return


def test_every_template_pattern_compiles_under_the_v_flag():
    """
    **Feature: forms (ADM-20 pattern attributes)**
    **Property: no template ships a pattern the browser would ignore.**
    """
    problems = [
        "{}: {} ({})".format(path, pattern, v_flag_class_problem(pattern))
        for path, pattern in _template_patterns()
        if v_flag_class_problem(pattern) is not None
    ]
    testbase.assert_equal(problems, [])
    return


def test_the_project_name_pattern_matches_the_server_rule():
    """
    **Feature: forms (ADM-20 pattern attributes)**
    **Property: the project create and edit forms use the same rule as the
    project manager (letter or digit first, at most 128 characters).**
    """
    from ccai.pychestrate.core.managers.project_manager import PROJECT_NAME_PATTERN  # noqa: E402
    patterns = {pattern for path, pattern in _template_patterns() if path.startswith(os.path.join("projects", ""))
                and "projects/projects/" in path.replace(os.sep, "/")}
    samples = ["web-app", "web.app_2", "-leading", ".hidden", "x" * 128, "x" * 129, "has space"]
    browser = {p: [re.fullmatch(p, sample) is not None for sample in samples] for p in patterns}
    server = [PROJECT_NAME_PATTERN.match(sample) is not None for sample in samples]
    testbase.assert_equal(list(browser.values()), [server] * len(patterns))
    return


def _secret_manager() -> SecretManager:
    engine = sa.create_engine("sqlite://")
    PychestrateModelBase.metadata.create_all(engine)
    rtnval = SecretManager(sessionmaker(bind=engine)(), encryption_key=b"\x42" * 32)
    return rtnval


def test_the_server_refuses_a_scope_name_the_form_forbids():
    """
    **Feature: forms (ADM-20 pattern attributes)**
    **Property: creating a secret scope named "bad scope!" is refused by
    the server, not only by the browser.**
    """
    refused = False
    try:
        _secret_manager().create_scope(SecretScopeCreateRequest(name="bad scope!"))
    except SecretManagerError:
        refused = True
    testbase.assert_equal(refused, True)
    return


def test_the_server_accepts_a_scope_name_the_form_allows():
    """
    **Feature: forms (ADM-20 pattern attributes)**
    **Property: a scope name the form's pattern allows is created.**
    """
    scope = _secret_manager().create_scope(SecretScopeCreateRequest(name="ci-builds_2"))
    testbase.assert_equal(scope.name, "ci-builds_2")
    return
