"""
.. module:: test_p10a_maintenance_webhooks_out_m1
    :synopsis: Tests for P10a — 0-maintenance-mode + 8-webhooks-out M1.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import List

from automojo import testbase

from automojo.pychestrate.core.defaults import new_uuid

from automojo.pychestrate.webservice.extensions.registry import (
    reset_registry_for_testing,
)
from automojo.pychestrate.webservice.maintenance import (
    MaintenanceEventTopics,
    MaintenanceMode,
    MaintenanceScopeInvalidError,
    clear_scope_mode,
    get_effective_mode,
    get_gate,
    get_scope_mode,
    list_active_scopes,
    list_audit_for_scope,
    mode_precedence,
    reset_for_testing as reset_maintenance_for_testing,
    set_scope_mode,
)
from automojo.pychestrate.webservice.maintenance.service import (
    warm_gate_from_db,
)
from automojo.pychestrate.webservice.messaging.event_bus import (
    EntityEvent,
    reset_for_testing as reset_event_bus,
    subscribe,
)
from automojo.pychestrate.webservice.webhooks_out import (
    DeliveryOutcome,
    SignatureScheme,
    WebhookOutEventTopics,
    WebhookTargetConflictError,
    WebhookTargetInvalidError,
    WebhookTargetNotFoundError,
    build_signed_request,
    compute_signature,
    disable_target,
    get_target,
    list_recent_deliveries_for_target,
    list_targets_for_project,
    record_delivery_attempt,
    register_builtin_extensions as webhooks_out_register,
    register_target,
)

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
)


PROJECT_UUID = "00000000-0000-4000-8000-000000100001"
ACTOR_UUID = "00000000-0000-4000-8000-000000100002"
SECRET = b"super-shared-secret"


def _prepare_runtime() -> None:
    reset_registry_for_testing()
    reset_event_bus()
    reset_maintenance_for_testing()
    webhooks_out_register()
    return


# -------------------------------------
# 0-maintenance-mode — primitives
# -------------------------------------

def test_mode_precedence_picks_most_restrictive():
    """
    **Feature: 0-maintenance-mode (M1)**
    **Property: mode_precedence picks the most restrictive mode
    under active < read_only < draining.**
    """
    _prepare_runtime()
    testbase.assert_equal(
        mode_precedence(modes=[MaintenanceMode.ACTIVE]),
        MaintenanceMode.ACTIVE,
    )
    testbase.assert_equal(
        mode_precedence(
            modes=[MaintenanceMode.ACTIVE, MaintenanceMode.READ_ONLY],
        ),
        MaintenanceMode.READ_ONLY,
    )
    testbase.assert_equal(
        mode_precedence(
            modes=[MaintenanceMode.READ_ONLY, MaintenanceMode.DRAINING],
        ),
        MaintenanceMode.DRAINING,
    )
    testbase.assert_equal(
        mode_precedence(
            modes=[MaintenanceMode.DRAINING, MaintenanceMode.ACTIVE],
        ),
        MaintenanceMode.DRAINING,
    )
    return


def test_mode_precedence_empty_raises():
    """
    **Feature: 0-maintenance-mode (M1)**
    **Property: mode_precedence with no modes raises
    ValueError.**
    """
    _prepare_runtime()
    raised = False
    try:
        mode_precedence(modes=[])
    except ValueError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_set_scope_mode_persists_audit_and_emits():
    """
    **Feature: 0-maintenance-mode (M1)**
    **Property: set_scope_mode persists the row, appends an
    audit row, updates the in-memory cache, and emits
    MODE_CHANGED.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received_changed: List[EntityEvent] = []
    subscribe(
        topic=MaintenanceEventTopics.MODE_CHANGED,
        subscriber=lambda e: received_changed.append(e),
    )
    view = set_scope_mode(
        db_session=session, scope="service",
        mode=MaintenanceMode.READ_ONLY,
        reason="upgrade window",
        actor_id=ACTOR_UUID,
    )
    testbase.assert_equal(view.mode, MaintenanceMode.READ_ONLY)
    testbase.assert_equal(view.reason, "upgrade window")
    testbase.assert_equal(len(received_changed), 1)

    audits = list_audit_for_scope(db_session=session, scope="service")
    testbase.assert_equal(len(audits), 1)
    testbase.assert_equal(audits[0].from_mode, MaintenanceMode.ACTIVE)
    testbase.assert_equal(audits[0].to_mode, MaintenanceMode.READ_ONLY)

    gate = get_gate()
    testbase.assert_equal(
        gate.get_mode_in_memory(scope="service"),
        MaintenanceMode.READ_ONLY,
    )
    return


