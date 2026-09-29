"""
.. module:: test_p31zq_tab_titles_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Browser tab titles tell pages apart and use one separator (PRJ-39).

.. moduleauthor:: Code Craft AI LLC

The Projects dashboard and the project list were both "Projects", an IP pool
and a resource pool of the same name had the same title, and a project page
mixed the shell's " · " with the templates' " - " ("Members - demo · Pychestrate").
Titles now read "Page · Entity · Pychestrate", and no two templates share one.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import collections
import os
import re
import uuid

from ccai import testbase

from ccai.pychestrate.webservice.webinterface.blueprints import projects as projects_package
from ccai.pychestrate.webservice.webinterface.blueprints.config.routes import extract_fragment_title

from ccai.tests.singlehost.pychestrate.webservice.phase10._e2e_harness import (
    drive_request,
    ensure_app,
    logged_in_cookies,
)
from ccai.tests.singlehost.pychestrate.webservice.phase10._projects_ui_helpers import create_project_via_ui


def _fragment(title: str) -> str:
    return '<meta name="pyc-page-title" content="{}"><section>x</section>'.format(title)


def test_the_parts_of_a_title_are_joined_with_the_shells_separator():
    """
    **Feature: tab titles (PRJ-39)**
    **Property: a template title "Members - demo - Pychestrate" becomes
    "Members · demo · Pychestrate"; the legacy suffixes are still removed; a
    title that is only the product name, or empty, leaves the path table to
    decide.**
    """
    results = [
        extract_fragment_title(html=_fragment(raw))[1]
        for raw in (
            "Members - demo - Pychestrate",
            "IP Pool - lab-1 - Pychestrate Resources",
            "jdoe - User - Pychestrate Configuration",
            "Roles - Pychestrate Configuration",
            "Pychestrate",
            "",
        )
    ]

    testbase.assert_equal(
        results,
        ["Members · demo · Pychestrate", "IP Pool · lab-1 · Pychestrate", "jdoe · User · Pychestrate",
         "Roles · Pychestrate", None, None],
    )
    return


def test_no_two_templates_share_a_title_block():
    """
    **Feature: tab titles (PRJ-39)**
    **Property: across the config, projects and resources templates, every
    ``{% block title %}`` is different from every other (the dashboard and
    the list of projects, and the IP pool and resource pool detail pages,
    used to share one).**
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(projects_package.__file__)))
    titles = collections.defaultdict(list)
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            if not name.endswith(".html"):
                continue
            path = os.path.join(dirpath, name)
            with open(path, encoding="utf-8") as handle:
                found = re.search(r"\{% block title %\}(.*?)\{% endblock %\}", handle.read(), re.S)
            if found is not None:
                titles[found.group(1).strip()].append(os.path.relpath(path, root))
    shared = {title: paths for title, paths in titles.items() if len(paths) > 1}

    testbase.assert_equal(shared, {})
    return


def _title(response) -> str:
    found = re.search(r"<title>(.*?)</title>", response.text, re.S)
    return found.group(1) if found is not None else ""


def test_the_projects_dashboard_and_list_and_a_project_page_read_differently_in_the_tab():
    """
    **Feature: tab titles (PRJ-39)**
    **Property: through the application, /projects is "Project Dashboard ·
    Pychestrate", /projects/list is "All Projects · Pychestrate", and a
    project's members page is "Members · <project> · Pychestrate", with no
    " - " left in any of them.**
    """
    handle = ensure_app()
    cookies = logged_in_cookies(wsgi_app=handle.wsgi_app)
    project_id = create_project_via_ui(wsgi_app=handle.wsgi_app, cookies=cookies, prefix="ttl" + uuid.uuid4().hex[:4])
    titles = {}
    for path in ("/projects", "/projects/list", "/projects/{}/members".format(project_id)):
        titles[path] = _title(drive_request(wsgi_app=handle.wsgi_app, method="GET", path=path, cookies=cookies))
    members = titles["/projects/{}/members".format(project_id)]

    testbase.assert_equal(
        (titles["/projects"], titles["/projects/list"], members.startswith("Members · ttl"), members.endswith(" · Pychestrate"),
         any(" - " in title for title in titles.values())),
        ("Project Dashboard · Pychestrate", "All Projects · Pychestrate", True, True, False),
    )
    return
