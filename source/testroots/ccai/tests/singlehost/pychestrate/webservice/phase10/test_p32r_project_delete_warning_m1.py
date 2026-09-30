"""
.. module:: test_p32r_project_delete_warning_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Deleting a project says what goes with it, in numbers, and asks for its name (XC-15).

.. moduleauthor:: Code Craft AI LLC

The warning before a project is deleted named the kinds of thing that go with it
("members, repositories, build, test and infrastructure history ...") but not how
many, and one click confirmed it. The project page now counts what it can (repositories,
builds, test jobs, members) and its Delete form asks for the project's name to be typed.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import html
import re

from typing import Any, Dict, Tuple

from ccai import testbase

from ccai.pychestrate.webservice.webinterface.blueprints.projects.routes import describe_project_deletion

from ccai.tests.singlehost.pychestrate.webservice.phase10._e2e_harness import (
    drive_request,
    ensure_app,
    logged_in_cookies,
)
from ccai.tests.singlehost.pychestrate.webservice.phase10._projects_ui_helpers import (
    create_project_via_ui,
)
from ccai.tests.singlehost.pychestrate.webservice.phase10._test_repository import add_repository


TAIL = "Everything else in it goes too: infrastructure history, releases, watches and RPA specifications and jobs. This cannot be undone."


def test_the_warning_counts_what_it_can_and_leaves_out_what_it_cannot():
    """
    **Feature: deletion warning with numbers (XC-15)**
    **Property: counts are pluralised and joined ("2 repositories, 41 builds and 1 test job"); a
    zero or unknown count is left out; one member "loses" access and several "lose" it; with no
    counts at all only the name and the general warning remain.**
    """
    everything = describe_project_deletion(name="Alpha", members=3, repositories=2, builds=41, tests=1)
    one_member = describe_project_deletion(name="Alpha", members=1, repositories=1, builds=0, tests=None)
    nothing = describe_project_deletion(name="Alpha", members=None, repositories=0, builds=None, tests=0)
    only_builds = describe_project_deletion(name="Alpha", members=0, repositories=None, builds=5, tests=None)

    testbase.assert_equal(
        (everything, one_member, nothing, only_builds),
        (
            'Delete the project "Alpha"? This permanently deletes its 2 repositories, 41 builds and 1 test job. 3 members lose access. ' + TAIL,
            'Delete the project "Alpha"? This permanently deletes its 1 repository. 1 member loses access. ' + TAIL,
            'Delete the project "Alpha"? ' + TAIL,
            'Delete the project "Alpha"? This permanently deletes its 5 builds. ' + TAIL,
        ),
    )
    return


def _form_attributes(page: str) -> Tuple[str, str]:
    """The ``data-confirm`` and ``data-confirm-type`` of the project page's Delete form."""
    match = re.search(r'<form[^>]*action="/projects/\d+/delete"[^>]*>', page)
    testbase.assert_true(match is not None, "no delete form on the page")
    tag = match.group(0)
    message = re.search(r'data-confirm="([^"]*)"', tag)
    typed = re.search(r'data-confirm-type="([^"]*)"', tag)
    return (html.unescape(message.group(1)) if message else "", html.unescape(typed.group(1)) if typed else "")


def test_the_project_page_asks_for_the_projects_name_and_counts_what_goes_with_it():
    """
    **Feature: deletion warning with numbers (XC-15)**
    **Property: a project with two repositories has a Delete form that asks for its own name to be
    typed and warns that "2 repositories" are deleted and its member loses access; after a repository
    is added the count is 3, not a stale number.**
    """
    handle = ensure_app()
    cookies = logged_in_cookies(wsgi_app=handle.wsgi_app)
    project_id = create_project_via_ui(wsgi_app=handle.wsgi_app, cookies=cookies, prefix="delwarn")
    add_repository(wsgi_app=handle.wsgi_app, cookies=cookies, project_id=project_id, name="first")
    add_repository(wsgi_app=handle.wsgi_app, cookies=cookies, project_id=project_id, name="second")

    def _page() -> str:
        return drive_request(wsgi_app=handle.wsgi_app, method="GET", path="/projects/{}".format(project_id), cookies=cookies).text

    page = _page()
    name = html.unescape(re.search(r"<h1>([^<]+)</h1>", page).group(1))
    message, typed = _form_attributes(page)
    add_repository(wsgi_app=handle.wsgi_app, cookies=cookies, project_id=project_id, name="third")
    message_after, _typed_after = _form_attributes(_page())

    testbase.assert_equal(
        (typed == name, message.startswith('Delete the project "{}"? This permanently deletes its 2 repositories.'.format(name)), message.endswith(TAIL), "3 repositories" in message_after),
        (True, True, True, True),
    )
    return
