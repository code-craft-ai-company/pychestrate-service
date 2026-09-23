"""
.. module:: tests.singlehost.pychestrate.webservice.phase10._projects_ui_helpers
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Small request helpers shared by the /projects end-to-end
               test modules.

.. moduleauthor:: Code Craft AI LLC

Thin wrappers over :func:`_e2e_harness.drive_request` that post forms
with the session's CSRF token, keep the cookie jar current (the session
cookie is re-signed whenever a flash is queued or consumed) and create
projects through the UI.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import urllib.parse
import uuid

from typing import Any, Dict

from ccai.pychestrate.webservice.metadata import SITE_SHARED_GLOBALS
from ccai.tests.singlehost.pychestrate.webservice.phase10._e2e_harness import (
    WsgiResponse,
    drive_request,
    extract_csrf_token_from_cookies,
)


FORM_HEADERS: Dict[str, str] = {
    "Content-Type": "application/x-www-form-urlencoded",
}


def post_form(
        *,
        wsgi_app: Any,
        path: str,
        cookies: Dict[str, str],
        fields: Dict[str, str]
    ) -> WsgiResponse:
    """
        POST ``fields`` (plus the session's CSRF token) as a urlencoded
        form and fold any re-signed session cookie back into
        ``cookies``.

        :param wsgi_app: The WSGI app under test.
        :param path: Request path.
        :param cookies: Cookie jar; updated in place.
        :param fields: Form fields.

        :returns: The :class:`WsgiResponse`.
    """
    payload = dict(fields)
    payload["csrf_token"] = extract_csrf_token_from_cookies(cookies=cookies)
    rtnval = drive_request(
        wsgi_app=wsgi_app,
        method="POST",
        path=path,
        body=urllib.parse.urlencode(payload).encode("utf-8"),
        headers=FORM_HEADERS,
        cookies=cookies,
    )
    cookies.update(rtnval.collect_set_cookies())
    return rtnval


def get_page(
        *, wsgi_app: Any, path: str, cookies: Dict[str, str]
    ) -> WsgiResponse:
    """
        GET ``path`` with ``cookies`` and fold any re-signed session
        cookie back into ``cookies``.

        :returns: The :class:`WsgiResponse`.
    """
    rtnval = drive_request(
        wsgi_app=wsgi_app, method="GET", path=path, cookies=cookies,
    )
    cookies.update(rtnval.collect_set_cookies())
    return rtnval


def create_project_via_ui(
        *, wsgi_app: Any, cookies: Dict[str, str], prefix: str
    ) -> int:
    """
        Create a project through ``POST /projects/create`` and return its
        id (parsed from the redirect to the project page).

        :raises AssertionError: when the create does not redirect to the
                                new project.
    """
    name = "{}-{}".format(prefix, uuid.uuid4().hex[:8])
    response = post_form(
        wsgi_app=wsgi_app,
        path="/projects/create",
        cookies=cookies,
        fields={"name": name, "description": "", "metadata": ""},
    )
    location = response.header("Location") or ""
    if response.status_code not in (302, 303) or not location.startswith("/projects/"):
        raise AssertionError(
            "project create did not redirect to the project: {} {}".format(
                response.status_code, location
            )
        )
    rtnval = int(location.rstrip("/").split("/")[-1])
    return rtnval


def open_db_session() -> Any:
    """
        Open a session on the app's shared in-memory database. The
        caller closes it.
    """
    rtnval = SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY()
    return rtnval
