"""
.. module:: test_p32zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz_delete_sits_below_content_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: A detail page keeps Delete below its content, never beside Edit (PRJ-32).

.. moduleauthor:: Code Craft AI LLC

Eight detail pages (roles, variables, release templates, watches, both pool kinds, resources) put Delete below the content; four (projects,
repositories, build specifications and RPA job types, whose "Retire type" is as final) put it in the header, in a row with Edit and Disable. A destructive button next to
the everyday ones is one slip from a lost project, and the place moved from page to page. Delete is now below the content on every detail
page, with the reason it is unavailable beside it. This lint reads every server-rendered template and fails when a danger button other than
a running job's Cancel sits in a page header's action row.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import re

from typing import Dict, List

from ccai import testbase


#: The split page header: from its opening tag to the first closing tag that starts a line (the header's own).
HEADER = re.compile(r'<div class="page-header page-header--split">.*?\n</div>\n', re.S)

#: Cancelling a build or job that is running is an urgent operational control, not a loss of data: it stays beside the status at the top.
CANCEL_FORM = re.compile(r"<form action=\"\{\{ url_for\('[^']*_cancel'.*?</form>", re.S)


def _root() -> str:
    current = os.path.dirname(os.path.abspath(__file__))
    while not os.path.isdir(os.path.join(current, "source", "site")) and current != os.path.dirname(current):
        current = os.path.dirname(current)
    return os.path.join(current, "source", "site", "ccai", "pychestrate", "webservice", "webinterface", "blueprints")


def _read(*parts: str) -> str:
    with open(os.path.join(_root(), *parts), encoding="utf-8") as handle:
        return handle.read()


def test_no_page_header_holds_a_delete_button():
    """
    **Feature: consistent detail pages (PRJ-32)**
    **Property: in no server-rendered template does a ``btn-danger`` button sit inside a split page header's action row, except the Cancel
    of a running build or job.**
    """
    found: Dict[str, int] = {}
    for base, _dirs, files in os.walk(_root()):
        for name in files:
            if name.endswith(".html"):
                path = os.path.join(base, name)
                with open(path, encoding="utf-8") as handle:
                    text = handle.read()
                for match in HEADER.finditer(text):
                    if "btn-danger" in CANCEL_FORM.sub("", match.group(0)):
                        found[os.path.relpath(path, _root())] = text.count("\n", 0, match.start()) + 1

    testbase.assert_equal(found, {})
    return


def test_the_three_pages_keep_delete_below_the_content_for_people_who_may_delete():
    """
    **Feature: consistent detail pages (PRJ-32)**
    **Property: the project, repository and build specification pages end with a ``mt`` section inside ``can_delete`` that holds the Delete form,
    and the two pages that can be blocked put the reason in the same section.**
    """
    pages = {
        "project": ("projects", "templates", "projects", "projects", "detail.html"),
        "repository": ("projects", "templates", "projects", "repositories", "detail.html"),
        "specification": ("projects", "templates", "projects", "builds", "spec_detail.html"),
    }
    found: Dict[str, List[bool]] = {}
    for label, parts in pages.items():
        text = _read(*parts)
        tail = text[text.rindex('{% if can_delete %}\n<div class="mt">'):]
        found[label] = [
            "_delete'" in tail,
            "btn btn-danger" in tail,
            tail.rstrip().endswith("{% endif %}\n{% endblock %}") or tail.rstrip().endswith("{% endblock %}"),
            ("cannot be" in tail) if label != "project" else True,
        ]

    testbase.assert_equal(found, {"project": [True] * 4, "repository": [True] * 4, "specification": [True] * 4})
    return
