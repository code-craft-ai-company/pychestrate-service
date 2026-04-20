"""
.. module:: test_rbac_evaluator
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for 1-rbac catalog + evaluator.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import uuid as uuidmod

from datetime import datetime, timezone

from automojo import testbase

from automojo.errors.exceptions import SemanticError

from automojo.pychestrate.core.defaults import new_uuid

from automojo.pychestrate.webservice.security.auth.models import AuthProviderKind
from automojo.pychestrate.webservice.security.auth.session_service import AuthPrincipal
from automojo.pychestrate.webservice.security.rbac import catalog, rbac_evaluator
from automojo.pychestrate.webservice.security.rbac.exceptions import AuthorizationError
from automojo.pychestrate.webservice.security.rbac.models import (
    BindingScope,
    PermissionEffect,
    PrincipalKind,
    RbacRole,
    RbacRoleBinding,
    RoleSource,
)

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
    reset_phase1_runtime,
)


def _build_principal(user_id: str) -> AuthPrincipal:
    rtnval = AuthPrincipal(
        user_id=user_id,
        session_id="test-session",
        provider_kind=AuthProviderKind.LOCAL,
        provider_name="local",
    )
    return rtnval


def _bind_role(*, session, role_name: str, user_id: str) -> None:
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


def test_catalog_loads_core_permissions_and_roles():
    """
    **Feature: 1-rbac**
    **Property: load_catalog_from_registry returns the core permission
    keys and the SystemAdminRole + AuditorRole presets.**
    """
    reset_phase1_runtime()
    snapshot = catalog.load_catalog_from_registry()

    testbase.assert_equal("system:users.write" in snapshot.permissions, True)
    testbase.assert_equal("system:rbac.admin" in snapshot.permissions, True)
    testbase.assert_equal("system:audit.read" in snapshot.permissions, True)
    testbase.assert_equal("system-admin" in snapshot.roles, True)
    testbase.assert_equal("auditor" in snapshot.roles, True)
    return


def test_check_permission_allow_via_binding():
    """
    **Feature: 1-rbac**
    **Property: A principal bound to SystemAdminRole is allowed.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()

    user_id = str(uuidmod.uuid4())
    _bind_role(session=session, role_name="system-admin", user_id=user_id)

    decision = rbac_evaluator.check_permission(
        db_session=session,
        principal=_build_principal(user_id),
        permission_key="system:users.write",
        now=datetime.now(timezone.utc),
    )

    testbase.assert_equal(decision.allowed, True)
    testbase.assert_equal(decision.reason, "binding_allow")
    return


def test_check_permission_unknown_key_denies():
    """
    **Feature: 1-rbac**
    **Property: A well-formed but unregistered key denies with
    reason=unknown_permission_key.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()

    decision = rbac_evaluator.check_permission(
        db_session=session,
        principal=_build_principal(str(uuidmod.uuid4())),
        permission_key="system:does.not.exist",
        now=datetime.now(timezone.utc),
    )

    testbase.assert_equal(decision.allowed, False)
    testbase.assert_equal(decision.reason, "unknown_permission_key")
    return


def test_check_permission_malformed_raises_semantic_error():
    """
    **Feature: 1-rbac**
    **Property: A permission_key without ':' raises SemanticError.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()

    raised = False
    try:
        rbac_evaluator.check_permission(
            db_session=session,
            principal=_build_principal(str(uuidmod.uuid4())),
            permission_key="no_namespace",
            now=datetime.now(timezone.utc),
        )
    except SemanticError:
        raised = True

    testbase.assert_equal(raised, True)
    return


def test_require_permission_raises_authorization_error():
    """
    **Feature: 1-rbac**
    **Property: require_permission raises AuthorizationError on deny.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()

    raised = False
    try:
        rbac_evaluator.require_permission(
            db_session=session,
            principal=_build_principal(str(uuidmod.uuid4())),
            permission_key="system:users.write",
            now=datetime.now(timezone.utc),
        )
    except AuthorizationError as xcpt:
        raised = True
        testbase.assert_equal("PERMISSION: system:users.write" in str(xcpt), True)

    testbase.assert_equal(raised, True)
    return


def test_deny_beats_allow():
    """
    **Feature: 1-rbac**
    **Property: When a principal carries both ALLOW and DENY for the same
    key, DENY wins.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()

    user_id = str(uuidmod.uuid4())

    allow_role = RbacRole(
        role_id=new_uuid(),
        role_name="system-admin",
        source=RoleSource.BUILTIN,
        source_name="CorePermissionExtension",
        description="",
    )
    session.add(allow_role)
    session.flush()
    session.add(RbacRoleBinding(
        binding_id=new_uuid(),
        role_id=allow_role.role_id,
        principal_kind=PrincipalKind.USER,
        principal_id=user_id,
        scope_kind=BindingScope.SYSTEM,
        scope_id=None,
        inherits_into_project=False,
        created_by=None,
    ))

    # Register an ephemeral deny role pack via a transient RoleExtension class.
    from automojo.pychestrate.webservice.extensions.registry import register_resource_extension
    from automojo.pychestrate.webservice.security.rbac.extensions.role_extension import (
        PermissionGrant, RoleExtension,
    )

    class _DenyAllWritesRole(RoleExtension):
        resource_extension_name: str = "role_extension"
        role_name: str = "deny-users-write"
        description: str = "Explicit deny override for users.write"
        permissions: tuple = (
            PermissionGrant(permission_key="system:users.write", effect=PermissionEffect.DENY),
        )

    register_resource_extension(base_class=RoleExtension, extension=_DenyAllWritesRole)

    deny_role = RbacRole(
        role_id=new_uuid(),
        role_name="deny-users-write",
        source=RoleSource.BUILTIN,
        source_name="test_fixture",
        description="",
    )
    session.add(deny_role)
    session.flush()
    session.add(RbacRoleBinding(
        binding_id=new_uuid(),
        role_id=deny_role.role_id,
        principal_kind=PrincipalKind.USER,
        principal_id=user_id,
        scope_kind=BindingScope.SYSTEM,
        scope_id=None,
        inherits_into_project=False,
        created_by=None,
    ))
    session.commit()

    decision = rbac_evaluator.check_permission(
        db_session=session,
        principal=_build_principal(user_id),
        permission_key="system:users.write",
        now=datetime.now(timezone.utc),
    )

    testbase.assert_equal(decision.allowed, False)
    testbase.assert_equal(decision.reason, "explicit_deny")
    return


def test_unbound_project_user_is_denied():
    """
    **Feature: 1-rbac (M2)**
    **Property: A user with no PROJECT-scope binding is denied for
    project-scoped keys.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()

    project_id = str(uuidmod.uuid4())
    decision = rbac_evaluator.check_permission(
        db_session=session,
        principal=_build_principal(str(uuidmod.uuid4())),
        permission_key="project:{}:runs.dispatch".format(project_id),
        now=datetime.now(timezone.utc),
    )

    testbase.assert_equal(decision.allowed, False)
    testbase.assert_equal(decision.reason, "no_matching_binding")
    return
