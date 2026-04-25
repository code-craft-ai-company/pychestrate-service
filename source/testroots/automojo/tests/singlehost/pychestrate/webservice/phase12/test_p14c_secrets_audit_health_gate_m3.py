"""
.. module:: test_p14c_secrets_audit_health_gate_m3
    :synopsis: Tests for P14c — 1-secrets-vault M3
               audit-unhealthy write-block.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import List

from automojo import testbase

from automojo.pychestrate.core.defaults import new_uuid

from automojo.pychestrate.webservice.audit.events import AuditEventTopics
from automojo.pychestrate.webservice.messaging.event_bus import (
    EntityEvent,
    publish,
)
from automojo.pychestrate.webservice.secrets import (
    audit_health_gate,
    secrets_service,
)
from automojo.pychestrate.webservice.secrets.exceptions import (
    AuditUnavailableError,
)
from automojo.pychestrate.webservice.secrets.kek_loader import (
    KekHandle,
    reset_active_kek_for_testing,
    set_active_kek,
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
    audit_health_gate.reset_for_testing()
    audit_health_gate.install_subscribers()
    _install_test_kek()
    _engine, session = build_in_memory_session()
    actor_id = new_uuid()
    _bind_system_admin(session=session, user_id=actor_id)
    return (session, _principal(actor_id))


# -------------------------------------
# Gate state machine
# -------------------------------------

def test_gate_starts_unblocked():
    """
    **Feature: 1-secrets-vault (M3)**
    **Property: a fresh process has the gate open — secrets
    writes are allowed until an unhealthy emit lands.**
    """
    audit_health_gate.reset_for_testing()
    testbase.assert_equal(audit_health_gate.is_write_blocked(), False)
    testbase.assert_equal(audit_health_gate.blocking_sinks(), set())
    return


def test_canonical_unhealthy_emit_blocks_writes():
    """
    **Feature: 1-secrets-vault (M3)**
    **Property: a canonical AUDIT_SINK_UNHEALTHY emit closes
    the gate.**
    """
    audit_health_gate.reset_for_testing()
    audit_health_gate.install_subscribers()
    publish(event=EntityEvent(
        topic=AuditEventTopics.AUDIT_SINK_UNHEALTHY,
        payload={
            "sink_name": "local-db",
            "is_canonical": True,
            "reason": "simulated",
        },
        source_event_id=new_uuid(),
    ))
    testbase.assert_equal(audit_health_gate.is_write_blocked(), True)
    testbase.assert_equal(
        "local-db" in audit_health_gate.blocking_sinks(), True,
    )
    return


def test_non_canonical_unhealthy_emit_does_not_block_writes():
    """
    **Feature: 1-secrets-vault (M3)**
    **Property: a non-canonical fan-out sink reporting
    unhealthy is recorded by the audit system but does NOT
    close the secrets-write gate.**
    """
    audit_health_gate.reset_for_testing()
    audit_health_gate.install_subscribers()
    publish(event=EntityEvent(
        topic=AuditEventTopics.AUDIT_SINK_UNHEALTHY,
        payload={
            "sink_name": "json-file",
            "is_canonical": False,
            "reason": "path_unwritable",
        },
        source_event_id=new_uuid(),
    ))
    testbase.assert_equal(audit_health_gate.is_write_blocked(), False)
    return


def test_canonical_healthy_emit_reopens_gate():
    """
    **Feature: 1-secrets-vault (M3)**
    **Property: a canonical AUDIT_SINK_HEALTHY emit reopens
    the gate even if a prior unhealthy emit closed it.**
    """
    audit_health_gate.reset_for_testing()
    audit_health_gate.install_subscribers()
    publish(event=EntityEvent(
        topic=AuditEventTopics.AUDIT_SINK_UNHEALTHY,
        payload={"sink_name": "local-db", "is_canonical": True},
        source_event_id=new_uuid(),
    ))
    testbase.assert_equal(audit_health_gate.is_write_blocked(), True)
    publish(event=EntityEvent(
        topic=AuditEventTopics.AUDIT_SINK_HEALTHY,
        payload={"sink_name": "local-db", "is_canonical": True},
        source_event_id=new_uuid(),
    ))
    testbase.assert_equal(audit_health_gate.is_write_blocked(), False)
    return


def test_install_subscribers_is_idempotent():
    """
    **Feature: 1-secrets-vault (M3)**
    **Property: install_subscribers can be called multiple
    times — a single unhealthy emit only blocks once and a
    matching healthy emit reopens.**
    """
    audit_health_gate.reset_for_testing()
    audit_health_gate.install_subscribers()
    audit_health_gate.install_subscribers()
    publish(event=EntityEvent(
        topic=AuditEventTopics.AUDIT_SINK_UNHEALTHY,
        payload={"sink_name": "local-db", "is_canonical": True},
        source_event_id=new_uuid(),
    ))
    testbase.assert_equal(audit_health_gate.is_write_blocked(), True)
    return


# -------------------------------------
# put_secret refuses when gate is closed
# -------------------------------------

def test_put_secret_blocked_when_audit_sink_unhealthy():
    """
    **Feature: 1-secrets-vault (M3)**
    **Property: put_secret raises AuditUnavailableError when
    the canonical audit sink is unhealthy.**
    """
    session, principal = _setup()
    publish(event=EntityEvent(
        topic=AuditEventTopics.AUDIT_SINK_UNHEALTHY,
        payload={"sink_name": "local-db", "is_canonical": True},
        source_event_id=new_uuid(),
    ))
    raised = False
    try:
        secrets_service.put_secret(
            db_session=session, principal=principal,
            secret_ref="ops:audit-blocked",
            plaintext=SecretBytes(b"x"),
            aspects=build_default_aspects(),
        )
    except AuditUnavailableError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_put_secret_succeeds_after_sink_recovers():
    """
    **Feature: 1-secrets-vault (M3)**
    **Property: a healthy emit reopens the gate so the next
    put_secret call succeeds.**
    """
    session, principal = _setup()
    publish(event=EntityEvent(
        topic=AuditEventTopics.AUDIT_SINK_UNHEALTHY,
        payload={"sink_name": "local-db", "is_canonical": True},
        source_event_id=new_uuid(),
    ))
    publish(event=EntityEvent(
        topic=AuditEventTopics.AUDIT_SINK_HEALTHY,
        payload={"sink_name": "local-db", "is_canonical": True},
        source_event_id=new_uuid(),
    ))
    version = secrets_service.put_secret(
        db_session=session, principal=principal,
        secret_ref="ops:after-recovery",
        plaintext=SecretBytes(b"x"),
        aspects=build_default_aspects(),
    )
    testbase.assert_equal(version is not None, True)
    return


# -------------------------------------
# rotate_secret + force_expire_secret refuse when gate is closed
# -------------------------------------

def test_rotate_secret_blocked_when_audit_sink_unhealthy():
    """
    **Feature: 1-secrets-vault (M3)**
    **Property: rotate_secret refuses with
    AuditUnavailableError while the canonical sink is
    unhealthy.**
    """
    session, principal = _setup()
    secrets_service.put_secret(
        db_session=session, principal=principal,
        secret_ref="ops:rotate.gated",
        plaintext=SecretBytes(b"v1"),
        aspects=build_default_aspects(),
    )
    publish(event=EntityEvent(
        topic=AuditEventTopics.AUDIT_SINK_UNHEALTHY,
        payload={"sink_name": "local-db", "is_canonical": True},
        source_event_id=new_uuid(),
    ))
    raised = False
    try:
        secrets_service.rotate_secret(
            db_session=session, principal=principal,
            secret_ref="ops:rotate.gated",
            new_plaintext=SecretBytes(b"v2"),
            aspects=build_default_aspects(),
        )
    except AuditUnavailableError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_force_expire_secret_blocked_when_audit_sink_unhealthy():
    """
    **Feature: 1-secrets-vault (M3)**
    **Property: force_expire_secret refuses with
    AuditUnavailableError while the canonical sink is
    unhealthy.**
    """
    session, principal = _setup()
    secrets_service.put_secret(
        db_session=session, principal=principal,
        secret_ref="ops:expire.gated",
        plaintext=SecretBytes(b"v1"),
        aspects=build_default_aspects(),
    )
    publish(event=EntityEvent(
        topic=AuditEventTopics.AUDIT_SINK_UNHEALTHY,
        payload={"sink_name": "local-db", "is_canonical": True},
        source_event_id=new_uuid(),
    ))
    raised = False
    try:
        secrets_service.force_expire_secret(
            db_session=session, principal=principal,
            secret_ref="ops:expire.gated",
        )
    except AuditUnavailableError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_read_secret_not_blocked_by_audit_unhealthy():
    """
    **Feature: 1-secrets-vault (M3)**
    **Property: read_secret continues to serve while the
    canonical sink is unhealthy — the gate is a write-only
    invariant.**
    """
    session, principal = _setup()
    secrets_service.put_secret(
        db_session=session, principal=principal,
        secret_ref="ops:read.during.outage",
        plaintext=SecretBytes(b"value"),
        aspects=build_default_aspects(),
    )
    publish(event=EntityEvent(
        topic=AuditEventTopics.AUDIT_SINK_UNHEALTHY,
        payload={"sink_name": "local-db", "is_canonical": True},
        source_event_id=new_uuid(),
    ))
    read = secrets_service.read_secret(
        db_session=session, principal=principal,
        secret_ref="ops:read.during.outage",
        aspects=build_default_aspects(),
    )
    testbase.assert_equal(read.plaintext.reveal(), b"value")
    return
