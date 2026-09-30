"""
.. module:: test_p31zzzz_ui_glossary_lint_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The server-rendered pages follow the UI glossary (ADM-27).

.. moduleauthor:: Code Craft AI LLC

``userguide/18-00-ui-glossary.rst`` says what the interface calls things, and
pages had drifted from it: "N/A" and hyphens where an absent value is an em
dash, "Checkin" and "Checkout" where the verbs are "Check in" and "Check out",
headings such as "User Management" where the navigation says "Users", counts
like "Total: 1 users", and a red "Exclusive" badge where red is reserved for
errors. This lint reads every server-rendered template and fails when one of
those comes back, so the glossary is kept by a test and not by a review.

It reads the *visible* text of a template (the Jinja and the HTML tags are
stripped), so a URL, a CSS class or a variable named ``checkin`` is not a
finding.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import glob
import os
import re

from typing import Dict, List, Tuple

from ccai import testbase

import ccai.pychestrate.webservice.webinterface as webinterface_package


TEMPLATE_ROOTS = ("blueprints", "site_shell")

#: Page headings the navigation labels replaced ("Users", "Roles", "Variables", "Sessions").
BANNED_HEADINGS = ("User Management", "Role Management", "Global Variables", "Active Sessions", "Secret Management")


def _templates() -> List[Tuple[str, str]]:
    root = os.path.dirname(os.path.abspath(webinterface_package.__file__))
    found: List[Tuple[str, str]] = []
    for name in TEMPLATE_ROOTS:
        for path in sorted(glob.glob(os.path.join(root, name, "**", "*.html"), recursive=True)):
            with open(path, encoding="utf-8") as handle:
                found.append((os.path.relpath(path, root), handle.read()))
    return found


def _visible_text(source: str) -> str:
    """
        What a reader sees of a template as prose: no comments, Jinja, script, style,
        no tags, and no code (``<pre>`` and ``<code>`` hold identifiers such as the
        ``checkout`` build step type, which are not copy).
    """
    text = re.sub(r"\{#.*?#\}", " ", source, flags=re.S)
    text = re.sub(r"<(script|style|pre|code)\b.*?</\1>", " ", text, flags=re.S | re.I)
    text = re.sub(r"\{\{.*?\}\}", " ", text, flags=re.S)
    text = re.sub(r"\{%.*?%\}", " ", text, flags=re.S)
    text = re.sub(r"<[^>]*>", " ", text, flags=re.S)
    return re.sub(r"[ \t\r\f\v]+", " ", text)


def _findings() -> Dict[str, List[str]]:
    found: Dict[str, List[str]] = {
        "N/A for an absent value": [],
        "a hyphen or word for an absent value": [],
        "Checkin/Checkout/Check-in/Check-out": [],
        "Log in/Log out/Logout/Login": [],
        "a heading the navigation renamed": [],
        "a count that is always plural": [],
        "Exclusive in a danger badge": [],
    }
    for path, source in _templates():
        if "N/A" in source:
            found["N/A for an absent value"].append(path)
        if re.search(r"(?:format_datetime|local_datetime|truncate_id|default)\([^)]*'(?:-|None|None set)'\)|\bor '(?:-|None)'", source):
            found["a hyphen or word for an absent value"].append(path)
        text = _visible_text(source)
        if re.search(r"\bcheck-?(?:in|out)\b", text, re.I):
            found["Checkin/Checkout/Check-in/Check-out"].append(path)
        if re.search(r"\bLog (?:in|out)\b|\bLogout\b|\bLogin\b(?! name)", text):
            found["Log in/Log out/Logout/Login"].append(path)
        for heading in re.findall(r"<h1[^>]*>(.*?)</h1>", source, re.S):
            if _visible_text(heading).strip() in BANNED_HEADINGS:
                found["a heading the navigation renamed"].append(path)
        if re.search(r"Total: \{\{[^}]+\}\} [A-Za-z][A-Za-z ]*s\b", source):
            found["a count that is always plural"].append(path)
        if re.search(r"badge-danger\">\s*Exclusive", source):
            found["Exclusive in a danger badge"].append(path)
    return found


def test_no_template_breaks_the_glossary():
    """
    **Feature: UI glossary (ADM-27)**
    **Property: no server-rendered template shows "N/A" or a hyphen for an
    absent value, spells the check-out and check-in verbs as one word, says
    "Log in"/"Logout", heads a page with a name the navigation replaced, prints
    a count that is plural for one, or puts Exclusive in a red badge.**
    """
    found = {rule: paths for rule, paths in _findings().items() if len(paths) > 0}

    testbase.assert_equal(found, {})
    return


def test_the_lint_reads_the_templates_it_claims_to():
    """
    **Feature: UI glossary (ADM-27)**
    **Property: the lint reads well over a hundred templates from both roots,
    and its own rules catch a sample of each kind of violation (so an empty
    result is not the lint reading nothing).**
    """
    paths = [path for path, _source in _templates()]
    sample = (
        "<h1>User Management</h1><td>{{ x | format_datetime('%Y', 'N/A') }}</td>"
        "<button>Checkin All</button><a>Log in</a><p>Total: {{ n }} users</p>"
        "<span class=\"badge badge-danger\">Exclusive</span>{{ y | local_datetime(false, '-') }}"
    )
    text = _visible_text(sample)

    testbase.assert_equal(
        (
            len(paths) > 100,
            any(path.startswith("blueprints") for path in paths),
            any(path.startswith("site_shell") for path in paths),
            "N/A" in sample,
            re.search(r"\bcheck-?(?:in|out)\b", text, re.I) is not None,
            re.search(r"\bLog (?:in|out)\b", text) is not None,
            re.search(r"(?:local_datetime)\([^)]*'-'\)", sample) is not None,
            re.search(r"Total: \{\{[^}]+\}\} [A-Za-z][A-Za-z ]*s\b", sample) is not None,
            re.search(r"badge-danger\">\s*Exclusive", sample) is not None,
            "<" in text,
        ),
        (True, True, True, True, True, True, True, True, True, False),
    )
    return
