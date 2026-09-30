"""
.. module:: test_p31zzzw_projects_navigation_names_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: One name and one address per projects page, everywhere (PRJ-27).

.. moduleauthor:: Code Craft AI LLC

The sidebar had one entry, "All Projects", that opened the dashboard, while the
project pages' own navigation had "Dashboard" and an "All Projects" that opened
the list: the same name for two pages, and two names for one. The Projects group
now has "Projects Dashboard" (``/projects/dashboard``) and "All Projects"
(``/projects``, the list), and the project pages' navigation uses the same two
names and addresses. These tests drive the whole application.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import re
import uuid

from collections import Counter

from ccai import testbase

from ccai.pychestrate.webservice.webinterface.site_shell.nav_manifest import GROUP_PROJECTS, NAV_ENTRIES

from ccai.tests.singlehost.pychestrate.webservice.phase10._e2e_harness import (
    drive_request,
    ensure_app,
    logged_in_cookies,
)
from ccai.tests.singlehost.pychestrate.webservice.phase10._projects_ui_helpers import (
    create_project_via_ui,
)


def _sidebar_projects_entries():
    return [(entry.label, entry.route) for entry in NAV_ENTRIES if entry.group_id == GROUP_PROJECTS]


def test_the_projects_group_names_its_two_pages_and_no_label_is_used_twice():
    """
    **Feature: one name per projects page (PRJ-27)**
    **Property: the sidebar's Projects group lists "Projects Dashboard" at
    /projects/dashboard and "All Projects" at /projects, and no two sidebar
    entries (any group) share a label.**
    """
    labels = Counter(entry.label for entry in NAV_ENTRIES)

    testbase.assert_equal(
        (_sidebar_projects_entries(), sorted(label for label, count in labels.items() if count > 1)),
        ([("Projects Dashboard", "/projects/dashboard"), ("All Projects", "/projects")], []),
    )
    return


def test_each_address_opens_the_page_its_name_promises():
    """
    **Feature: one name per projects page (PRJ-27)**
    **Property: /projects and /projects/list open the list of projects (an "All
    Projects" heading and a Create Project button); /projects/dashboard opens the
    dashboard ("Projects Dashboard", "Needs attention").**
    """
    handle = ensure_app()
    cookies = logged_in_cookies(wsgi_app=handle.wsgi_app)

    pages = {}
    for path in ("/projects", "/projects/list", "/projects/dashboard"):
        response = drive_request(wsgi_app=handle.wsgi_app, method="GET", path=path, cookies=cookies)
        pages[path] = (response.status_code, "<h1>All Projects</h1>" in response.text, "Create Project" in response.text, "Needs attention" in response.text)

    testbase.assert_equal(
        pages,
        {
            "/projects": (200, True, True, False),
            "/projects/list": (200, True, True, False),
            "/projects/dashboard": (200, False, False, True),
        },
    )
    return


def test_a_project_pages_own_navigation_uses_the_sidebars_names_and_addresses():
    """
    **Feature: one name per projects page (PRJ-27)**
    **Property: the first two links of a project page's own navigation are the
    sidebar's Projects entries, name for name and address for address.**
    """
    handle = ensure_app()
    cookies = logged_in_cookies(wsgi_app=handle.wsgi_app)
    project_id = create_project_via_ui(wsgi_app=handle.wsgi_app, cookies=cookies, prefix="nav" + uuid.uuid4().hex[:4])

    response = drive_request(wsgi_app=handle.wsgi_app, method="GET", path="/projects/{}/members".format(project_id), cookies=cookies)

    nav = re.search(r'<nav class="pyc-subnav".*?</nav>', response.text, re.S)
    links = re.findall(r'<a href="([^"]*)"[^>]*>\s*(?:<svg.*?</svg>)?\s*([^<]+?)\s*</a>', nav.group(0), re.S) if nav else []
    testbase.assert_equal(
        [(text, href) for href, text in links[:2]],
        _sidebar_projects_entries(),
    )
    return
