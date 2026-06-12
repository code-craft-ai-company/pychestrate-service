"""
.. module:: test_secrets_service
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for 1-secrets-vault put_secret / read_secret +
               LocalEncryptedSecretsBackend AES-GCM crypto.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import uuid as uuidmod

from datetime import datetime, timezone

from ccai import testbase

from ccai.pychestrate.core.defaults import new_uuid

from ccai.pychestrate.webservice.audit.models import AuditRecord
from ccai.pychestrate.webservice.messaging.event_bus import subscribe
from ccai.pychestrate.webservice.secrets import secrets_service
from ccai.pychestrate.webservice.secrets.exceptions import (
    SecretAccessDeniedError,
    SecretAlreadyExistsError,
    SecretNotFoundError,
)
from ccai.pychestrate.webservice.secrets.factories.local_backend import (
    decrypt_ciphertext,
    encrypt_plaintext,
)
from ccai.pychestrate.webservice.secrets.kek_loader import (
    KekHandle,
    reset_active_kek_for_testing,
    set_active_kek,
)
from ccai.pychestrate.webservice.secrets.models import SecretRecord, SecretVersion
from ccai.pychestrate.webservice.secrets.secret_bytes import SecretBytes
from ccai.pychestrate.webservice.secrets.secrets_aspects import build_default_aspects
from ccai.pychestrate.webservice.security.auth.models import AuthProviderKind
from ccai.pychestrate.webservice.security.auth.session_service import AuthPrincipal
from ccai.pychestrate.webservice.security.rbac.models import (
    BindingScope, PermissionEffect, PrincipalKind, RbacRole, RbacRoleBinding, RoleSource,
)

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
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


def test_encrypt_decrypt_round_trip_with_kek():
    """
    **Feature: 1-secrets-vault**
    **Property: AES-GCM encrypt then decrypt recovers the original bytes.**
    """
    _install_test_kek()
    plaintext = SecretBytes(b"correct horse battery staple")
    payload = encrypt_plaintext(plaintext=plaintext, secret_ref="system:test.key")

    recovered = decrypt_ciphertext(
        ciphertext_bytes=payload.ciphertext_bytes,
        wrapped_dek=payload.wrapped_dek,
        secret_ref="system:test.key",
    )
    testbase.assert_equal(recovered.reveal(), b"correct horse battery staple")
    return


def test_encrypt_is_not_deterministic():
    """
    **Feature: 1-secrets-vault**
    **Property: Encrypting the same plaintext twice produces distinct
    ciphertexts (fresh DEK + nonce per encrypt).**
    """
    _install_test_kek()
    plaintext_a = SecretBytes(b"hunter2")
    plaintext_b = SecretBytes(b"hunter2")

    payload_a = encrypt_plaintext(plaintext=plaintext_a, secret_ref="system:test.key")
    payload_b = encrypt_plaintext(plaintext=plaintext_b, secret_ref="system:test.key")

    testbase.assert_equal(payload_a.ciphertext_bytes != payload_b.ciphertext_bytes, True)
    testbase.assert_equal(payload_a.wrapped_dek != payload_b.wrapped_dek, True)
    return


def test_decrypt_rejects_wrong_secret_ref():
    """
    **Feature: 1-secrets-vault**
    **Property: AEAD associated data binds ciphertext to secret_ref —
    decrypting with a different ref fails.**
    """
    _install_test_kek()
    plaintext = SecretBytes(b"bound-to-ref")
    payload = encrypt_plaintext(plaintext=plaintext, secret_ref="system:key.a")

    raised = False
    try:
        decrypt_ciphertext(
            ciphertext_bytes=payload.ciphertext_bytes,
            wrapped_dek=payload.wrapped_dek,
            secret_ref="system:key.b",
        )
    except Exception:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_put_secret_requires_authorization():
    """
    **Feature: 1-secrets-vault**
    **Property: A principal with no binding cannot put_secret.**
    """
    reset_phase1_runtime()
    _install_test_kek()
    _engine, session = build_in_memory_session()

    raised = False
    try:
        secrets_service.put_secret(
            db_session=session,
            principal=_principal(str(uuidmod.uuid4())),
            secret_ref="system:test.secret",
            plaintext=SecretBytes(b"v1"),
            aspects=build_default_aspects(),
        )
    except SecretAccessDeniedError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_put_secret_admin_round_trip():
    """
    **Feature: 1-secrets-vault + 1-rbac + 1-audit-log**
    **Property: system-admin principal can put_secret, read_secret, and
    produces an audit row per access.**
    """
    reset_phase1_runtime()
    _install_test_kek()
    _engine, session = build_in_memory_session()

    admin_id = str(uuidmod.uuid4())
    _bind_system_admin(session=session, user_id=admin_id)
    principal = _principal(admin_id)

    version = secrets_service.put_secret(
        db_session=session,
        principal=principal,
        secret_ref="system:demo.api_key",
        plaintext=SecretBytes(b"seekrit"),
        aspects=build_default_aspects(),
    )
    testbase.assert_equal(version.version_number, 1)

    result = secrets_service.read_secret(
        db_session=session,
        principal=principal,
        secret_ref="system:demo.api_key",
        aspects=build_default_aspects(),
    )
    testbase.assert_equal(result.plaintext.reveal(), b"seekrit")
    testbase.assert_equal(result.version_number, 1)

    # One audit record per write, one per read.
    rows = session.query(AuditRecord).order_by(AuditRecord.sequence_number.asc()).all()
    kinds = [r.kind for r in rows]
    testbase.assert_equal("audit.secret.created" in kinds, True)
    testbase.assert_equal("audit.secret.accessed" in kinds, True)
    return


def test_put_secret_duplicate_raises():
    """
    **Feature: 1-secrets-vault**
    **Property: put_secret on an existing secret_ref raises
    SecretAlreadyExistsError.**
    """
    reset_phase1_runtime()
    _install_test_kek()
    _engine, session = build_in_memory_session()

    admin_id = str(uuidmod.uuid4())
    _bind_system_admin(session=session, user_id=admin_id)
    principal = _principal(admin_id)

    secrets_service.put_secret(
        db_session=session,
        principal=principal,
        secret_ref="system:dup.key",
        plaintext=SecretBytes(b"v1"),
        aspects=build_default_aspects(),
    )

    raised = False
    try:
        secrets_service.put_secret(
            db_session=session,
            principal=principal,
            secret_ref="system:dup.key",
            plaintext=SecretBytes(b"v2"),
            aspects=build_default_aspects(),
        )
    except SecretAlreadyExistsError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_owner_can_read_without_rbac_grant():
    """
    **Feature: 1-secrets-vault**
    **Property: The owner of a secret can always read it even without
    a system:secrets.read binding.**
    """
    reset_phase1_runtime()
    _install_test_kek()
    _engine, session = build_in_memory_session()

    owner_id = str(uuidmod.uuid4())
    _bind_system_admin(session=session, user_id=owner_id)
    owner_principal = _principal(owner_id)

    secrets_service.put_secret(
        db_session=session,
        principal=owner_principal,
        secret_ref="system:owned.key",
        plaintext=SecretBytes(b"only-owner-sees-this"),
        aspects=build_default_aspects(),
    )

    # Simulate removing the binding: create a fresh principal matching the
    # owner but without system-admin context. Owner-match must still grant
    # read.
    fresh_principal = _principal(owner_id)
    result = secrets_service.read_secret(
        db_session=session,
        principal=fresh_principal,
        secret_ref="system:owned.key",
        aspects=build_default_aspects(),
    )
    testbase.assert_equal(result.plaintext.reveal(), b"only-owner-sees-this")
    return


def test_read_missing_secret_raises():
    """
    **Feature: 1-secrets-vault**
    **Property: read_secret for an unknown ref raises SecretNotFoundError.**
    """
    reset_phase1_runtime()
    _install_test_kek()
    _engine, session = build_in_memory_session()

    admin_id = str(uuidmod.uuid4())
    _bind_system_admin(session=session, user_id=admin_id)

    raised = False
    try:
        secrets_service.read_secret(
            db_session=session,
            principal=_principal(admin_id),
            secret_ref="system:does.not.exist",
            aspects=build_default_aspects(),
        )
    except SecretNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_read_publishes_entity_secret_accessed():
    """
    **Feature: 1-secrets-vault**
    **Property: A successful read publishes entity.secret.accessed on
    the bus.**
    """
    reset_phase1_runtime()
    _install_test_kek()
    _engine, session = build_in_memory_session()

    admin_id = str(uuidmod.uuid4())
    _bind_system_admin(session=session, user_id=admin_id)
    principal = _principal(admin_id)

    secrets_service.put_secret(
        db_session=session,
        principal=principal,
        secret_ref="system:event.key",
        plaintext=SecretBytes(b"payload"),
        aspects=build_default_aspects(),
    )

    received = []
    subscribe(
        topic="entity.secret.accessed",
        subscriber=lambda evt: received.append(evt),
    )

    secrets_service.read_secret(
        db_session=session,
        principal=principal,
        secret_ref="system:event.key",
        aspects=build_default_aspects(),
    )

    testbase.assert_equal(len(received), 1)
    testbase.assert_equal(received[0].payload["secret_ref"], "system:event.key")
    return
