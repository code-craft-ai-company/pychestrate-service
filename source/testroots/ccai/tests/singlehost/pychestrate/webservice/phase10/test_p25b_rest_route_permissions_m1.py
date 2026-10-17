"""
.. module:: test_p25b_rest_route_permissions_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for route-level REST permission enforcement
               (:mod:`api.rest_authz`) and the permission each
               wrapped REST route declares.

.. moduleauthor:: Code Craft AI LLC

Audit finding LD-12: several REST route modules never checked a
permission, so any caller -- including an anonymous one -- could
create projects, mint enrollment tokens, write feature flags, or
read the audit log. :func:`api.rest_authz.require_rest_permission`
now wraps those handlers at registration time.

Coverage:

* :func:`permission_denial` -- 401 without a principal, 403 without
  the permission (evaluated by the real RBAC evaluator against an
  in-memory database), pass-through with it, 503 without a database
  session, and fail-closed when the evaluator raises.
* :func:`require_rest_permission` -- a denied caller never reaches
  the handler; the wrapper advertises its key.
* The route matrix -- each wrapped module registers every route
  with the documented permission, and every declared key exists in
  the RBAC catalog.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import uuid

from typing import Any, Dict, List, Optional, Tuple

from ccai import testbase
from ccai.testbase.mocking import create_module_patch

from ccai.pychestrate.core.defaults import new_uuid

from ccai.pychestrate.webservice.api.rest_authz import (
    AUTHENTICATED_ONLY,
    permission_denial,
    require_rest_permission,
)
from ccai.pychestrate.webservice.security.auth.models import AuthProviderKind
from ccai.pychestrate.webservice.security.auth.session_service import AuthPrincipal
from ccai.pychestrate.webservice.security.rbac import catalog, rbac_evaluator
from ccai.pychestrate.webservice.security.rbac.models import (
    BindingScope,
    PrincipalKind,
    RbacRole,
    RbacRoleBinding,
    RoleSource,
)

from ccai.pychestrate.webservice.audit.restapi.v1 import audit_routes
from ccai.pychestrate.webservice.clients.restapi.v1 import enrollment_routes
from ccai.pychestrate.webservice.identity.flags.restapi.v1 import flags_routes
from ccai.pychestrate.webservice.identity.users.restapi.v1 import users_routes
from ccai.pychestrate.webservice.notifications.restapi.v1 import channels_routes
from ccai.pychestrate.webservice.project_templates.restapi.v1 import templates_routes
from ccai.pychestrate.webservice.projects.restapi.v1 import projects_routes
from ccai.pychestrate.webservice.retention.restapi.v1 import retention_routes
from ccai.pychestrate.webservice.tagging.restapi.v1 import tags_routes
from ccai.pychestrate.webservice.variables.restapi.v1 import variables_routes

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
    reset_phase1_runtime,
)
from ccai.tests.singlehost.pychestrate.webservice.shared.webworks_test_harness import (
    make_fake_app,
)


VERSION_PREFIX = "/api/v1"
PERMISSION_UNDER_TEST = "system:audit.read"


# ---------------------------------------------------------------------------
# Stubs + helpers
# ---------------------------------------------------------------------------


class _FakeRequest:
    """
        The attributes the session middleware attaches and the
        wrapper reads: ``path``, ``auth_principal``, ``db_session``.
    """

    def __init__(
        self,
        *,
        auth_principal: Optional[Any] = None,
        db_session: Optional[Any] = None,
        path: str = "/api/v1/audit",
    ) -> None:
        self.path: str = path
        self.auth_principal: Optional[Any] = auth_principal
        self.db_session: Optional[Any] = db_session
        return


class _RecordingHandler:
    """
        Route handler stand-in that records each call and answers
        with a fixed marker.
    """

    def __init__(self) -> None:
        self.calls: List[Any] = []
        return

    def __call__(self, request: Any) -> str:
        self.calls.append(request)
        return "handler-ran"


def _principal(user_id: str) -> AuthPrincipal:
    rtnval = AuthPrincipal(
        user_id=user_id,
        session_id="test-session",
        provider_kind=AuthProviderKind.LOCAL,
        provider_name="local",
    )
    return rtnval


def _bind_role(*, session: Any, role_name: str, user_id: str) -> None:
    role = RbacRole(
        role_id=new_uuid(),
        role_name=role_name,
        source=RoleSource.BUILTIN,
        source_name="CorePermissionExtension",
        description="",
    )
    session.add(role)
    session.flush()
    binding = RbacRoleBinding(
        binding_id=new_uuid(),
        role_id=role.role_id,
        principal_kind=PrincipalKind.USER,
        principal_id=user_id,
        scope_kind=BindingScope.SYSTEM,
        scope_id=None,
        inherits_into_project=False,
        created_by=None,
    )
    session.add(binding)
    session.commit()
    return


def _problem_body(response: Any) -> Dict[str, Any]:
    rtnval = json.loads(response.body.decode("utf-8"))
    return rtnval


def _declared_permissions(
        *, registrar: Any
    ) -> Dict[Tuple[str, str], Optional[str]]:
    """
        Register a REST module on a fake app and map each
        ``(method, path)`` to the permission its handler declares.
        Handlers left unwrapped map to ``"<unwrapped>"``.
    """
    app = make_fake_app()
    registrar(app=app, version_prefix=VERSION_PREFIX)
    rtnval: Dict[Tuple[str, str], Optional[str]] = {}
    for path, methods, handler in app.calls:
        for method in methods:
            rtnval[(method, path)] = getattr(
                handler, "required_permission", "<unwrapped>"
            )
    return rtnval


_ALL_REGISTRARS: Tuple[Any, ...] = (
    projects_routes.register_projects_routes,
    enrollment_routes.register_enrollment_routes,
    audit_routes.register_audit_routes,
    users_routes.register_users_routes,
    flags_routes.register_flags_routes,
    channels_routes.register_channels_routes,
    retention_routes.register_retention_routes,
    tags_routes.register_tags_routes,
    variables_routes.register_variables_routes,
    templates_routes.register_templates_routes,
)


# ===========================================================================
# permission_denial
# ===========================================================================


def test_permission_denial_answers_401_without_a_principal():
    """
    **Feature: REST route permissions (LD-12)**
    **Property: a request with no auth_principal is refused with a
    401 problem document before any permission is evaluated.**
    """
    denial = permission_denial(
        request=_FakeRequest(auth_principal=None),
        permission_key=PERMISSION_UNDER_TEST,
    )
    testbase.assert_equal(denial.status_code, 401)
    return


def test_permission_denial_lets_any_principal_through_authenticated_only_routes():
    """
    **Feature: REST route permissions (LD-12)**
    **Property: with AUTHENTICATED_ONLY, any signed-in principal may
    proceed; no database session or permission is needed.**
    """
    denial = permission_denial(
        request=_FakeRequest(auth_principal=_principal(str(uuid.uuid4()))),
        permission_key=AUTHENTICATED_ONLY,
    )
    testbase.assert_equal(denial, None)
    return


def test_permission_denial_answers_403_when_rbac_denies():
    """
    **Feature: REST route permissions (LD-12)**
    **Property: a signed-in principal with no role binding is
    refused with a 403 whose problem document names the required
    permission (decided by the real RBAC evaluator).**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()
    try:
        denial = permission_denial(
            request=_FakeRequest(
                auth_principal=_principal(str(uuid.uuid4())),
                db_session=session,
            ),
            permission_key=PERMISSION_UNDER_TEST,
        )
        testbase.assert_equal(
            (denial.status_code, _problem_body(denial).get("required_permission")),
            (403, PERMISSION_UNDER_TEST),
        )
    finally:
        session.close()
    return


