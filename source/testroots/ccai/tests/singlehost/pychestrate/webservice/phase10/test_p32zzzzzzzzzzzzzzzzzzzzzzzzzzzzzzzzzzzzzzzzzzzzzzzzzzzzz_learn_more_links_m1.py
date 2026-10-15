"""
.. module:: test_learn_more_links_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: "Learn more" links from the complex forms to the user guide (audit DOC-20).

.. moduleauthor:: Code Craft AI LLC

The audit found no outbound links on any page. The service serves the guide it shipped with, so a form can link to the section that explains it. Which forms
link where is decided in the templates (``ui.learn_more(page, anchor)``). The link is drawn only when the built guide is installed and has the page, so it never
leads nowhere; this test keeps it from leading to a section that was renamed away, by checking every link against the headings of the guide's source.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import re
import tempfile

from typing import Dict, List, Set, Tuple

from docutils import nodes

from ccai import testbase
from ccai.testbase.mocking import create_module_patch

from ccai.pychestrate.webservice.webinterface.site_shell import user_guide_route
from ccai.tests.singlehost.pychestrate.webservice.phase10 import _adm_helpers as adm


CALL = re.compile(r"""ui\.learn_more\(\s*"([^"]+)"\s*(?:,\s*"([^"]*)")?""")
UNDERLINE = re.compile(r"^([=\-~^\"#*+.])\1{2,}\s*$")


def _repo_root() -> str:
    current = os.path.dirname(os.path.abspath(__file__))
    while not os.path.isdir(os.path.join(current, "userguide")) and current != os.path.dirname(current):
        current = os.path.dirname(current)
    return current


def _calls() -> List[Tuple[str, str, str]]:
    """Every ``ui.learn_more(page, anchor)`` in the web interface's templates: ``(template, page, anchor)``."""
    base = os.path.join(_repo_root(), "source", "site", "ccai", "pychestrate", "webservice", "webinterface")
    found: List[Tuple[str, str, str]] = []
    for folder, _dirs, files in os.walk(base):
        for name in sorted(files):
            if not name.endswith(".html"):
                continue
            path = os.path.join(folder, name)
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
            for match in CALL.finditer(text):
                found.append((os.path.relpath(path, base), match.group(1), match.group(2) or ""))
    return found


def _section_ids(page: str) -> Set[str]:
    """The ids Sphinx gives the sections of a chapter: docutils' own rule applied to each heading of the source."""
    path = os.path.join(_repo_root(), "userguide", page + ".rst")
    with open(path, encoding="utf-8") as handle:
        lines = handle.read().split("\n")
    ids: Set[str] = set()
    for index in range(1, len(lines)):
        title = lines[index - 1].strip()
        if len(title) > 0 and UNDERLINE.match(lines[index]) is not None and len(lines[index].strip()) >= len(title) and UNDERLINE.match(lines[index - 1]) is None:
            ids.add(nodes.make_id(title))
    return ids


def test_every_learn_more_link_names_a_chapter_and_a_section_of_the_guide():
    """
    **Feature: learn more links (DOC-20)**
    **Property: each ``ui.learn_more(page, anchor)`` in the templates names a chapter that exists in ``userguide/`` and a section whose id is a heading of it;
    the forms that need explaining use it (at least twelve links over the roles, projects, devices, pools, IP pools, reservations, health, RPA job type and
    notification pages).**
    """
    calls = _calls()
    broken: List[str] = []
    for template, page, anchor in calls:
        if not os.path.isfile(os.path.join(_repo_root(), "userguide", page + ".rst")):
            broken.append("{}: no chapter {}".format(template, page))
        elif len(anchor) > 0 and anchor not in _section_ids(page):
            broken.append("{}: {} has no section {}".format(template, page, anchor))
    templates = {template for template, _page, _anchor in calls}

    testbase.assert_equal(
        (broken, len(calls) >= 12, any("roles" in t for t in templates), any("projects/projects/create" in t for t in templates),
         any("resources/create" in t for t in templates), any("notifications" in t for t in templates), any("rpa_types" in t for t in templates)),
        ([], True, True, True, True, True, True),
    )
    return


def test_the_address_is_drawn_only_for_a_guide_that_is_installed_and_has_the_page():
    """
    **Feature: learn more links (DOC-20)**
    **Property: ``user_guide_page_url`` answers ``/docs/<page>.html#<section>`` when the built guide's first page and that chapter exist, the page alone
    without a section, and an empty string when the guide is missing or the chapter is not in it.**
    """
    with tempfile.TemporaryDirectory() as empty, tempfile.TemporaryDirectory() as installed:
        for name in ("userguide.html", "16-00-running-and-reading-work.html"):
            with open(os.path.join(installed, name), "w", encoding="utf-8") as handle:
                handle.write("<html></html>")
        answers = (
            user_guide_route.user_guide_page_url("16-00-running-and-reading-work", "be-told-when-a-run-fails", docs_root=installed),
            user_guide_route.user_guide_page_url("16-00-running-and-reading-work", docs_root=installed),
            user_guide_route.user_guide_page_url("99-00-no-such-chapter", "x", docs_root=installed),
            user_guide_route.user_guide_page_url("16-00-running-and-reading-work", "x", docs_root=empty),
        )

    testbase.assert_equal(
        answers,
        ("/docs/16-00-running-and-reading-work.html#be-told-when-a-run-fails", "/docs/16-00-running-and-reading-work.html", "", ""),
    )
    return


def _guide_directory(*, chapters: List[str]) -> tempfile.TemporaryDirectory:
    folder = tempfile.TemporaryDirectory()
    for name in ["userguide"] + chapters:
        with open(os.path.join(folder.name, name + ".html"), "w", encoding="utf-8") as handle:
            handle.write("<html></html>")
    return folder


def _hrefs(path: str) -> List[str]:
    page = adm.get(path=path, cookies=adm.admin_cookies())
    return re.findall(r'<a class="pyc-learn-more" href="([^"]+)"', page.text) if page.status_code == 200 else ["status {}".format(page.status_code)]


def test_a_form_page_links_to_its_section_when_the_guide_is_installed_and_to_nothing_when_it_is_not():
    """
    **Feature: learn more links (DOC-20)**
    **Property: with the guide installed the create-role, create-project, create-resource and add-channel pages each carry one link to the section that
    explains them (opening in a new tab, with a screen-reader note); with no guide installed none of them carries any.**
    """
    paths = {
        "/admin/roles/create": "/docs/01-00-overview.html#concepts",
        "/projects/create": "/docs/02-00-getting-started.html#create-a-project",
        "/resources/create": "/docs/15-00-lab-administration.html#devices",
        "/admin/notifications/channels/create": "/docs/16-00-running-and-reading-work.html#be-told-when-a-run-fails",
    }
    chapters = ["01-00-overview", "02-00-getting-started", "15-00-lab-administration", "16-00-running-and-reading-work"]
    patch = create_module_patch(user_guide_route, "user_guide_root")
    try:
        mock = patch.activate()
        with _guide_directory(chapters=chapters) as installed:
            mock.configure(return_value=installed)
            with_guide = {path: _hrefs(path) for path in paths}
            html = adm.get(path="/admin/roles/create", cookies=adm.admin_cookies()).text
        with tempfile.TemporaryDirectory() as empty:
            mock.configure(return_value=empty)
            without_guide = {path: _hrefs(path) for path in paths}
    finally:
        patch.deactivate()

    testbase.assert_equal(
        (with_guide, without_guide, 'target="_blank" rel="noopener"' in html, "opens in a new tab" in html),
        ({path: [href] for path, href in paths.items()}, {path: [] for path in paths}, True, True),
    )
    return
