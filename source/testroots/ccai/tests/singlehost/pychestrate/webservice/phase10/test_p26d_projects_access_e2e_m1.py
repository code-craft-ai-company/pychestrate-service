"""
.. module:: test_p26d_projects_access_e2e_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests that project membership and the project-* roles give
               access to the Projects area (PRJ-17).

.. moduleauthor:: Code Craft AI LLC

Only system administrators could use Projects: the ``project-owner`` /
``project-editor`` / ``project-viewer`` roles offered on a user's page
granted nothing, and a project member without a system role got the
"no access yet" page because the Projects navigation required
``system:projects.read``.

Each test uses its own user, so role bindings never leak between tests
(or into the shared admin and viewer).
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import uuid

from typing import Any, Dict, List

from ccai import testbase

from ccai.tests.singlehost.pychestrate.webservice.phase10._e2e_harness import (
    drive_request,
    ensure_app,
    ensure_seeded_user,
    grant_role_to_user,
    logged_in_cookies,
    login_as,
)
from ccai.tests.singlehost.pychestrate.webservice.phase10._projects_ui_helpers import (
    create_project_via_ui,
    get_page,
    open_db_session,
)


def _navigation_groups(*, user_id: str) -> List[str]:
    """
        Call ``GET /api/v1/me/navigation``'s handler for ``user_id`` (the
        consumer-UI test app does not mount the REST surface) and return
        the group ids it offers.
    """
    from types import SimpleNamespace  # noqa: E402

    from ccai.pychestrate.webservice.security.auth.models import AuthProviderKind  # noqa: E402
    from ccai.pychestrate.webservice.security.auth.restapi.v1 import me_routes  # noqa: E402
    from ccai.pychestrate.webservice.security.auth.session_service import AuthPrincipal  # noqa: E402

    db_session = open_db_session()
    try:
        request = SimpleNamespace(
            path="/api/v1/me/navigation",
            db_session=db_session,
            auth_principal=AuthPrincipal(
                user_id=user_id, session_id="", provider_kind=AuthProviderKind.LOCAL,
                provider_name="local",
            ),
        )
        response = me_routes.handle_get_my_navigation(request)
        payload = json.loads(response.body)
    finally:
        db_session.close()
    rtnval = [group["group_id"] for group in payload.get("groups", [])]
    return rtnval


def _add_member(*, project_id: int, user_id: str, role: str) -> None:
    from ccai.pychestrate.core.orm import ProjectMember  # noqa: E402

    db_session = open_db_session()
    try:
        db_session.add(ProjectMember(project_id=project_id, user_id=uuid.UUID(user_id), role=role))
        db_session.commit()
    finally:
        db_session.close()
    return


def _admin_project(*, prefix: str) -> int:
    handle = ensure_app()
    cookies = logged_in_cookies(wsgi_app=handle.wsgi_app)
    rtnval = create_project_via_ui(wsgi_app=handle.wsgi_app, cookies=cookies, prefix=prefix)
    return rtnval


def _bind(
        *, user_id: str, role_name: str, scope_kind: str, inherits: bool = False,
        principal_kind: str = "USER", principal_id: Any = None
    ) -> None:
    """
        Bind ``role_name`` at ``scope_kind`` (SYSTEM or ORGANIZATION) to
        the user, or to the group ``principal_id`` when
        ``principal_kind`` is GROUP.
    """
    from ccai.pychestrate.webservice.security.rbac import cache as rbac_cache  # noqa: E402
    from ccai.pychestrate.webservice.security.rbac.models import (  # noqa: E402
        BindingScope,
        PrincipalKind,
        RbacRole,
        RbacRoleBinding,
        RoleSource,
    )

    db_session = open_db_session()
    try:
        role = db_session.query(RbacRole).filter(RbacRole.role_name == role_name).first()
        if role is None:
            role = RbacRole(
                role_id=uuid.uuid4(), role_name=role_name, source=RoleSource.BUILTIN,
                source_name=role_name, description="",
            )
            db_session.add(role)
            db_session.flush()
        db_session.add(RbacRoleBinding(
            binding_id=uuid.uuid4(),
            role_id=role.role_id,
            principal_kind=PrincipalKind(principal_kind),
            principal_id=principal_id if principal_id is not None else uuid.UUID(user_id),
            scope_kind=BindingScope(scope_kind),
            scope_id=uuid.uuid4() if scope_kind == "ORGANIZATION" else None,
            inherits_into_project=inherits,
        ))
        db_session.commit()
    finally:
        db_session.close()
    rbac_cache.invalidate_principal(principal_id=user_id)
    return


def _global_role(user_id: str) -> Any:
    from ccai.pychestrate.webservice.webinterface.blueprints.projects.project_access import (  # noqa: E402
        resolve_global_project_role,
    )

    db_session = open_db_session()
    try:
        rtnval = resolve_global_project_role(db_session=db_session, user_id=user_id)
    finally:
        db_session.close()
    return rtnval


# ---------------------------------------------------------------------------
# Global roles -> role on every project
# ---------------------------------------------------------------------------


def test_project_editor_role_gives_developer_on_every_project():
    """
    **Feature: projects access (PRJ-17)**
    **Property: a SYSTEM-scope project-editor binding resolves to the
    developer role on every project.**
    """
    ensure_app()
    user = ensure_seeded_user(login="e2e-prj17-editor-a")
    grant_role_to_user(user_id=user.user_id, role_name="project-editor")

    testbase.assert_equal(_global_role(user.user_id), "developer")
    return


def test_project_owner_role_gives_owner_on_every_project():
    """
    **Feature: projects access (PRJ-17)**
    **Property: a SYSTEM-scope project-owner binding resolves to owner.**
    """
    ensure_app()
    user = ensure_seeded_user(login="e2e-prj17-owner-a")
    grant_role_to_user(user_id=user.user_id, role_name="project-owner")

    testbase.assert_equal(_global_role(user.user_id), "owner")
    return


def test_system_admin_keeps_owner_access_to_every_project():
    """
    **Feature: projects access (PRJ-17)**
    **Property: system-admin (system:projects.write) resolves to owner, so
    system administrators keep full access to every project.**
    """
    ensure_app()
    user = ensure_seeded_user(login="e2e-prj17-sysadmin")
    grant_role_to_user(user_id=user.user_id, role_name="system-admin")

    testbase.assert_equal(_global_role(user.user_id), "owner")
    return


def test_a_group_binding_of_project_viewer_gives_viewer():
    """
    **Feature: projects access (PRJ-17)**
    **Property: a user in a group bound to project-viewer at SYSTEM scope
    resolves to viewer.**
    """
    from ccai.pychestrate.webservice.identity.users.models import (  # noqa: E402
        IdentityGroup,
        IdentityGroupMembership,
    )

    ensure_app()
    user = ensure_seeded_user(login="e2e-prj17-grouped")
    group_id = uuid.uuid4()
    db_session = open_db_session()
    try:
        db_session.add(IdentityGroup(group_id=group_id, group_name="prj17-readers-{}".format(group_id.hex[:6])))
        db_session.flush()
        db_session.add(IdentityGroupMembership(group_id=group_id, user_id=uuid.UUID(user.user_id)))
        db_session.commit()
    finally:
        db_session.close()
    _bind(user_id=user.user_id, role_name="project-viewer", scope_kind="SYSTEM",
          principal_kind="GROUP", principal_id=group_id)

    testbase.assert_equal(_global_role(user.user_id), "viewer")
    return


def test_an_organization_binding_counts_only_when_it_inherits_into_projects():
    """
    **Feature: projects access (PRJ-17)**
    **Property: an ORGANIZATION-scope project-editor binding without
    inherits_into_project gives no project access.**
    """
    ensure_app()
    user = ensure_seeded_user(login="e2e-prj17-org-no-inherit")
    _bind(user_id=user.user_id, role_name="project-editor", scope_kind="ORGANIZATION", inherits=False)

    testbase.assert_equal(_global_role(user.user_id), None)
    return


def test_an_inheriting_organization_binding_gives_the_role():
    """
    **Feature: projects access (PRJ-17)**
    **Property: an ORGANIZATION-scope project-editor binding with
    inherits_into_project resolves to developer.**
    """
    ensure_app()
    user = ensure_seeded_user(login="e2e-prj17-org-inherit")
    _bind(user_id=user.user_id, role_name="project-editor", scope_kind="ORGANIZATION", inherits=True)

    testbase.assert_equal(_global_role(user.user_id), "developer")
    return


def test_a_user_without_roles_has_no_global_project_role():
    """
    **Feature: projects access (PRJ-17)**
    **Property: a user with no role bindings resolves to no global role.**
    """
    ensure_app()
    user = ensure_seeded_user(login="e2e-prj17-plain")

    testbase.assert_equal(_global_role(user.user_id), None)
    return


# ---------------------------------------------------------------------------
# Navigation: the Projects area is shown to everyone with project access
# ---------------------------------------------------------------------------


def test_a_project_editor_sees_projects_in_the_navigation():
    """
    **Feature: projects access (PRJ-17)**
    **Property: a user whose only role is project-editor gets the Projects
    group from /api/v1/me/navigation (it used to return no groups, and
    the shell showed "no access yet").**
    """
    ensure_app()
    user = ensure_seeded_user(login="e2e-prj17-editor-nav")
    grant_role_to_user(user_id=user.user_id, role_name="project-editor")

    groups = _navigation_groups(user_id=user.user_id)

    testbase.assert_equal("projects" in groups, True)
    return


def test_a_project_member_without_roles_sees_projects_in_the_navigation():
    """
    **Feature: projects access (PRJ-17)**
    **Property: a user with no role but a membership in one project gets
    the Projects group from /api/v1/me/navigation.**
    """
    ensure_app()
    user = ensure_seeded_user(login="e2e-prj17-member-nav")
    project_id = _admin_project(prefix="prj17-nav")
    _add_member(project_id=project_id, user_id=user.user_id, role="developer")

    groups = _navigation_groups(user_id=user.user_id)

    testbase.assert_equal("projects" in groups, True)
    return


def test_a_user_without_project_access_gets_no_projects_navigation():
    """
    **Feature: projects access (PRJ-17)**
    **Property: a user with no role and no membership still gets no
    Projects group (the "no access yet" state stays genuine).**
    """
    ensure_app()
    user = ensure_seeded_user(login="e2e-prj17-nobody-nav")

    groups = _navigation_groups(user_id=user.user_id)

    testbase.assert_equal("projects" in groups, False)
    return


# ---------------------------------------------------------------------------
# Project pages
# ---------------------------------------------------------------------------


def test_a_project_editor_can_open_a_project_they_are_not_a_member_of():
    """
    **Feature: projects access (PRJ-17)**
    **Property: GET /projects/{id} renders for a project-editor who is not
    a member of the project.**
    """
    handle = ensure_app()
    user = ensure_seeded_user(login="e2e-prj17-editor-page")
    grant_role_to_user(user_id=user.user_id, role_name="project-editor")
    project_id = _admin_project(prefix="prj17-page")
    cookies = login_as(wsgi_app=handle.wsgi_app, user=user)

    page = get_page(wsgi_app=handle.wsgi_app, path="/projects/{}".format(project_id), cookies=cookies)

    testbase.assert_equal(page.status_code, 200)
    return


def test_a_member_without_roles_can_open_their_project():
    """
    **Feature: projects access (PRJ-17)**
    **Property: GET /projects/{id} renders for a member who holds no role
    binding at all.**
    """
    handle = ensure_app()
    user = ensure_seeded_user(login="e2e-prj17-member-page")
    project_id = _admin_project(prefix="prj17-member")
    _add_member(project_id=project_id, user_id=user.user_id, role="viewer")
    cookies = login_as(wsgi_app=handle.wsgi_app, user=user)

    page = get_page(wsgi_app=handle.wsgi_app, path="/projects/{}".format(project_id), cookies=cookies)

    testbase.assert_equal(page.status_code, 200)
    return


def test_a_user_without_access_is_turned_away_from_a_project():
    """
    **Feature: projects access (PRJ-17)**
    **Property: GET /projects/{id} redirects a user who is neither a member
    nor holds a project role.**
    """
    handle = ensure_app()
    user = ensure_seeded_user(login="e2e-prj17-outsider-page")
    project_id = _admin_project(prefix="prj17-closed")
    cookies = login_as(wsgi_app=handle.wsgi_app, user=user)

    response = drive_request(
        wsgi_app=handle.wsgi_app, method="GET", path="/projects/{}".format(project_id), cookies=cookies,
    )

    testbase.assert_equal(response.status_code in (302, 303), True)
    return


def test_members_page_lists_people_with_a_global_project_role():
    """
    **Feature: projects access (PRJ-17)**
    **Property: the Members page shows, under "Access through global
    roles", a user who holds project-editor, so it is visible who can
    open the project without being a member.**
    """
    handle = ensure_app()
    user = ensure_seeded_user(login="e2e-prj17-listed-editor")
    grant_role_to_user(user_id=user.user_id, role_name="project-editor")
    project_id = _admin_project(prefix="prj17-members")
    cookies = logged_in_cookies(wsgi_app=handle.wsgi_app)

    page = get_page(
        wsgi_app=handle.wsgi_app, path="/projects/{}/members".format(project_id), cookies=cookies,
    )

    global_section = page.text.split("Access through global roles", 1)[-1]
    testbase.assert_equal(user.login in global_section, True)
    return