def test_set_scope_mode_draining_emits_drain_started():
    """
    **Feature: 0-maintenance-mode (M1)**
    **Property: a transition to DRAINING emits MODE_CHANGED
    plus DRAIN_STARTED.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received_drain: List[EntityEvent] = []
    subscribe(
        topic=MaintenanceEventTopics.DRAIN_STARTED,
        subscriber=lambda e: received_drain.append(e),
    )
    set_scope_mode(
        db_session=session, scope="service",
        mode=MaintenanceMode.DRAINING,
        reason="rolling restart",
    )
    testbase.assert_equal(len(received_drain), 1)
    return


def test_set_scope_mode_no_op_does_not_emit_again():
    """
    **Feature: 0-maintenance-mode (M1)**
    **Property: setting the same mode twice does not append a
    second audit row or emit a second MODE_CHANGED.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=MaintenanceEventTopics.MODE_CHANGED,
        subscriber=lambda e: received.append(e),
    )
    set_scope_mode(
        db_session=session, scope="service",
        mode=MaintenanceMode.READ_ONLY, reason="x",
    )
    set_scope_mode(
        db_session=session, scope="service",
        mode=MaintenanceMode.READ_ONLY, reason="x",
    )
    testbase.assert_equal(len(received), 1)
    audits = list_audit_for_scope(db_session=session, scope="service")
    testbase.assert_equal(len(audits), 1)
    return


def test_clear_scope_mode_emits_cleared_and_drain_ended():
    """
    **Feature: 0-maintenance-mode (M1)**
    **Property: clear_scope_mode restores ACTIVE, drops the
    cache entry, emits MODE_CLEARED, and emits DRAIN_ENDED
    when the prior mode was DRAINING. Idempotent on already-
    active scopes.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received_cleared: List[EntityEvent] = []
    received_drain_ended: List[EntityEvent] = []
    subscribe(
        topic=MaintenanceEventTopics.MODE_CLEARED,
        subscriber=lambda e: received_cleared.append(e),
    )
    subscribe(
        topic=MaintenanceEventTopics.DRAIN_ENDED,
        subscriber=lambda e: received_drain_ended.append(e),
    )
    set_scope_mode(
        db_session=session, scope="service",
        mode=MaintenanceMode.DRAINING, reason="rolling restart",
    )
    cleared = clear_scope_mode(
        db_session=session, scope="service", reason="done",
    )
    testbase.assert_equal(cleared.mode, MaintenanceMode.ACTIVE)
    testbase.assert_equal(len(received_cleared), 1)
    testbase.assert_equal(len(received_drain_ended), 1)
    # Idempotent
    clear_scope_mode(
        db_session=session, scope="service", reason="again",
    )
    testbase.assert_equal(len(received_cleared), 1)
    return


def test_set_scope_mode_active_routes_to_clear():
    """
    **Feature: 0-maintenance-mode (M1)**
    **Property: set_scope_mode(mode=ACTIVE) is rerouted through
    clear_scope_mode so callers can use a single entry point.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=MaintenanceEventTopics.MODE_CLEARED,
        subscriber=lambda e: received.append(e),
    )
    set_scope_mode(
        db_session=session, scope="service",
        mode=MaintenanceMode.READ_ONLY, reason="x",
    )
    set_scope_mode(
        db_session=session, scope="service",
        mode=MaintenanceMode.ACTIVE, reason="back online",
    )
    testbase.assert_equal(len(received), 1)
    return


def test_invalid_scope_raises():
    """
    **Feature: 0-maintenance-mode (M1)**
    **Property: a scope that is not 'service' or
    'project:<slug>' raises MaintenanceScopeInvalidError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    raised = False
    try:
        set_scope_mode(
            db_session=session, scope="not-a-scope",
            mode=MaintenanceMode.READ_ONLY, reason="x",
        )
    except MaintenanceScopeInvalidError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_get_effective_mode_picks_most_restrictive():
    """
    **Feature: 0-maintenance-mode (M1)**
    **Property: get_effective_mode folds the implicit service
    scope plus the supplied list and surfaces the most
    restrictive mode.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    set_scope_mode(
        db_session=session, scope="service",
        mode=MaintenanceMode.READ_ONLY, reason="x",
    )
    set_scope_mode(
        db_session=session, scope="project:alpha",
        mode=MaintenanceMode.DRAINING, reason="alpha drain",
    )
    effective_global = get_effective_mode()
    testbase.assert_equal(effective_global.mode, MaintenanceMode.READ_ONLY)
    effective_alpha = get_effective_mode(scopes=["project:alpha"])
    testbase.assert_equal(effective_alpha.mode, MaintenanceMode.DRAINING)
    testbase.assert_equal(
        "service" in effective_alpha.contributing_scopes, True,
    )
    testbase.assert_equal(
        "project:alpha" in effective_alpha.contributing_scopes, True,
    )
    return


