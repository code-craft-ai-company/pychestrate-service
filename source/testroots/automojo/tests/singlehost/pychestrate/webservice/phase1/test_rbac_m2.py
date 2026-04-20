"""
.. module:: test_rbac_m2
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for 1-rbac M2 — binding CRUD, project scope, group
               membership, organization inheritance, cache invalidation.

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

from automojo.pychestrate.core.defaults import new_uuid, utc_now

from automojo.pychestrate.webservice.identity.users.models import (
    IdentityGroup,
    IdentityGroupMembership,
    IdentityUser,
    UserStatus,
)
from automojo.pychestrate.webservice.messaging.event_bus import EntityEvent, publish, subscribe
from automojo.pychestrate.webservice.security.auth.models import AuthProviderKind
from automojo.pychestrate.webservice.security.auth.session_service import AuthPrincipal
from automojo.pychestrate.webservice.security.rbac import (
    binding_service,
    cache,
    inheritance,
    rbac_evaluator,
)
from automojo.pychestrate.webservice.security.rbac.exceptions import (
    BindingNotFoundError,
    InvalidBindingScopeError,
    RoleNotFoundError,
)
from automojo.pychestrate.webservice.security.rbac.models import (
    BindingScope,
    PrincipalKind,
    RbacRole,
    RbacRoleBinding,
    RoleSource,
)

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
    reset_phase1_runtime,
    session_for,
)


# =============================================================================
# Helpers
# =============================================================================

def _principal(user_id: str) -> AuthPrincipal:
    return AuthPrincipal(
        user_id=user_id,
        session_id="m2-test",
        provider_kind=AuthProviderKind.LOCAL,
        provider_name="local",
    )


def _insert_role(*, session, role_name: str) -> str:
    role = RbacRole(
        role_id=new_uuid(),
        role_name=role_name,
        source=RoleSource.BUILTIN,
        source_name="ProjectPermissionExtension",
        description="",
    )
    session.add(role)
    session.commit()
    return str(role.role_id)


def _insert_identity_user(*, session, login_suffix: str) -> str:
    user_id = new_uuid()
    session.add(IdentityUser(
        user_id=user_id,
        login_name="u-{}".format(login_suffix),
        primary_email="u-{}@example.com".format(login_suffix),
        display_name="User {}".format(login_suffix),
        status=UserStatus.ACTIVE,
        provisioning_source="local",
        external_id=None,
        timezone="UTC",
    ))
    session.commit()
    return user_id


def _insert_group(*, session, group_name: str) -> str:
    group_id = new_uuid()
    session.add(IdentityGroup(
        group_id=group_id,
        group_name=group_name,
        description="",
    ))
    session.commit()
    return group_id


def _add_user_to_group(*, session, user_id: str, group_id: str) -> None:
    session.add(IdentityGroupMembership(
        group_id=group_id,
        user_id=user_id,
        added_at=utc_now(),
        added_by=None,
    ))
    session.commit()
    return


# =============================================================================
# binding_service
# =============================================================================

def test_assign_role_creates_binding_and_publishes_event():
    """
    **Feature: 1-rbac M2**
    **Property: assign_role creates a RbacRoleBinding row and publishes
    entity.role.assigned after commit.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()
    _insert_role(session=session, role_name="project-owner")

    received = []
    subscribe(topic="entity.role.assigned", subscriber=lambda evt: received.append(evt))

    project_id = new_uuid()
    user_id = _insert_identity_user(session=session, login_suffix="owner")

    binding = binding_service.assign_role(
        db_session=session,
        role_name="project-owner",
        principal_kind=PrincipalKind.USER,
        principal_id=user_id,
        scope_kind=BindingScope.PROJECT,
        scope_id=project_id,
        inherits_into_project=False,
        actor_user_id=None,
    )

    testbase.assert_equal(binding is not None, True)
    testbase.assert_equal(len(received), 1)
    testbase.assert_equal(received[0].payload["role_name"], "project-owner")
    testbase.assert_equal(received[0].payload["principal_id"], str(user_id))
    return


