"""
.. module:: test_p32zzzzzzzzzzzzzzzzzzzzzzzzzzzzzz_list_actions_sit_right_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The primary action of a list page sits on the right, on every list page (PRJ-32).

.. moduleauthor:: Code Craft AI LLC

On Users, Watches, Roles, Pools, Secrets and others the primary action ("Create ...") sits at the right-hand end of the toolbar above the table;
on Repositories, Members, Build Specifications, RPA Specifications and RPA Job Types it sat on its own line at the left, so the main action
moved from page to page. Every list page now puts it in a right-aligned toolbar. This lint reads every server-rendered template and fails
when a primary button is the only thing in a plain ``mb`` wrapper again.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import re

from typing import Dict, List

from ccai import testbase


#: A primary button, alone, in a plain "mb" wrapper (the left-aligned placement).
LEFT_PLACED = re.compile(r'<div class="mb">\s*<a href="[^"]*" class="btn btn-primary"[^>]*>[^<]*(?:\{\{[^}]*\}\}[^<]*)*</a>\s*</div>', re.S)


def _root() -> str:
    current = os.path.dirname(os.path.abspath(__file__))
    while not os.path.isdir(os.path.join(current, "source", "site")) and current != os.path.dirname(current):
        current = os.path.dirname(current)
    return os.path.join(current, "source", "site", "ccai", "pychestrate", "webservice", "webinterface", "blueprints")


def test_no_list_page_leaves_its_primary_action_at_the_left():
    """
    **Feature: consistent list pages (PRJ-32)**
    **Property: no server-rendered template wraps a lone primary button in a plain ``mb`` div; the five pages that did
    (repositories, members, build specifications, RPA specifications, RPA job types) use the right-aligned toolbar.**
    """
    found: Dict[str, List[int]] = {}
    for base, _dirs, files in os.walk(_root()):
        for name in files:
            if name.endswith(".html"):
                path = os.path.join(base, name)
                with open(path, encoding="utf-8") as handle:
                    text = handle.read()
                for match in LEFT_PLACED.finditer(text):
                    found.setdefault(os.path.relpath(path, _root()), []).append(text.count("\n", 0, match.start()) + 1)

    testbase.assert_equal(found, {})
    return


def test_the_five_pages_use_the_right_aligned_toolbar():
    """
    **Feature: consistent list pages (PRJ-32)**
    **Property: the repositories, members, build specification, RPA specification and RPA job type lists each hold their primary
    action in ``<div class="toolbar toolbar--end">``.**
    """
    pages = [
        ("projects", "templates", "projects", "repositories", "list.html"),
        ("projects", "templates", "projects", "members", "list.html"),
        ("projects", "templates", "projects", "builds", "spec_list.html"),
        ("projects", "templates", "projects", "rpa", "spec_list.html"),
        ("config", "templates", "config", "rpa_types", "list.html"),
    ]
    found = []
    for parts in pages:
        with open(os.path.join(_root(), *parts), encoding="utf-8") as handle:
            text = handle.read()
        found.append(re.search(r'<div class="toolbar toolbar--end">\s*<a href="[^"]*" class="btn btn-primary"', text) is not None)

    testbase.assert_equal(found, [True] * 5)
    return
