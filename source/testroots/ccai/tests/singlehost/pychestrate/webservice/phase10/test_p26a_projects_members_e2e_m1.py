"""
.. module:: test_p26a_projects_members_e2e_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: End-to-end tests for project membership through the
               consumer UI (PRJ-01).

.. moduleauthor:: Code Craft AI LLC

Drives the real webworks app against the shared in-memory database:
the admin creates a project through ``POST /projects/create`` and then
adds, re-roles and removes a member through the Members pages. User
ids are UUIDs; the member routes used to coerce them to ``int`` and
every attempt failed with "user_id is required".
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import urllib.parse
import uuid

from typing import Dict

from ccai import testbase

from ccai.pychestrate.webservice.metadata import SITE_SHARED_GLOBALS
from ccai.tests.singlehost.pychestrate.webservice.phase10._e2e_harness import (
    drive_request,
    ensure_app,
    ensure_seeded_user,
    extract_csrf_token_from_cookies,
    logged_in_cookies,
)


_FORM_HEADERS: Dict[str, str] = {
    "Content-Type": "application/x-www-form-urlencoded",
}


def _post_form(
        *, wsgi_app, path: str, cookies: Dict[str, str], fields: Dict[str, str]
    ):
    """
        POST ``fields`` (plus the session's CSRF token) as a urlencoded
        form and fold any re-signed session cookie back into
        ``cookies``.

        :returns: The :class:`WsgiResponse`.
    """
    payload = dict(fields)
    payload["csrf_token"] = extract_csrf_token_from_cookies(cookies=cookies)
    response = drive_request(
        wsgi_app=wsgi_app,
        method="POST",
        path=path,
        body=urllib.parse.urlencode(payload).encode("utf-8"),
        headers=_FORM_HEADERS,
        cookies=cookies,
    )
    cookies.update(response.collect_set_cookies())
    return response


def _get(*, wsgi_app, path: str, cookies: Dict[str, str]):
    """
        GET ``path`` with ``cookies`` and fold any re-signed session
        cookie back into ``cookies``.

        :returns: The :class:`WsgiResponse`.
    """
    response = drive_request(
        wsgi_app=wsgi_app, method="GET", path=path, cookies=cookies,
    )
    cookies.update(response.collect_set_cookies())
    return response


def _create_project(*, wsgi_app, cookies: Dict[str, str], prefix: str) -> int:
    """
        Create a project through the UI and return its id (parsed from
        the redirect to the project page).
    """
    name = "{}-{}".format(prefix, uuid.uuid4().hex[:8])
    response = _post_form(
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


def _seed_membership(*, project_id: int, user_id: str, role: str) -> None:
    """
        Add ``user_id`` to the project straight through the manager, so
        the edit / remove tests do not depend on the add route.
    """
    from ccai.pychestrate.core.managers.project_manager import (  # noqa: E402
        ProjectManager,
        ProjectRole,
    )

    db_session = SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY()
    try:
        manager = ProjectManager(db_session)
        manager.add_member(project_id, user_id, ProjectRole(role), user_id)
    finally:
        db_session.close()
    return


def _member_role(*, project_id: int, user_id: str):
    """
        Read the stored project role for ``user_id`` straight from the
        database (``None`` when the user is not a member).
    """
    from ccai.pychestrate.core.orm import ProjectMember  # noqa: E402

    db_session = SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY()
    try:
        member = (
            db_session.query(ProjectMember)
            .filter(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == uuid.UUID(user_id),
            )
            .first()
        )
        rtnval = member.role if member is not None else None
    finally:
        db_session.close()
    return rtnval


def test_admin_adds_a_member_by_uuid_and_the_member_row_appears():
    """
    **Feature: projects members (PRJ-01)**
    **Property: POST /projects/{id}/members/add with a user's UUID
    adds the member, and the Members page then lists that user.**
    """
    handle = ensure_app()
    cookies = logged_in_cookies(wsgi_app=handle.wsgi_app)
    member = ensure_seeded_user(login="e2e-prj01-add")
    project_id = _create_project(
        wsgi_app=handle.wsgi_app, cookies=cookies, prefix="prj01-add"
    )

    _post_form(
        wsgi_app=handle.wsgi_app,
        path="/projects/{}/members/add".format(project_id),
        cookies=cookies,
        fields={"user_id": member.user_id, "role": "developer"},
    )
    page = _get(
        wsgi_app=handle.wsgi_app,
        path="/projects/{}/members".format(project_id),
        cookies=cookies,
    )

    testbase.assert_equal(member.login in page.text, True)
    return


def test_admin_changes_a_members_role():
    """
    **Feature: projects members (PRJ-01)**
    **Property: POST /projects/{id}/members/{uuid}/edit stores the new
    role for that member.**
    """
    handle = ensure_app()
    cookies = logged_in_cookies(wsgi_app=handle.wsgi_app)
    member = ensure_seeded_user(login="e2e-prj01-edit")
    project_id = _create_project(
        wsgi_app=handle.wsgi_app, cookies=cookies, prefix="prj01-edit"
    )
    _seed_membership(project_id=project_id, user_id=member.user_id, role="viewer")

    _post_form(
        wsgi_app=handle.wsgi_app,
        path="/projects/{}/members/{}/edit".format(project_id, member.user_id),
        cookies=cookies,
        fields={"role": "administrator"},
    )

    testbase.assert_equal(
        _member_role(project_id=project_id, user_id=member.user_id),
        "administrator",
    )
    return


def test_admin_removes_a_member():
    """
    **Feature: projects members (PRJ-01)**
    **Property: POST /projects/{id}/members/{uuid}/remove removes the
    membership.**
    """
    handle = ensure_app()
    cookies = logged_in_cookies(wsgi_app=handle.wsgi_app)
    member = ensure_seeded_user(login="e2e-prj01-remove")
    project_id = _create_project(
        wsgi_app=handle.wsgi_app, cookies=cookies, prefix="prj01-remove"
    )
    _seed_membership(project_id=project_id, user_id=member.user_id, role="developer")

    _post_form(
        wsgi_app=handle.wsgi_app,
        path="/projects/{}/members/{}/remove".format(project_id, member.user_id),
        cookies=cookies,
        fields={},
    )

    testbase.assert_equal(
        _member_role(project_id=project_id, user_id=member.user_id), None
    )
    return