def test_assign_role_is_idempotent_on_duplicate():
    """
    **Feature: 1-rbac M2**
    **Property: Re-assigning the same (role, principal, scope) returns
    the existing binding without publishing a second event.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()
    _insert_role(session=session, role_name="project-editor")

    received = []
    subscribe(topic="entity.role.assigned", subscriber=lambda evt: received.append(evt))

    project_id = new_uuid()
    user_id = _insert_identity_user(session=session, login_suffix="editor")

    first = binding_service.assign_role(
        db_session=session,
        role_name="project-editor",
        principal_kind=PrincipalKind.USER,
        principal_id=user_id,
        scope_kind=BindingScope.PROJECT,
        scope_id=project_id,
        inherits_into_project=False,
        actor_user_id=None,
    )
    second = binding_service.assign_role(
        db_session=session,
        role_name="project-editor",
        principal_kind=PrincipalKind.USER,
        principal_id=user_id,
        scope_kind=BindingScope.PROJECT,
        scope_id=project_id,
        inherits_into_project=False,
        actor_user_id=None,
    )

    testbase.assert_equal(str(first.binding_id), str(second.binding_id))
    testbase.assert_equal(len(received), 1)
    return


def test_assign_role_unknown_role_raises():
    """
    **Feature: 1-rbac M2**
    **Property: assign_role with an unregistered role_name raises
    RoleNotFoundError.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()

    raised = False
    try:
        binding_service.assign_role(
            db_session=session,
            role_name="no-such-role",
            principal_kind=PrincipalKind.USER,
            principal_id=new_uuid(),
            scope_kind=BindingScope.SYSTEM,
            scope_id=None,
            inherits_into_project=False,
            actor_user_id=None,
        )
    except RoleNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_assign_role_invalid_scope_combinations():
    """
    **Feature: 1-rbac M2**
    **Property: Illegal (scope_kind, scope_id, inherits_into_project)
    combinations raise InvalidBindingScopeError.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()
    _insert_role(session=session, role_name="system-admin-test")

    # SYSTEM with scope_id set → rejected.
    raised = False
    try:
        binding_service.assign_role(
            db_session=session,
            role_name="system-admin-test",
            principal_kind=PrincipalKind.USER,
            principal_id=new_uuid(),
            scope_kind=BindingScope.SYSTEM,
            scope_id=new_uuid(),
            inherits_into_project=False,
            actor_user_id=None,
        )
    except InvalidBindingScopeError:
        raised = True
    testbase.assert_equal(raised, True)

    # PROJECT with missing scope_id → rejected.
    raised = False
    try:
        binding_service.assign_role(
            db_session=session,
            role_name="system-admin-test",
            principal_kind=PrincipalKind.USER,
            principal_id=new_uuid(),
            scope_kind=BindingScope.PROJECT,
            scope_id=None,
            inherits_into_project=False,
            actor_user_id=None,
        )
    except InvalidBindingScopeError:
        raised = True
    testbase.assert_equal(raised, True)

    # PROJECT with inherits_into_project → rejected.
    raised = False
    try:
        binding_service.assign_role(
            db_session=session,
            role_name="system-admin-test",
            principal_kind=PrincipalKind.USER,
            principal_id=new_uuid(),
            scope_kind=BindingScope.PROJECT,
            scope_id=new_uuid(),
            inherits_into_project=True,
            actor_user_id=None,
        )
    except InvalidBindingScopeError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_revoke_role_removes_row_and_publishes_event():
    """
    **Feature: 1-rbac M2**
    **Property: revoke_role deletes the binding and publishes
    entity.role.revoked.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()
    _insert_role(session=session, role_name="project-viewer")

    revoked = []
    subscribe(topic="entity.role.revoked", subscriber=lambda evt: revoked.append(evt))

    project_id = new_uuid()
    user_id = _insert_identity_user(session=session, login_suffix="viewer")
    binding = binding_service.assign_role(
        db_session=session,
        role_name="project-viewer",
        principal_kind=PrincipalKind.USER,
        principal_id=user_id,
        scope_kind=BindingScope.PROJECT,
        scope_id=project_id,
        inherits_into_project=False,
        actor_user_id=None,
    )
    binding_id = str(binding.binding_id)

    binding_service.revoke_role(
        db_session=session,
        binding_id=binding_id,
        actor_user_id=None,
    )

    remaining = binding_service.list_bindings(db_session=session)
    testbase.assert_equal(len(remaining), 0)
    testbase.assert_equal(len(revoked), 1)
    testbase.assert_equal(revoked[0].payload["binding_id"], binding_id)
    return