def test_list_active_scopes_returns_only_non_active_rows():
    """
    **Feature: 0-maintenance-mode (M1)**
    **Property: list_active_scopes returns scopes whose mode is
    not active.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    set_scope_mode(
        db_session=session, scope="service",
        mode=MaintenanceMode.READ_ONLY, reason="x",
    )
    set_scope_mode(
        db_session=session, scope="project:beta",
        mode=MaintenanceMode.DRAINING, reason="y",
    )
    rows = list_active_scopes(db_session=session)
    scopes = sorted([r.scope for r in rows])
    testbase.assert_equal(scopes, ["project:beta", "service"])
    return


def test_warm_gate_from_db_replays_persisted_state():
    """
    **Feature: 0-maintenance-mode (M1)**
    **Property: warm_gate_from_db rehydrates the in-memory
    cache after a process restart.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    set_scope_mode(
        db_session=session, scope="service",
        mode=MaintenanceMode.DRAINING, reason="restart",
    )
    # Drop the in-memory cache and re-warm.
    reset_maintenance_for_testing()
    count = warm_gate_from_db(db_session=session)
    testbase.assert_equal(count, 1)
    testbase.assert_equal(
        get_gate().get_mode_in_memory(scope="service"),
        MaintenanceMode.DRAINING,
    )
    return


def test_get_scope_mode_unknown_returns_active_view():
    """
    **Feature: 0-maintenance-mode (M1)**
    **Property: get_scope_mode synthesizes an ACTIVE view for
    scopes the persistence layer has never seen.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    view = get_scope_mode(
        db_session=session, scope="project:never-touched",
    )
    testbase.assert_equal(view.mode, MaintenanceMode.ACTIVE)
    testbase.assert_equal(view.version, 0)
    return


# -------------------------------------
# 8-webhooks-out — primitives
# -------------------------------------

def test_compute_signature_is_deterministic():
    """
    **Feature: 8-webhooks-out (M1)**
    **Property: compute_signature returns the same digest for
    the same inputs.**
    """
    _prepare_runtime()
    a = compute_signature(
        secret=SECRET, timestamp="2026-04-25T00:00:00+00:00",
        body=b'{"hello":"world"}',
    )
    b = compute_signature(
        secret=SECRET, timestamp="2026-04-25T00:00:00+00:00",
        body=b'{"hello":"world"}',
    )
    testbase.assert_equal(a, b)
    testbase.assert_equal(a.startswith("sha256="), True)
    return


def test_register_target_persists_and_emits():
    """
    **Feature: 8-webhooks-out (M1)**
    **Property: register_target persists + emits
    TARGET_REGISTERED.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=WebhookOutEventTopics.TARGET_REGISTERED,
        subscriber=lambda e: received.append(e),
    )
    view = register_target(
        db_session=session, project_id=PROJECT_UUID,
        name="ops-bot", url="https://hooks.example.com/ops",
        topic_filters=["entity.alert.fired", "entity.alert.resolved"],
        custom_headers={"X-Source": "pychestrate"},
        actor_id=ACTOR_UUID,
    )
    testbase.assert_equal(view.name, "ops-bot")
    testbase.assert_equal(view.signature_scheme, SignatureScheme.HMAC_SHA256)
    testbase.assert_equal(len(received), 1)
    return


def test_register_target_invalid_url_raises():
    """
    **Feature: 8-webhooks-out (M1)**
    **Property: a URL without an http(s):// prefix raises
    WebhookTargetInvalidError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    raised = False
    try:
        register_target(
            db_session=session, project_id=PROJECT_UUID,
            name="bad", url="ftp://nope",
        )
    except WebhookTargetInvalidError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_register_target_duplicate_name_raises():
    """
    **Feature: 8-webhooks-out (M1)**
    **Property: a duplicate (project, name) raises
    WebhookTargetConflictError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    register_target(
        db_session=session, project_id=PROJECT_UUID,
        name="dup", url="https://example.com/a",
    )
    raised = False
    try:
        register_target(
            db_session=session, project_id=PROJECT_UUID,
            name="dup", url="https://example.com/b",
        )
    except WebhookTargetConflictError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_disable_target_idempotent_and_emits():
    """
    **Feature: 8-webhooks-out (M1)**
    **Property: disable_target emits TARGET_DISABLED on first
    call; second call is idempotent.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=WebhookOutEventTopics.TARGET_DISABLED,
        subscriber=lambda e: received.append(e),
    )
    target = register_target(
        db_session=session, project_id=PROJECT_UUID,
        name="ops", url="https://example.com/hooks",
    )
    disable_target(db_session=session, target_id=target.target_id)
    disable_target(db_session=session, target_id=target.target_id)
    testbase.assert_equal(len(received), 1)
    enabled = list_targets_for_project(
        db_session=session, project_id=PROJECT_UUID, enabled_only=True,
    )
    testbase.assert_equal(len(enabled), 0)
    return


def test_build_signed_request_returns_canonical_headers():
    """
    **Feature: 8-webhooks-out (M1)**
    **Property: build_signed_request includes the canonical
    signature, timestamp, topic, and delivery-id headers plus
    every per-target custom header.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    target = register_target(
        db_session=session, project_id=PROJECT_UUID,
        name="ops", url="https://example.com/hooks",
        custom_headers={"X-Tenant": "team-a"},
    )
    body = b'{"alert":"hi"}'
    request = build_signed_request(
        db_session=session, target_id=target.target_id,
        topic="entity.alert.fired",
        body=body, secret=SECRET,
    )
    testbase.assert_equal(request.method, "POST")
    testbase.assert_equal(request.url, "https://example.com/hooks")
    testbase.assert_equal(request.signature.startswith("sha256="), True)
    testbase.assert_equal(
        request.headers["X-Pychestrate-Signature"], request.signature,
    )
    testbase.assert_equal(
        request.headers["X-Pychestrate-Topic"], "entity.alert.fired",
    )
    testbase.assert_equal(
        request.headers["X-Pychestrate-Delivery-Id"], request.delivery_id,
    )
    testbase.assert_equal(request.headers["X-Tenant"], "team-a")
    testbase.assert_equal(len(request.payload_digest_sha256), 64)
    return


