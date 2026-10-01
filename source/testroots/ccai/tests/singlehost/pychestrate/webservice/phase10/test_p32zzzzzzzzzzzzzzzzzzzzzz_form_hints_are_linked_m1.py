"""
.. module:: test_p32zzzzzzzzzzzzzzzzzzzzzz_form_hints_are_linked_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Every form hint is tied to its field with aria-describedby (DOC-20).

.. moduleauthor:: Code Craft AI LLC

Only four of about 138 form hints were tied to their field: a screen reader read the label and the input and skipped the
text that says what to type ("HTTPS or SSH URL", "3 to 64 characters ..."). A hint (``class="form-text"``) now has an id that an
``aria-describedby`` on its control (or its fieldset) names, directly or through ``ui.invalid_attrs(errors, name, id)`` which
merges it with the field's error. Text that describes no control is a note (``class="muted small"``), not a hint. This lint
reads every server-rendered template, so a new hint cannot come back unlinked.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import re

from typing import Dict, List

from ccai import testbase


HINT = re.compile(r'<(?:div|p|small|span)\s[^>]*?\bclass="[^"]*\bform-text\b[^"]*"[^>]*>')
ID = re.compile(r'\bid="([^"]+)"')


def _templates_root() -> str:
    current = os.path.dirname(os.path.abspath(__file__))
    while not os.path.isdir(os.path.join(current, "source", "site")) and current != os.path.dirname(current):
        current = os.path.dirname(current)
    return os.path.join(current, "source", "site", "ccai", "pychestrate", "webservice", "webinterface")


def _unlinked() -> Dict[str, List[str]]:
    found: Dict[str, List[str]] = {}
    for base, _dirs, files in os.walk(_templates_root()):
        for name in sorted(files):
            if not name.endswith(".html"):
                continue
            path = os.path.join(base, name)
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
            for hint in HINT.finditer(text):
                line = text.count("\n", 0, hint.start()) + 1
                ident = ID.search(hint.group(0))
                if ident is None:
                    found.setdefault(os.path.relpath(path, _templates_root()), []).append("line {}: a hint with no id".format(line))
                    continue
                value = ident.group(1)
                # The id is named by a describedby: written out, or handed to ui.invalid_attrs.
                names_it = re.search(r'aria-describedby="[^"]*\b' + re.escape(value) + r'\b', text) is not None
                names_it = names_it or re.search(r"invalid_attrs\([^)]*[\"']" + re.escape(value) + r"\b", text) is not None
                names_it = names_it or re.search(r"invalid_attrs\([^)]*\b" + re.escape(value) + r"\b", text) is not None
                if not names_it:
                    found.setdefault(os.path.relpath(path, _templates_root()), []).append("line {}: #{} is not named by any aria-describedby".format(line, value))
    return found


def test_every_form_hint_is_named_by_the_aria_describedby_of_its_field():
    """
    **Feature: form hints (DOC-20)**
    **Property: in every server-rendered template, each ``form-text`` hint has an id that an ``aria-describedby`` (or
    ``ui.invalid_attrs(errors, name, id)``) names; a text that describes no control is a ``muted small`` note.**
    """
    testbase.assert_equal(_unlinked(), {})
    return


#: Pages that render hints for fields, opened as an administrator. The static lint above reads the template source; this
#: reads what the server renders, where ``ui.invalid_attrs`` has merged the hint with the field's error.
RENDERED_PAGES: List[str] = [
    "/admin/users/create",
    "/admin/roles/create",
    "/admin/secrets/create",
    "/admin/enrollment-tokens",
    "/projects/create",
    "/account/preferences",
]


def test_rendered_hints_are_named_by_a_describedby_in_the_page():
    """
    **Feature: form hints (DOC-20)**
    **Property: on the rendered form pages every ``form-text`` hint's id appears in the ``aria-describedby`` of some
    element on the same page (at least five of the six pages render).**
    """
    from ccai.tests.singlehost.pychestrate.webservice.phase10 import _adm_helpers as adm

    cookies = adm.admin_cookies()
    problems: Dict[str, List[str]] = {}
    rendered = 0
    hints_seen = 0
    for path in RENDERED_PAGES:
        response = adm.get(path=path, cookies=cookies)
        if response.status_code != 200:
            continue
        rendered += 1
        html = response.text
        described = set()
        for match in re.finditer(r'aria-describedby="([^"]*)"', html):
            described.update(match.group(1).split())
        for hint in re.finditer(r'<(?:div|p|small|span)\s[^>]*?\bclass="[^"]*\bform-text\b[^"]*"[^>]*>', html):
            hints_seen += 1
            ident = re.search(r'\bid="([^"]+)"', hint.group(0))
            if ident is None or ident.group(1) not in described:
                problems.setdefault(path, []).append(hint.group(0)[:120])
    testbase.assert_equal((rendered >= 5, hints_seen >= 5, problems), (True, True, {}))
    return