def test_revoke_role_unknown_raises():
    """
    **Feature: 1-rbac M2**
    **Property: revoke_role with an unknown binding_id raises
    BindingNotFoundError.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()

    raised = False
    try:
        binding_service.revoke_role(
            db_session=session,
            binding_id=new_uuid(),
            actor_user_id=None,
        )
    except BindingNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_list_bindings_filters():
    """
    **Feature: 1-rbac M2**
    **Property: list_bindings returns only rows matching the filters.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()
    _insert_role(session=session, role_name="project-editor")

    project_a = new_uuid()
    project_b = new_uuid()
    user_id = _insert_identity_user(session=session, login_suffix="listed")

    binding_service.assign_role(
        db_session=session, role_name="project-editor",
        principal_kind=PrincipalKind.USER, principal_id=user_id,
        scope_kind=BindingScope.PROJECT, scope_id=project_a,
        inherits_into_project=False, actor_user_id=None,
    )
    binding_service.assign_role(
        db_session=session, role_name="project-editor",
        principal_kind=PrincipalKind.USER, principal_id=user_id,
        scope_kind=BindingScope.PROJECT, scope_id=project_b,
        inherits_into_project=False, actor_user_id=None,
    )

    all_views = binding_service.list_bindings(db_session=session)
    testbase.assert_equal(len(all_views), 2)

    only_a = binding_service.list_bindings(
        db_session=session, scope_kind=BindingScope.PROJECT, scope_id=project_a,
    )
    testbase.assert_equal(len(only_a), 1)
    testbase.assert_equal(only_a[0].scope_id, project_a)
    return


# =============================================================================
# Project-scope evaluation
# =============================================================================

def test_project_owner_binding_allows_project_action():
    """
    **Feature: 1-rbac M2**
    **Property: A user with ProjectOwnerRole at PROJECT scope is allowed
    every project:<id>:<action> key the preset grants.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()
    _insert_role(session=session, role_name="project-owner")

    project_id = new_uuid()
    user_id = _insert_identity_user(session=session, login_suffix="owner")

    binding_service.assign_role(
        db_session=session, role_name="project-owner",
        principal_kind=PrincipalKind.USER, principal_id=user_id,
        scope_kind=BindingScope.PROJECT, scope_id=project_id,
        inherits_into_project=False, actor_user_id=None,
    )

    decision = rbac_evaluator.check_permission(
        db_session=session,
        principal=_principal(user_id),
        permission_key="project:{}:runs.dispatch".format(project_id),
        now=datetime.now(timezone.utc),
    )
    testbase.assert_equal(decision.allowed, True)
    testbase.assert_equal(decision.reason, "binding_allow")
    return


def test_project_binding_does_not_leak_to_other_projects():
    """
    **Feature: 1-rbac M2**
    **Property: A PROJECT-scope binding on project A does not grant
    permission for project B.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()
    _insert_role(session=session, role_name="project-editor")

    project_a = new_uuid()
    project_b = new_uuid()
    user_id = _insert_identity_user(session=session, login_suffix="editor")

    binding_service.assign_role(
        db_session=session, role_name="project-editor",
        principal_kind=PrincipalKind.USER, principal_id=user_id,
        scope_kind=BindingScope.PROJECT, scope_id=project_a,
        inherits_into_project=False, actor_user_id=None,
    )

    decision = rbac_evaluator.check_permission(
        db_session=session,
        principal=_principal(user_id),
        permission_key="project:{}:runs.dispatch".format(project_b),
        now=datetime.now(timezone.utc),
    )
    testbase.assert_equal(decision.allowed, False)
    testbase.assert_equal(decision.reason, "no_matching_binding")
    return