def test_permission_denial_allows_a_principal_holding_the_permission():
    """
    **Feature: REST route permissions (LD-12)**
    **Property: a principal bound to system-admin passes the check
    (the real RBAC evaluator allows), so the handler may run.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()
    try:
        user_id = str(uuid.uuid4())
        _bind_role(session=session, role_name="system-admin", user_id=user_id)
        denial = permission_denial(
            request=_FakeRequest(
                auth_principal=_principal(user_id), db_session=session,
            ),
            permission_key=PERMISSION_UNDER_TEST,
        )
        testbase.assert_equal(denial, None)
    finally:
        session.close()
    return


def test_permission_denial_answers_503_without_a_database_session():
    """
    **Feature: REST route permissions (LD-12)**
    **Property: when the permission cannot be evaluated because the
    request carries no database session, the request is refused
    with a 503 rather than allowed.**
    """
    denial = permission_denial(
        request=_FakeRequest(
            auth_principal=_principal(str(uuid.uuid4())), db_session=None,
        ),
        permission_key=PERMISSION_UNDER_TEST,
    )
    testbase.assert_equal(denial.status_code, 503)
    return


def test_permission_denial_fails_closed_when_the_evaluator_raises():
    """
    **Feature: REST route permissions (LD-12)**
    **Property: an exception inside the RBAC evaluator counts as a
    denial (403), never as permission.**
    """

    def _raise(**kwargs: Any) -> Any:
        raise RuntimeError("evaluator unavailable")

    patch = create_module_patch(rbac_evaluator, "check_permission")
    mock = patch.activate()
    mock.configure(side_effect=_raise)
    try:
        denial = permission_denial(
            request=_FakeRequest(
                auth_principal=_principal(str(uuid.uuid4())),
                db_session=object(),
            ),
            permission_key=PERMISSION_UNDER_TEST,
        )
    finally:
        patch.deactivate()
    testbase.assert_equal(denial.status_code, 403)
    return


# ===========================================================================
# require_rest_permission
# ===========================================================================


def test_wrapped_handler_is_not_called_for_a_refused_caller():
    """
    **Feature: REST route permissions (LD-12)**
    **Property: when the caller is refused, the wrapped handler
    never runs and the wrapper returns the refusal.**
    """
    handler = _RecordingHandler()
    wrapped = require_rest_permission(handler, permission_key=PERMISSION_UNDER_TEST)

    response = wrapped(_FakeRequest(auth_principal=None))

    testbase.assert_equal((response.status_code, len(handler.calls)), (401, 0))
    return


def test_wrapped_handler_runs_for_an_allowed_caller():
    """
    **Feature: REST route permissions (LD-12)**
    **Property: when the caller may proceed, the wrapper returns the
    handler's own response.**
    """
    handler = _RecordingHandler()
    wrapped = require_rest_permission(handler, permission_key=AUTHENTICATED_ONLY)

    response = wrapped(_FakeRequest(auth_principal=_principal(str(uuid.uuid4()))))

    testbase.assert_equal(response, "handler-ran")
    return


def test_wrapped_handler_advertises_its_required_permission():
    """
    **Feature: REST route permissions (LD-12)**
    **Property: the wrapper exposes the key it enforces as
    ``required_permission`` so route inventories can read it.**
    """
    wrapped = require_rest_permission(
        _RecordingHandler(), permission_key=PERMISSION_UNDER_TEST
    )
    testbase.assert_equal(wrapped.required_permission, PERMISSION_UNDER_TEST)
    return


# ===========================================================================
# Route matrix
# ===========================================================================


def test_projects_routes_declare_documented_permissions():
    """
    **Feature: REST route permissions (LD-12)**
    **Property: project writes need projects.write, reads need
    projects.read, and membership changes need
    projects.members.manage. The list route keeps its own in-handler
    check (it filters by membership).**
    """
    base = VERSION_PREFIX + "/projects"
    expected = {
        ("GET", base): "<unwrapped>",
        ("POST", base): "system:projects.write",
        ("GET", base + "/{slug}"): "system:projects.read",
        ("PATCH", base + "/{slug}"): "system:projects.write",
        ("DELETE", base + "/{slug}"): "system:projects.write",
        ("POST", base + "/{slug}/archive"): "system:projects.write",
        ("POST", base + "/{slug}/unarchive"): "system:projects.write",
        ("GET", base + "/{slug}/members"): "system:projects.read",
        ("POST", base + "/{slug}/members"): "system:projects.members.manage",
        ("DELETE", base + "/{slug}/members/{user_id}"): "system:projects.members.manage",
        ("DELETE", base + "/{slug}/members/{user_id}/{role_name}"): "system:projects.members.manage",
    }
    testbase.assert_equal(
        _declared_permissions(registrar=projects_routes.register_projects_routes),
        expected,
    )
    return


def test_enrollment_routes_declare_documented_permissions():
    """
    **Feature: REST route permissions (LD-12)**
    **Property: listing enrollment tokens needs clients.read; minting
    and revoking need clients.write; redeem stays unwrapped because
    the one-time token in the body is its credential.**
    """
    base = VERSION_PREFIX + "/enrollment-tokens"
    expected = {
        ("GET", base): "system:clients.read",
        ("POST", base): "system:clients.write",
        ("POST", base + "/redeem"): "<unwrapped>",
        ("POST", base + "/clients/{client_id}/revoke"): "system:clients.write",
        ("DELETE", base + "/{token_id}"): "system:clients.write",
    }
    testbase.assert_equal(
        _declared_permissions(registrar=enrollment_routes.register_enrollment_routes),
        expected,
    )
    return


def test_audit_routes_declare_documented_permissions():
    """
    **Feature: REST route permissions (LD-12)**
    **Property: both audit-log routes need audit.read.**
    """
    base = VERSION_PREFIX + "/audit"
    expected = {
        ("GET", base): "system:audit.read",
        ("GET", base + "/{sequence_number:int}"): "system:audit.read",
    }
    testbase.assert_equal(
        _declared_permissions(registrar=audit_routes.register_audit_routes),
        expected,
    )
    return


def test_identity_users_routes_declare_documented_permissions():
    """
    **Feature: REST route permissions (LD-12)**
    **Property: creating a user, deactivating, reactivating and anonymising one
    need users.write; reading one and listing them (the picker list) need
    users.read.**
    """
    base = VERSION_PREFIX + "/identity/users"
    expected = {
        ("GET", base): "system:users.read",
        ("POST", base): "system:users.write",
        ("GET", base + "/{user_id}"): "system:users.read",
        ("POST", base + "/{user_id}/deactivate"): "system:users.write",
        ("POST", base + "/{user_id}/reactivate"): "system:users.write",
        ("POST", base + "/{user_id}/anonymise"): "system:users.write",
        ("DELETE", base + "/{user_id}"): "system:users.write",
    }
    testbase.assert_equal(
        _declared_permissions(registrar=users_routes.register_users_routes),
        expected,
    )
    return


def test_flags_routes_declare_documented_permissions():
    """
    **Feature: REST route permissions (LD-12)**
    **Property: flag administration (backends, create, update,
    retire, history) needs flags.admin; listing, reading, and
    evaluating flags needs only a signed-in caller.**
    """
    base = VERSION_PREFIX + "/flags"
    expected = {
        ("GET", base + "/backends"): "system:flags.admin",
        ("GET", base): AUTHENTICATED_ONLY,
        ("POST", base): "system:flags.admin",
        ("GET", base + "/{flag_key}"): AUTHENTICATED_ONLY,
        ("PATCH", base + "/{flag_key}"): "system:flags.admin",
        ("POST", base + "/{flag_key}/retire"): "system:flags.admin",
        ("GET", base + "/{flag_key}/history"): "system:flags.admin",
        ("POST", base + "/{flag_key}/evaluate"): AUTHENTICATED_ONLY,
    }
    testbase.assert_equal(
        _declared_permissions(registrar=flags_routes.register_flags_routes),
        expected,
    )
    return


def test_notification_channel_routes_declare_documented_permissions():
    """
    **Feature: REST route permissions (LD-12)**
    **Property: reading notification channels needs the notifications read
    key and every change (create, change, delete, send a test) the write key
    (channels carry delivery endpoints and credentials, so both are
    administrative).**
    """
    base = VERSION_PREFIX + "/notifications/channels"
    expected = {
        ("GET", base): "system:notifications.read",
        ("POST", base): "system:notifications.write",
        ("GET", base + "/{channel_id}"): "system:notifications.read",
        ("PATCH", base + "/{channel_id}"): "system:notifications.write",
        ("DELETE", base + "/{channel_id}"): "system:notifications.write",
        ("POST", base + "/{channel_id}/test"): "system:notifications.write",
    }
    testbase.assert_equal(
        _declared_permissions(registrar=channels_routes.register_channels_routes),
        expected,
    )
    return


def test_retention_routes_declare_documented_permissions():
    """
    **Feature: REST route permissions (LD-12)**
    **Property: creating and publishing retention policies needs the
    admin view key; reading them needs only a signed-in caller.**
    """
    base = VERSION_PREFIX + "/retention/policies"
    expected = {
        ("GET", base): AUTHENTICATED_ONLY,
        ("POST", base): "system:ui.admin.view",
        ("GET", base + "/{policy_id}"): AUTHENTICATED_ONLY,
        ("POST", base + "/{policy_id}/publish"): "system:ui.admin.view",
    }
    testbase.assert_equal(
        _declared_permissions(registrar=retention_routes.register_retention_routes),
        expected,
    )
    return


def test_tags_routes_declare_documented_permissions():
    """
    **Feature: REST route permissions (LD-12)**
    **Property: assigning and removing tags needs the admin view
    key; searching and listing tags needs only a signed-in caller.**
    """
    base = VERSION_PREFIX + "/tags"
    expected = {
        ("GET", base + "/search"): AUTHENTICATED_ONLY,
        ("GET", base + "/taxonomies"): AUTHENTICATED_ONLY,
        ("POST", base + "/{entity_kind}/{entity_id}"): "system:ui.admin.view",
        ("GET", base + "/{entity_kind}/{entity_id}"): AUTHENTICATED_ONLY,
        ("DELETE", base + "/{entity_kind}/{entity_id}/{tag:path}"): "system:ui.admin.view",
    }
    testbase.assert_equal(
        _declared_permissions(registrar=tags_routes.register_tags_routes),
        expected,
    )
    return


def test_variables_routes_declare_documented_permissions():
    """
    **Feature: REST route permissions (LD-12)**
    **Property: every variables route needs the admin view key.**
    """
    base = VERSION_PREFIX + "/variables"
    expected = {
        ("GET", base + "/effective"): "system:ui.admin.view",
        ("GET", base + "/{scope}/{scope_id}"): "system:ui.admin.view",
        ("GET", base + "/{scope}/{scope_id}/{name}"): "system:ui.admin.view",
        ("PUT", base + "/{scope}/{scope_id}/{name}"): "system:ui.admin.view",
        ("DELETE", base + "/{scope}/{scope_id}/{name}"): "system:ui.admin.view",
    }
    testbase.assert_equal(
        _declared_permissions(registrar=variables_routes.register_variables_routes),
        expected,
    )
    return


def test_project_template_routes_declare_documented_permissions():
    """
    **Feature: REST route permissions (LD-12)**
    **Property: the read-only project-template catalog needs only a
    signed-in caller.**
    """
    base = VERSION_PREFIX + "/project-templates"
    expected = {
        ("GET", base): AUTHENTICATED_ONLY,
        ("GET", base + "/{template_id}"): AUTHENTICATED_ONLY,
    }
    testbase.assert_equal(
        _declared_permissions(registrar=templates_routes.register_templates_routes),
        expected,
    )
    return


def test_every_declared_rest_permission_exists_in_the_rbac_catalog():
    """
    **Feature: REST route permissions (LD-12)**
    **Property: every permission key a wrapped REST route declares
    is registered in the RBAC catalog, so no route is locked behind
    a misspelled key that nobody can hold.**
    """
    reset_phase1_runtime()
    known = set(catalog.load_catalog_from_registry().permissions)

    unknown: List[Tuple[str, str, str]] = []
    for registrar in _ALL_REGISTRARS:
        for (method, path), key in _declared_permissions(registrar=registrar).items():
            if key in (AUTHENTICATED_ONLY, "<unwrapped>"):
                continue
            if key not in known:
                unknown.append((method, path, key))
    testbase.assert_equal(unknown, [])
    return