def test_build_signed_request_disabled_target_raises():
    """
    **Feature: 8-webhooks-out (M1)**
    **Property: build_signed_request against a disabled target
    raises WebhookTargetInvalidError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    target = register_target(
        db_session=session, project_id=PROJECT_UUID,
        name="ops", url="https://example.com/hooks",
    )
    disable_target(db_session=session, target_id=target.target_id)
    raised = False
    try:
        build_signed_request(
            db_session=session, target_id=target.target_id,
            topic="entity.alert.fired", body=b"{}",
            secret=SECRET,
        )
    except WebhookTargetInvalidError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_build_signed_request_unknown_target_raises():
    """
    **Feature: 8-webhooks-out (M1)**
    **Property: build_signed_request against an unknown id
    raises WebhookTargetNotFoundError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    raised = False
    try:
        build_signed_request(
            db_session=session, target_id=new_uuid(),
            topic="x", body=b"{}",
            secret=SECRET,
        )
    except WebhookTargetNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_record_delivery_attempt_persists_and_emits():
    """
    **Feature: 8-webhooks-out (M1)**
    **Property: record_delivery_attempt persists + emits
    DELIVERY_ATTEMPTED; FAILED outcome also emits
    DELIVERY_FAILED.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received_attempted: List[EntityEvent] = []
    received_failed: List[EntityEvent] = []
    subscribe(
        topic=WebhookOutEventTopics.DELIVERY_ATTEMPTED,
        subscriber=lambda e: received_attempted.append(e),
    )
    subscribe(
        topic=WebhookOutEventTopics.DELIVERY_FAILED,
        subscriber=lambda e: received_failed.append(e),
    )
    target = register_target(
        db_session=session, project_id=PROJECT_UUID,
        name="ops", url="https://example.com/hooks",
    )
    request = build_signed_request(
        db_session=session, target_id=target.target_id,
        topic="entity.alert.fired", body=b"{}", secret=SECRET,
    )
    record_delivery_attempt(
        db_session=session, target_id=target.target_id,
        delivery_id=request.delivery_id,
        topic="entity.alert.fired",
        payload_digest_sha256=request.payload_digest_sha256,
        signature=request.signature,
        request_headers=dict(request.headers),
        outcome=DeliveryOutcome.SUCCEEDED,
        response_status=200, duration_ms=42,
    )
    record_delivery_attempt(
        db_session=session, target_id=target.target_id,
        delivery_id=new_uuid(),
        topic="entity.alert.fired",
        payload_digest_sha256=request.payload_digest_sha256,
        signature=request.signature,
        request_headers=dict(request.headers),
        outcome=DeliveryOutcome.FAILED,
        response_status=500, response_excerpt="server bummer",
        duration_ms=120,
    )
    testbase.assert_equal(len(received_attempted), 2)
    testbase.assert_equal(len(received_failed), 1)
    rows = list_recent_deliveries_for_target(
        db_session=session, target_id=target.target_id,
    )
    testbase.assert_equal(len(rows), 2)
    return


def test_get_target_unknown_raises():
    """
    **Feature: 8-webhooks-out (M1)**
    **Property: get_target on an unknown id raises
    WebhookTargetNotFoundError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    raised = False
    try:
        get_target(db_session=session, target_id=new_uuid())
    except WebhookTargetNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return