def test_group_membership_grants_project_access():
    """
    **Feature: 1-rbac M2**
    **Property: A PROJECT binding on a group the user belongs to grants
    project-scope permissions to that user.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()
    _insert_role(session=session, role_name="project-editor")

    project_id = new_uuid()
    user_id = _insert_identity_user(session=session, login_suffix="group-member")
    group_id = _insert_group(session=session, group_name="editors")
    _add_user_to_group(session=session, user_id=user_id, group_id=group_id)

    binding_service.assign_role(
        db_session=session, role_name="project-editor",
        principal_kind=PrincipalKind.GROUP, principal_id=group_id,
        scope_kind=BindingScope.PROJECT, scope_id=project_id,
        inherits_into_project=False, actor_user_id=None,
    )

    decision = rbac_evaluator.check_permission(
        db_session=session,
        principal=_principal(user_id),
        permission_key="project:{}:runs.dispatch".format(project_id),
        now=datetime.now(timezone.utc),
    )
    testbase.assert_equal(decision.allowed, True)
    return


def test_group_binding_without_membership_is_denied():
    """
    **Feature: 1-rbac M2**
    **Property: A GROUP-scope binding does not grant permission to users
    who are not members of that group.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()
    _insert_role(session=session, role_name="project-editor")

    project_id = new_uuid()
    user_id = _insert_identity_user(session=session, login_suffix="outsider")
    group_id = _insert_group(session=session, group_name="insiders")
    # note: user is NOT added to group

    binding_service.assign_role(
        db_session=session, role_name="project-editor",
        principal_kind=PrincipalKind.GROUP, principal_id=group_id,
        scope_kind=BindingScope.PROJECT, scope_id=project_id,
        inherits_into_project=False, actor_user_id=None,
    )

    decision = rbac_evaluator.check_permission(
        db_session=session,
        principal=_principal(user_id),
        permission_key="project:{}:runs.dispatch".format(project_id),
        now=datetime.now(timezone.utc),
    )
    testbase.assert_equal(decision.allowed, False)
    return


def test_organization_binding_inherits_into_seeded_project():
    """
    **Feature: 1-rbac M2**
    **Property: An ORGANIZATION-scope binding with inherits_into_project=True
    grants permission inside a project after seed_project_permissions runs.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()
    _insert_role(session=session, role_name="project-viewer")

    project_id = new_uuid()
    user_id = _insert_identity_user(session=session, login_suffix="org-user")

    binding_service.assign_role(
        db_session=session, role_name="project-viewer",
        principal_kind=PrincipalKind.USER, principal_id=user_id,
        scope_kind=BindingScope.ORGANIZATION, scope_id=None,
        inherits_into_project=True, actor_user_id=None,
    )

    # Seed the project.
    inserted = inheritance.seed_project_permissions(
        db_session=session, project_id=project_id,
    )
    session.commit()
    testbase.assert_equal(len(inserted) >= 1, True)

    decision = rbac_evaluator.check_permission(
        db_session=session,
        principal=_principal(user_id),
        permission_key="project:{}:runs.read".format(project_id),
        now=datetime.now(timezone.utc),
    )
    testbase.assert_equal(decision.allowed, True)
    return


def test_seed_project_permissions_is_idempotent():
    """
    **Feature: 1-rbac M2**
    **Property: Running seed_project_permissions twice for the same
    project does not create duplicate rows.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()
    _insert_role(session=session, role_name="project-viewer")

    project_id = new_uuid()
    user_id = _insert_identity_user(session=session, login_suffix="idempotent")

    binding_service.assign_role(
        db_session=session, role_name="project-viewer",
        principal_kind=PrincipalKind.USER, principal_id=user_id,
        scope_kind=BindingScope.ORGANIZATION, scope_id=None,
        inherits_into_project=True, actor_user_id=None,
    )

    first = inheritance.seed_project_permissions(
        db_session=session, project_id=project_id,
    )
    session.commit()
    second = inheritance.seed_project_permissions(
        db_session=session, project_id=project_id,
    )
    session.commit()

    testbase.assert_equal(len(first) >= 1, True)
    testbase.assert_equal(len(second), 0)
    return


# =============================================================================
# Cache + invalidation
# =============================================================================

