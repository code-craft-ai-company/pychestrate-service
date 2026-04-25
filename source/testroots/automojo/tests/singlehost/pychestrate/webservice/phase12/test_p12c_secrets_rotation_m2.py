"""
.. module:: test_p12c_secrets_rotation_m2
    :synopsis: Tests for P12c — 1-secrets-vault rotation slice.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime, timedelta, timezone
from typing import List

from automojo import testbase

from automojo.pychestrate.core.defaults import new_uuid

from automojo.pychestrate.webservice.messaging.event_bus import (
    EntityEvent,
    subscribe,
)
from automojo.pychestrate.webservice.secrets import secrets_service
from automojo.pychestrate.webservice.secrets.events import SecretEventTopics
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
    SecretVersion,
    SecretVersionState,
)
from automojo.pychestrate.webservice.secrets.secret_bytes import SecretBytes
from automojo.pychestrate.webservice.secrets.secrets_aspects import (
    build_default_aspects,
)
from automojo.pychestrate.webservice.security.auth.models import (
    AuthProviderKind,
)
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
    return AuthPrincipal(
        user_id=user_id,
        session_id="sess",
        provider_kind=AuthProviderKind.LOCAL,
        provider_name="local",
    )


def _bind_system_admin(*, session, user_id: str) -> None:
    role = RbacRole(
        role_id=new_uuid(),
        role_name="system-admin",
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


def _setup() -> tuple:
    reset_phase1_runtime()
    _install_test_kek()
    _engine, session = build_in_memory_session()
    actor_id = new_uuid()
    _bind_system_admin(session=session, user_id=actor_id)
    return (session, _principal(actor_id))


# -------------------------------------
# rotate_secret
# -------------------------------------

def test_rotate_secret_creates_new_version_and_emits():
    """
    **Feature: 1-secrets-vault (M2)**
    **Property: rotate_secret writes a new ACTIVE version,
    flips the prior to SUPERSEDED with a grace_expires_at
    deadline, and emits SECRET_ROTATED.**
    """
    session, principal = _setup()
    received: List[EntityEvent] = []
    subscribe(
        topic=SecretEventTopics.SECRET_ROTATED,
        subscriber=lambda e: received.append(e),
    )
    secrets_service.put_secret(
        db_session=session, principal=principal,
        secret_ref="ops:rotate.target",
        plaintext=SecretBytes(b"v1-payload"),
        aspects=build_default_aspects(),
    )

    new_version = secrets_service.rotate_secret(
        db_session=session, principal=principal,
        secret_ref="ops:rotate.target",
        new_plaintext=SecretBytes(b"v2-payload"),
        aspects=build_default_aspects(),
    )
    testbase.assert_equal(new_version.version_number, 2)
    testbase.assert_equal(new_version.state, SecretVersionState.ACTIVE)
    testbase.assert_equal(len(received), 1)
    testbase.assert_equal(received[0].payload["version_number"], 2)

    versions = (
        session.query(SecretVersion)
        .filter(SecretVersion.secret_ref == "ops:rotate.target")
        .order_by(SecretVersion.version_number.asc())
        .all()
    )
    testbase.assert_equal(versions[0].state, SecretVersionState.SUPERSEDED)
    testbase.assert_equal(versions[0].grace_expires_at is not None, True)

    record = (
        session.query(SecretRecord)
        .filter(SecretRecord.secret_ref == "ops:rotate.target")
        .first()
    )
    testbase.assert_equal(record.current_version_id, new_version.version_id)
    return


def test_rotate_secret_unknown_ref_raises_not_found():
    """
    **Feature: 1-secrets-vault (M2)**
    **Property: rotate_secret on a missing record raises
    SecretNotFoundError.**
    """
    session, principal = _setup()
    raised = False
    try:
        secrets_service.rotate_secret(
            db_session=session, principal=principal,
            secret_ref="ops:does.not.exist",
            new_plaintext=SecretBytes(b"x"),
            aspects=build_default_aspects(),
        )
    except SecretNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_rotate_secret_requires_write_permission():
    """
    **Feature: 1-secrets-vault (M2)**
    **Property: rotate_secret without write permission raises
    SecretAccessDeniedError.**
    """
    session, principal = _setup()
    secrets_service.put_secret(
        db_session=session, principal=principal,
        secret_ref="ops:permission.target",
        plaintext=SecretBytes(b"v1"),
        aspects=build_default_aspects(),
    )
    # Different user with no admin binding.
    outsider = _principal(new_uuid())
    raised = False
    try:
        secrets_service.rotate_secret(
            db_session=session, principal=outsider,
            secret_ref="ops:permission.target",
            new_plaintext=SecretBytes(b"v2"),
            aspects=build_default_aspects(),
        )
    except SecretAccessDeniedError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_rotate_secret_read_returns_new_value():
    """
    **Feature: 1-secrets-vault (M2)**
    **Property: read_secret after rotate returns the v2
    plaintext (the active row points at the new version).**
    """
    session, principal = _setup()
    secrets_service.put_secret(
        db_session=session, principal=principal,
        secret_ref="ops:rotate.read",
        plaintext=SecretBytes(b"old-value"),
        aspects=build_default_aspects(),
    )
    secrets_service.rotate_secret(
        db_session=session, principal=principal,
        secret_ref="ops:rotate.read",
        new_plaintext=SecretBytes(b"new-value"),
        aspects=build_default_aspects(),
    )
    read = secrets_service.read_secret(
        db_session=session, principal=principal,
        secret_ref="ops:rotate.read",
        aspects=build_default_aspects(),
    )
    testbase.assert_equal(read.plaintext.reveal(), b"new-value")
    return


# -------------------------------------
# force_expire_secret
# -------------------------------------

def test_force_expire_secret_marks_every_version_expired():
    """
    **Feature: 1-secrets-vault (M2)**
    **Property: force_expire_secret bypasses the grace window,
    flips every non-EXPIRED version to EXPIRED, clears
    current_version_id, and emits SECRET_FORCE_EXPIRED with
    the count.**
    """
    session, principal = _setup()
    received: List[EntityEvent] = []
    subscribe(
        topic=SecretEventTopics.SECRET_FORCE_EXPIRED,
        subscriber=lambda e: received.append(e),
    )
    secrets_service.put_secret(
        db_session=session, principal=principal,
        secret_ref="ops:force.expire",
        plaintext=SecretBytes(b"v1"),
        aspects=build_default_aspects(),
    )
    secrets_service.rotate_secret(
        db_session=session, principal=principal,
        secret_ref="ops:force.expire",
        new_plaintext=SecretBytes(b"v2"),
        aspects=build_default_aspects(),
    )

    transitioned = secrets_service.force_expire_secret(
        db_session=session, principal=principal,
        secret_ref="ops:force.expire",
        reason="leak_suspected",
    )
    testbase.assert_equal(transitioned, 2)
    versions = (
        session.query(SecretVersion)
        .filter(SecretVersion.secret_ref == "ops:force.expire")
        .all()
    )
    for version in versions:
        testbase.assert_equal(version.state, SecretVersionState.EXPIRED)
    record = (
        session.query(SecretRecord)
        .filter(SecretRecord.secret_ref == "ops:force.expire")
        .first()
    )
    testbase.assert_equal(record.current_version_id, None)
    testbase.assert_equal(len(received), 1)
    testbase.assert_equal(received[0].payload["expired_count"], 2)
    testbase.assert_equal(received[0].payload["reason"], "leak_suspected")
    return


def test_force_expire_secret_unknown_ref_raises_not_found():
    """
    **Feature: 1-secrets-vault (M2)**
    **Property: force_expire_secret on a missing record raises
    SecretNotFoundError.**
    """
    session, principal = _setup()
    raised = False
    try:
        secrets_service.force_expire_secret(
            db_session=session, principal=principal,
            secret_ref="ops:never.created",
        )
    except SecretNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return


# -------------------------------------
# sweep_expired_versions
# -------------------------------------

def test_sweep_expired_versions_flips_past_grace_rows():
    """
    **Feature: 1-secrets-vault (M2)**
    **Property: sweep_expired_versions flips SUPERSEDED rows
    whose grace_expires_at is in the past to EXPIRED. Active
    rows and rows still inside their grace window are
    untouched.**
    """
    session, principal = _setup()
    secrets_service.put_secret(
        db_session=session, principal=principal,
        secret_ref="ops:sweep.target",
        plaintext=SecretBytes(b"v1"),
        aspects=build_default_aspects(),
    )
    secrets_service.rotate_secret(
        db_session=session, principal=principal,
        secret_ref="ops:sweep.target",
        new_plaintext=SecretBytes(b"v2"),
        aspects=build_default_aspects(),
        grace_period=timedelta(seconds=1),
    )
    # Push the SUPERSEDED row's grace deadline into the past
    # by moving the sweep clock forward.
    future = datetime.now(tz=timezone.utc) + timedelta(hours=1)
    transitioned = secrets_service.sweep_expired_versions(
        db_session=session, now=future,
    )
    testbase.assert_equal(transitioned, 1)

    versions = (
        session.query(SecretVersion)
        .filter(SecretVersion.secret_ref == "ops:sweep.target")
        .order_by(SecretVersion.version_number.asc())
        .all()
    )
    testbase.assert_equal(versions[0].state, SecretVersionState.EXPIRED)
    testbase.assert_equal(versions[1].state, SecretVersionState.ACTIVE)
    return


def test_sweep_expired_versions_skips_rows_inside_grace():
    """
    **Feature: 1-secrets-vault (M2)**
    **Property: sweep_expired_versions does not touch
    SUPERSEDED rows whose grace deadline is in the future.**
    """
    session, principal = _setup()
    secrets_service.put_secret(
        db_session=session, principal=principal,
        secret_ref="ops:sweep.fresh",
        plaintext=SecretBytes(b"v1"),
        aspects=build_default_aspects(),
    )
    secrets_service.rotate_secret(
        db_session=session, principal=principal,
        secret_ref="ops:sweep.fresh",
        new_plaintext=SecretBytes(b"v2"),
        aspects=build_default_aspects(),
        grace_period=timedelta(hours=1),
    )
    transitioned = secrets_service.sweep_expired_versions(
        db_session=session,
    )
    testbase.assert_equal(transitioned, 0)
    return


def test_sweep_expired_versions_no_op_when_nothing_pending():
    """
    **Feature: 1-secrets-vault (M2)**
    **Property: sweep_expired_versions returns 0 when no
    SUPERSEDED rows exist.**
    """
    session, _principal = _setup()
    transitioned = secrets_service.sweep_expired_versions(
        db_session=session,
    )
    testbase.assert_equal(transitioned, 0)
    return
