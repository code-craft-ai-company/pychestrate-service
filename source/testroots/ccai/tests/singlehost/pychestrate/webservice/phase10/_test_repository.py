"""
.. module:: _test_repository
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Add a repository to a project through the UI, for e2e tests.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import re

from typing import Any, Dict

from ccai.tests.singlehost.pychestrate.webservice.phase10._projects_ui_helpers import (
    post_form,
)


def add_repository(*, wsgi_app: Any, cookies: Dict[str, str], project_id: int, name: str) -> int:
    """
        Create a repository through ``POST /projects/{id}/repositories/create``.

        :returns: The new repository's id (parsed from the redirect).

        :raises AssertionError: when the create does not redirect to the repository.
    """
    response = post_form(
        wsgi_app=wsgi_app,
        path="/projects/{}/repositories/create".format(project_id),
        cookies=cookies,
        fields={"name": name, "url": "https://example.com/{}.git".format(name), "auth_type": "none", "default_branch": "main", "description": ""},
    )
    location = response.header("Location") or ""
    found = re.search(r"/repositories/(\d+)", location)
    if response.status_code not in (302, 303) or found is None:
        raise AssertionError("repository create did not redirect to the repository: {} {} {}".format(response.status_code, location, response.text[:300]))
    return int(found.group(1))