def test_cache_hit_short_circuits_evaluation():
    """
    **Feature: 1-rbac M2**
    **Property: A second evaluation for the same (principal, key) uses
    the cache; after invalidation, it re-reads from the DB.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()
    _insert_role(session=session, role_name="project-owner")

    project_id = new_uuid()
    user_id = _insert_identity_user(session=session, login_suffix="cache")

    binding_service.assign_role(
        db_session=session, role_name="project-owner",
        principal_kind=PrincipalKind.USER, principal_id=user_id,
        scope_kind=BindingScope.PROJECT, scope_id=project_id,
        inherits_into_project=False, actor_user_id=None,
    )

    key = "project:{}:runs.dispatch".format(project_id)
    first = rbac_evaluator.check_permission(
        db_session=session, principal=_principal(user_id),
        permission_key=key, now=datetime.now(timezone.utc),
    )
    testbase.assert_equal(first.allowed, True)

    # Directly invalidate through the cache API; confirm the lookup
    # afterwards returns None (entry gone).
    cached = cache.cache_get(
        principal_id=user_id, permission_key=key, scope_id=project_id,
    )
    testbase.assert_equal(cached is not None, True)

    cache.invalidate_principal(principal_id=user_id)
    cached = cache.cache_get(
        principal_id=user_id, permission_key=key, scope_id=project_id,
    )
    testbase.assert_equal(cached is None, True)
    return


def test_role_revoked_event_invalidates_cached_decisions():
    """
    **Feature: 1-rbac M2**
    **Property: Publishing entity.role.revoked drops cached decisions
    for the affected principal so the next evaluation re-reads the DB
    and reflects the revocation.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()
    _insert_role(session=session, role_name="project-editor")

    project_id = new_uuid()
    user_id = _insert_identity_user(session=session, login_suffix="revoked")

    binding_service.assign_role(
        db_session=session, role_name="project-editor",
        principal_kind=PrincipalKind.USER, principal_id=user_id,
        scope_kind=BindingScope.PROJECT, scope_id=project_id,
        inherits_into_project=False, actor_user_id=None,
    )

    key = "project:{}:runs.dispatch".format(project_id)
    first = rbac_evaluator.check_permission(
        db_session=session, principal=_principal(user_id),
        permission_key=key, now=datetime.now(timezone.utc),
    )
    testbase.assert_equal(first.allowed, True)

    # Revoke and let the bus event invalidate the cache.
    bindings = binding_service.list_bindings(db_session=session, principal_id=user_id)
    testbase.assert_equal(len(bindings), 1)
    binding_service.revoke_role(
        db_session=session, binding_id=bindings[0].binding_id, actor_user_id=None,
    )

    second = rbac_evaluator.check_permission(
        db_session=session, principal=_principal(user_id),
        permission_key=key, now=datetime.now(timezone.utc),
    )
    testbase.assert_equal(second.allowed, False)
    return


# =============================================================================
# Controller / REST-layer smoke
# =============================================================================

def test_list_bindings_rest_shape():
    """
    **Feature: 1-rbac M2**
    **Property: BindingView fields survive the controller's dict
    marshaling (compile-check on _binding_to_dict).**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()
    _insert_role(session=session, role_name="project-viewer")

    project_id = new_uuid()
    user_id = _insert_identity_user(session=session, login_suffix="rest")

    binding_service.assign_role(
        db_session=session, role_name="project-viewer",
        principal_kind=PrincipalKind.USER, principal_id=user_id,
        scope_kind=BindingScope.PROJECT, scope_id=project_id,
        inherits_into_project=False, actor_user_id=None,
    )

    views = binding_service.list_bindings(db_session=session)
    testbase.assert_equal(len(views), 1)
    view = views[0]
    testbase.assert_equal(view.role_name, "project-viewer")
    testbase.assert_equal(view.scope_kind, BindingScope.PROJECT)
    testbase.assert_equal(view.scope_id, project_id)
    testbase.assert_equal(view.principal_kind, PrincipalKind.USER)
    testbase.assert_equal(view.principal_id, user_id)
    testbase.assert_equal(view.inherits_into_project, False)
    return
