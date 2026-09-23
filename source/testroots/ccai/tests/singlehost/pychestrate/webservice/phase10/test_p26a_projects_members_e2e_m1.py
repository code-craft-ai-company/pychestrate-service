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


import uuid

from ccai import testbase

from ccai.tests.singlehost.pychestrate.webservice.phase10._e2e_harness import (
    ensure_app,
    ensure_seeded_user,
    logged_in_cookies,
)
from ccai.tests.singlehost.pychestrate.webservice.phase10._projects_ui_helpers import (
    create_project_via_ui,
    get_page,
    open_db_session,
    post_form,
)


def _seed_membership(*, project_id: int, user_id: str, role: str) -> None:
    """
        Add ``user_id`` to the project straight through the manager, so
        the edit / remove tests do not depend on the add route.
    """
    from ccai.pychestrate.core.managers.project_manager import (  # noqa: E402
        ProjectManager,
        ProjectRole,
    )

    db_session = open_db_session()
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

    db_session = open_db_session()
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
    project_id = create_project_via_ui(
        wsgi_app=handle.wsgi_app, cookies=cookies, prefix="prj01-add"
    )

    post_form(
        wsgi_app=handle.wsgi_app,
        path="/projects/{}/members/add".format(project_id),
        cookies=cookies,
        fields={"user_id": member.user_id, "role": "developer"},
    )
    page = get_page(
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
    project_id = create_project_via_ui(
        wsgi_app=handle.wsgi_app, cookies=cookies, prefix="prj01-edit"
    )
    _seed_membership(project_id=project_id, user_id=member.user_id, role="viewer")

    post_form(
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
    project_id = create_project_via_ui(
        wsgi_app=handle.wsgi_app, cookies=cookies, prefix="prj01-remove"
    )
    _seed_membership(project_id=project_id, user_id=member.user_id, role="developer")

    post_form(
        wsgi_app=handle.wsgi_app,
        path="/projects/{}/members/{}/remove".format(project_id, member.user_id),
        cookies=cookies,
        fields={},
    )

    testbase.assert_equal(
        _member_role(project_id=project_id, user_id=member.user_id), None
    )
    return
