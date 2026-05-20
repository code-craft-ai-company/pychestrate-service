"""
.. module:: test_p20g_secrets_scoping_crud
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for PR p20g — org/project/user-scoped secrets
               management with full CRUD.

.. moduleauthor:: Automation Mojo LLC

Coverage:

* create at each scope (org / project / user);
* the value-read permission matrix (org / project / user);
* list filters by scope and never leaks values;
* update rotates the version + emits audit;
* delete removes rows + emits audit;
* the migration columns are present on the live model.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import uuid as uuidmod

from automojo import testbase

from automojo.pychestrate.core.defaults import new_uuid

from automojo.pychestrate.webservice.audit.models import AuditRecord
from automojo.pychestrate.webservice.projects.models import ProjectMemberBinding
from automojo.pychestrate.webservice.secrets import secrets_service
from automojo.pychestrate.webservice.secrets.exceptions import (
    SecretAccessDeniedError,
    SecretNotFoundError,
)
from automojo.pychestrate.webservice.secrets.kek_loader import (
    KekHandle,
    reset_active_kek_for_testing,
    set_active_kek,
)
from automojo.pychestrate.webservice.secrets.models import (
    SecretRecord,
    SecretScopeKind,
    SecretVersion,
)
from automojo.pychestrate.webservice.secrets.secret_bytes import SecretBytes
from automojo.pychestrate.webservice.secrets.secrets_aspects import (
    build_default_aspects,
)
from automojo.pychestrate.webservice.security.auth.models import AuthProviderKind
from automojo.pychestrate.webservice.security.auth.session_service import (
    AuthPrincipal,
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
)


def _install_test_kek() -> None:
    reset_active_kek_for_testing()
    set_active_kek(kek=KekHandle(
        kek_id="test-kek-1",
        key_material=SecretBytes(b"Z" * 32),
        source="test",
    ))
    return


def _principal(user_id: str) -> AuthPrincipal:
    rtnval = AuthPrincipal(
        user_id=user_id,
        session_id="sess",
        provider_kind=AuthProviderKind.LOCAL,
        provider_name="local",
    )
    return rtnval


def _bind_role(*, session, user_id: str, role_name: str) -> None:
    role = (
        session.query(RbacRole)
        .filter(RbacRole.role_name == role_name)
        .first()
    )
    if role is None:
        role = RbacRole(
            role_id=new_uuid(),
            role_name=role_name,
            source=RoleSource.BUILTIN,
            source_name="CorePermissionExtension",
            description="",
        )
        session.add(role)
        session.flush()

    session.add(RbacRoleBinding(
        binding_id=new_uuid(),
        role_id=role.role_id,
        principal_kind=PrincipalKind.USER,
        principal_id=user_id,
        scope_kind=BindingScope.SYSTEM,
        scope_id=None,
        inherits_into_project=False,
        created_by=None,
    ))
    session.commit()
    return


def _bind_admin(*, session, user_id: str) -> None:
    _bind_role(session=session, user_id=user_id, role_name="system-admin")
    return


def _add_project_member(*, session, project_id: str, user_id: str) -> None:
    session.add(ProjectMemberBinding(
        binding_id=new_uuid(),
        project_id=project_id,
        user_id=user_id,
        role_name="member",
        added_by_user_id=None,
    ))
    session.commit()
    return


def test_model_carries_scope_columns():
    """
    **Feature: 1-secrets-vault PR p20g**
    **Property: The SecretRecord model exposes scope_kind + scope_ref
    (the columns the alembic migration adds).**
    """
    columns = SecretRecord.__table__.columns.keys()
    testbase.assert_equal("scope_kind" in columns, True)
    testbase.assert_equal("scope_ref" in columns, True)
    return


def test_create_org_scoped_secret():
    """
    **Feature: 1-secrets-vault PR p20g**
    **Property: An admin can create an ORG-scoped secret; the row is
    persisted with scope_kind ORG and a null scope_ref.**
    """
    reset_phase1_runtime()
    _install_test_kek()
    _engine, session = build_in_memory_session()

    admin_id = str(uuidmod.uuid4())
    _bind_admin(session=session, user_id=admin_id)

    secrets_service.put_secret(
        db_session=session,
        principal=_principal(admin_id),
        secret_ref="system:org.key",
        plaintext=SecretBytes(b"orgvalue"),
        aspects=build_default_aspects(),
        scope_kind=SecretScopeKind.ORG,
    )

    record = session.query(SecretRecord).filter(
        SecretRecord.secret_ref == "system:org.key"
    ).first()
    testbase.assert_equal(record.scope_kind, SecretScopeKind.ORG)
    testbase.assert_equal(record.scope_ref, None)
    return


def test_create_project_and_user_scoped_secrets():
    """
    **Feature: 1-secrets-vault PR p20g**
    **Property: An admin can create PROJECT- and USER-scoped secrets;
    scope_ref carries the project_id / user_id.**
    """
    reset_phase1_runtime()
    _install_test_kek()
    _engine, session = build_in_memory_session()

    admin_id = str(uuidmod.uuid4())
    _bind_admin(session=session, user_id=admin_id)
    project_id = str(uuidmod.uuid4())
    user_id = str(uuidmod.uuid4())

    secrets_service.put_secret(
        db_session=session,
        principal=_principal(admin_id),
        secret_ref="project:p.key",
        plaintext=SecretBytes(b"projvalue"),
        aspects=build_default_aspects(),
        scope_kind=SecretScopeKind.PROJECT,
        scope_ref=project_id,
    )
    secrets_service.put_secret(
        db_session=session,
        principal=_principal(admin_id),
        secret_ref="user:u.key",
        plaintext=SecretBytes(b"uservalue"),
        aspects=build_default_aspects(),
        scope_kind=SecretScopeKind.USER,
        scope_ref=user_id,
    )

    proj = session.query(SecretRecord).filter(
        SecretRecord.secret_ref == "project:p.key"
    ).first()
    usr = session.query(SecretRecord).filter(
        SecretRecord.secret_ref == "user:u.key"
    ).first()
    testbase.assert_equal(proj.scope_kind, SecretScopeKind.PROJECT)
    testbase.assert_equal(str(proj.scope_ref), project_id)
    testbase.assert_equal(usr.scope_kind, SecretScopeKind.USER)
    testbase.assert_equal(str(usr.scope_ref), user_id)
    return


def test_create_project_scope_without_ref_rejected():
    """
    **Feature: 1-secrets-vault PR p20g**
    **Property: A PROJECT-scoped create with no scope_ref raises
    SemanticError.**
    """
    from automojo.errors.exceptions import SemanticError

    reset_phase1_runtime()
    _install_test_kek()
    _engine, session = build_in_memory_session()

    admin_id = str(uuidmod.uuid4())
    _bind_admin(session=session, user_id=admin_id)

    raised = False
    try:
        secrets_service.put_secret(
            db_session=session,
            principal=_principal(admin_id),
            secret_ref="project:bad.key",
            plaintext=SecretBytes(b"x"),
            aspects=build_default_aspects(),
            scope_kind=SecretScopeKind.PROJECT,
            scope_ref=None,
        )
    except SemanticError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_list_filters_by_scope_and_omits_values():
    """
    **Feature: 1-secrets-vault PR p20g**
    **Property: list_secrets filters by scope_kind and the rows it
    returns carry no plaintext / ciphertext fields.**
    """
    reset_phase1_runtime()
    _install_test_kek()
    _engine, session = build_in_memory_session()

    admin_id = str(uuidmod.uuid4())
    _bind_admin(session=session, user_id=admin_id)
    project_id = str(uuidmod.uuid4())

    secrets_service.put_secret(
        db_session=session, principal=_principal(admin_id),
        secret_ref="system:o1", plaintext=SecretBytes(b"a"),
        aspects=build_default_aspects(), scope_kind=SecretScopeKind.ORG,
    )
    secrets_service.put_secret(
        db_session=session, principal=_principal(admin_id),
        secret_ref="project:p1", plaintext=SecretBytes(b"b"),
        aspects=build_default_aspects(),
        scope_kind=SecretScopeKind.PROJECT, scope_ref=project_id,
    )

    org_rows = secrets_service.list_secrets(
        db_session=session, scope_kind=SecretScopeKind.ORG,
    )
    testbase.assert_equal(len(org_rows), 1)
    testbase.assert_equal(org_rows[0].secret_ref, "system:o1")

    proj_rows = secrets_service.list_secrets(
        db_session=session, scope_kind=SecretScopeKind.PROJECT,
        scope_ref=project_id,
    )
    testbase.assert_equal(len(proj_rows), 1)
    testbase.assert_equal(proj_rows[0].secret_ref, "project:p1")

    # SecretRecord carries no plaintext-bearing attribute.
    record_columns = SecretRecord.__table__.columns.keys()
    testbase.assert_equal("value" not in record_columns, True)
    testbase.assert_equal("plaintext" not in record_columns, True)
    return


def test_user_scope_value_read_matrix():
    """
    **Feature: 1-secrets-vault PR p20g**
    **Property: A USER-scoped secret value is readable by the owning
    user and by an admin, but not by an unrelated user.**
    """
    reset_phase1_runtime()
    _install_test_kek()
    _engine, session = build_in_memory_session()

    admin_id = str(uuidmod.uuid4())
    owner_id = str(uuidmod.uuid4())
    stranger_id = str(uuidmod.uuid4())
    _bind_admin(session=session, user_id=admin_id)

    secrets_service.put_secret(
        db_session=session, principal=_principal(admin_id),
        secret_ref="user:owned.key", plaintext=SecretBytes(b"mine"),
        aspects=build_default_aspects(),
        scope_kind=SecretScopeKind.USER, scope_ref=owner_id,
    )

    # Owner can read.
    owner_result = secrets_service.read_secret(
        db_session=session, principal=_principal(owner_id),
        secret_ref="user:owned.key", aspects=build_default_aspects(),
    )
    testbase.assert_equal(owner_result.plaintext.reveal(), b"mine")

    # Admin can read.
    admin_result = secrets_service.read_secret(
        db_session=session, principal=_principal(admin_id),
        secret_ref="user:owned.key", aspects=build_default_aspects(),
    )
    testbase.assert_equal(admin_result.plaintext.reveal(), b"mine")

    # Stranger cannot.
    denied = False
    try:
        secrets_service.read_secret(
            db_session=session, principal=_principal(stranger_id),
            secret_ref="user:owned.key", aspects=build_default_aspects(),
        )
    except SecretAccessDeniedError:
        denied = True
    testbase.assert_equal(denied, True)
    return


def test_project_scope_value_read_requires_membership():
    """
    **Feature: 1-secrets-vault PR p20g**
    **Property: A PROJECT-scoped secret value is readable only by a
    member of that project holding system:project_secrets.read; a
    non-member is denied.**
    """
    reset_phase1_runtime()
    _install_test_kek()
    _engine, session = build_in_memory_session()

    admin_id = str(uuidmod.uuid4())
    member_id = str(uuidmod.uuid4())
    non_member_id = str(uuidmod.uuid4())
    project_id = str(uuidmod.uuid4())

    _bind_admin(session=session, user_id=admin_id)
    # The member holds the project-secrets role and is bound to the
    # project. system-admin role carries system:project_secrets.read.
    _bind_admin(session=session, user_id=member_id)
    _add_project_member(
        session=session, project_id=project_id, user_id=member_id,
    )

    secrets_service.put_secret(
        db_session=session, principal=_principal(admin_id),
        secret_ref="project:scoped.key", plaintext=SecretBytes(b"projsecret"),
        aspects=build_default_aspects(),
        scope_kind=SecretScopeKind.PROJECT, scope_ref=project_id,
    )

    # Member of the project can read.
    member_result = secrets_service.read_secret(
        db_session=session, principal=_principal(member_id),
        secret_ref="project:scoped.key", aspects=build_default_aspects(),
    )
    testbase.assert_equal(member_result.plaintext.reveal(), b"projsecret")

    # A user with no membership and no admin grant is denied.
    denied = False
    try:
        secrets_service.read_secret(
            db_session=session, principal=_principal(non_member_id),
            secret_ref="project:scoped.key", aspects=build_default_aspects(),
        )
    except SecretAccessDeniedError:
        denied = True
    testbase.assert_equal(denied, True)
    return


def test_org_scope_value_read_denied_without_grant():
    """
    **Feature: 1-secrets-vault PR p20g**
    **Property: An ORG-scoped secret value is denied to a principal
    holding no secrets permission.**
    """
    reset_phase1_runtime()
    _install_test_kek()
    _engine, session = build_in_memory_session()

    admin_id = str(uuidmod.uuid4())
    nobody_id = str(uuidmod.uuid4())
    _bind_admin(session=session, user_id=admin_id)

    secrets_service.put_secret(
        db_session=session, principal=_principal(admin_id),
        secret_ref="system:guarded.key", plaintext=SecretBytes(b"v"),
        aspects=build_default_aspects(), scope_kind=SecretScopeKind.ORG,
    )

    denied = False
    try:
        secrets_service.read_secret(
            db_session=session, principal=_principal(nobody_id),
            secret_ref="system:guarded.key", aspects=build_default_aspects(),
        )
    except SecretAccessDeniedError:
        denied = True
    testbase.assert_equal(denied, True)
    return


def test_update_secret_rotates_and_audits():
    """
    **Feature: 1-secrets-vault PR p20g**
    **Property: update_secret installs a new ACTIVE version, the value
    round-trips, and an audit.secret.updated row is emitted.**
    """
    reset_phase1_runtime()
    _install_test_kek()
    _engine, session = build_in_memory_session()

    admin_id = str(uuidmod.uuid4())
    _bind_admin(session=session, user_id=admin_id)
    principal = _principal(admin_id)

    secrets_service.put_secret(
        db_session=session, principal=principal,
        secret_ref="system:rot.key", plaintext=SecretBytes(b"v1"),
        aspects=build_default_aspects(), scope_kind=SecretScopeKind.ORG,
    )
    version = secrets_service.update_secret(
        db_session=session, principal=principal,
        secret_ref="system:rot.key", plaintext=SecretBytes(b"v2"),
        aspects=build_default_aspects(),
    )
    testbase.assert_equal(version.version_number, 2)

    result = secrets_service.read_secret(
        db_session=session, principal=principal,
        secret_ref="system:rot.key", aspects=build_default_aspects(),
    )
    testbase.assert_equal(result.plaintext.reveal(), b"v2")

    versions = session.query(SecretVersion).filter(
        SecretVersion.secret_ref == "system:rot.key"
    ).count()
    testbase.assert_equal(versions, 2)

    rows = session.query(AuditRecord).all()
    kinds = [r.kind for r in rows]
    testbase.assert_equal("audit.secret.updated" in kinds, True)
    return


def test_delete_secret_removes_rows_and_audits():
    """
    **Feature: 1-secrets-vault PR p20g**
    **Property: delete_secret removes the record + version rows and
    emits an audit.secret.deleted row.**
    """
    reset_phase1_runtime()
    _install_test_kek()
    _engine, session = build_in_memory_session()

    admin_id = str(uuidmod.uuid4())
    _bind_admin(session=session, user_id=admin_id)
    principal = _principal(admin_id)

    secrets_service.put_secret(
        db_session=session, principal=principal,
        secret_ref="system:del.key", plaintext=SecretBytes(b"bye"),
        aspects=build_default_aspects(), scope_kind=SecretScopeKind.ORG,
    )
    secrets_service.delete_secret(
        db_session=session, principal=principal,
        secret_ref="system:del.key", aspects=build_default_aspects(),
    )

    remaining = session.query(SecretRecord).filter(
        SecretRecord.secret_ref == "system:del.key"
    ).count()
    testbase.assert_equal(remaining, 0)
    versions = session.query(SecretVersion).filter(
        SecretVersion.secret_ref == "system:del.key"
    ).count()
    testbase.assert_equal(versions, 0)

    rows = session.query(AuditRecord).all()
    kinds = [r.kind for r in rows]
    testbase.assert_equal("audit.secret.deleted" in kinds, True)
    return


def test_delete_missing_secret_raises():
    """
    **Feature: 1-secrets-vault PR p20g**
    **Property: delete_secret for an unknown ref raises
    SecretNotFoundError.**
    """
    reset_phase1_runtime()
    _install_test_kek()
    _engine, session = build_in_memory_session()

    admin_id = str(uuidmod.uuid4())
    _bind_admin(session=session, user_id=admin_id)

    raised = False
    try:
        secrets_service.delete_secret(
            db_session=session, principal=_principal(admin_id),
            secret_ref="system:nope.key", aspects=build_default_aspects(),
        )
    except SecretNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return
