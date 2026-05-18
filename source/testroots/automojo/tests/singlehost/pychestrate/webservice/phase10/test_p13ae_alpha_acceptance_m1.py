"""
.. module:: test_p13ae_alpha_acceptance_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Phase-1 alpha acceptance gate -- modern auth + RBAC +
               audit pipeline are wired end-to-end.

.. moduleauthor:: Automation Mojo LLC

The implementation plan's Phase-1 exit criterion calls for an end-
to-end demonstration that:

* an admin can log in,
* the admin's permission-gated mutations are admitted,
* every domain action lands in the audit log.

The piecewise tier-1..tier-4 e2e modules cover login (p13r),
permission gating (p13v), session lifecycle (p13ac), and static
asset serving (p13u). This module is the *acceptance gate* -- a
single test walking the full chain so a regression in any link
trips a single, clearly-named failure rather than reading like
a flake in some unrelated tier.

The chain exercised:

1. Bootstrap the runtime (in-memory SQLite, modern Phase-1 schema +
   in-tree RBAC catalog).
2. Wire the audit-bus subscriber (``audit.bus_subscriber.wire_bus_subscribers``)
   against the test session factory.
3. Login as the seeded admin (modern ``local_flow.verify_local_credentials``
   + ``session_service.open_session``) and recover the session cookie.
4. Drive ``GET /resources/create`` -- this is the canonical
   admin-gated route in the consumer UI surface and exercises
   ``ConsumerUISecurityAdapter.check_permission`` ->
   ``rbac_evaluator.check_permission`` against
   ``rbac_role_bindings`` (PR p13ad). Asserts the gate ALLOWS.
5. Publish an ``entity.project.created`` event on the in-process
   message bus and confirm an ``AuditRecord`` row lands in
   ``audit_records`` (the audit subscriber bridges bus topics into
   audit-writer ``capture_event`` calls).

If any of these links breaks, the alpha is not ready to ship.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import uuid

from automojo import testbase

from automojo.pychestrate.webservice.metadata import SITE_SHARED_GLOBALS

from automojo.tests.singlehost.pychestrate.webservice.phase10._e2e_harness import (
    drive_request,
    ensure_app,
    ensure_seeded_admin,
    ensure_seeded_admin_role,
    login_as,
)


def _wire_audit_bus_subscribers_for_tests() -> None:
    """
        Wire the audit-bus subscribers against the harness's
        session factory. The production runtime calls this from
        Phase-3 bootstrap; the harness skips Phase-3 wiring (see
        ``_bootstrap_runtime_for_tests``) so we install the
        subscriber explicitly here. Idempotent: ``subscribe()``
        appends but the audit-writer is keyed off
        ``source_event_id`` for dedup, so duplicates are
        harmless.
    """
    from automojo.pychestrate.webservice.audit.bus_subscriber import (  # noqa: E402
        wire_bus_subscribers,
    )
    factory = SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY
    wire_bus_subscribers(session_factory=factory)
    return


def _publish_test_project_created_event(*, project_id: str, actor_user_id: str) -> str:
    """
        Publish an ``entity.project.created`` event on the
        in-process bus and return the event's
        ``source_event_id`` so the caller can join against
        ``audit_records.source_event_id`` to verify capture.
    """
    from automojo.pychestrate.webservice.messaging.event_bus import (  # noqa: E402
        EntityEvent,
        publish,
    )
    source_event_id = str(uuid.uuid4())
    payload = {
        "actor_user_id": actor_user_id,
        "target_ref": "project:{}".format(project_id),
        "project_id": project_id,
        "name": "alpha-acceptance-project",
    }
    event = EntityEvent(
        topic="entity.project.created",
        payload=payload,
        source_event_id=source_event_id,
    )
    publish(event=event)
    return source_event_id


def _query_audit_event_by_source_id(*, source_event_id: str) -> bool:
    """
        Returns True if an :class:`AuditRecord` row exists with
        the given ``source_event_id``.
    """
    from automojo.pychestrate.webservice.audit.models import (  # noqa: E402
        AuditRecord,
    )
    factory = SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY
    db_session = factory()
    try:
        row = (
            db_session.query(AuditRecord)
            .filter(AuditRecord.source_event_id == source_event_id)
            .first()
        )
        rtnval = row is not None
        return rtnval
    finally:
        try:
            db_session.close()
        except Exception:
            pass


def test_alpha_acceptance_admin_login_rbac_audit_chain():
    """
    **Feature: alpha acceptance gate T20.1**
    **Property: The Phase-1 exit criterion is satisfied --
    a seeded admin can log in via the modern auth flow,
    pass the modern RBAC gate on an admin-only consumer-UI
    route, and an event published on the in-process bus
    lands in the audit_records table via the audit
    subscriber. Any regression in the auth flow, the
    rbac_evaluator wiring, the in-tree role/permission
    catalog, the consumer-UI gate, or the audit subscriber
    trips this test.**
    """
    # Step 1: bootstrap the runtime + harness DB. ensure_app()
    # is idempotent across modules; ensure_seeded_admin_role()
    # binds the modern "system-admin" role to the admin at
    # SYSTEM scope (see PR p13ad).
    handle = ensure_app()
    admin = ensure_seeded_admin()
    ensure_seeded_admin_role()

    # Step 2: wire the audit-bus subscriber. The harness skips
    # Phase-3 bootstrap, so this is the test's responsibility.
    _wire_audit_bus_subscribers_for_tests()

    # Step 3: log in as admin and recover the session cookie.
    cookies = login_as(wsgi_app=handle.wsgi_app, user=admin)
    testbase.assert_equal(len(cookies) > 0, True)

    # Step 4: drive a permission-gated route. /resources/create
    # is gated by ``system:resources.manage`` (see
    # ``resources/routes.py`` _ADMIN_PERMISSION). The gate
    # exercises ``ConsumerUISecurityAdapter.check_permission``
    # -> ``rbac_evaluator.check_permission``; if RBAC is wired
    # correctly the request is admitted (status NOT a redirect
    # to /resources or /login).
    response = drive_request(
        wsgi_app=handle.wsgi_app,
        method="GET",
        path="/resources/create",
        cookies=cookies,
    )
    location = response.header("Location") or ""
    is_login_redirect = location.endswith("/login")
    is_dashboard_deny = (
        response.status_code in (301, 302, 303, 307, 308)
        and location.endswith("/resources")
    )
    testbase.assert_equal(is_login_redirect, False)
    testbase.assert_equal(is_dashboard_deny, False)

    # Step 5: publish an entity.project.created event on the bus
    # and confirm the audit subscriber wrote a row.
    source_event_id = _publish_test_project_created_event(
        project_id=str(uuid.uuid4()),
        actor_user_id=admin.user_id,
    )
    audit_landed = _query_audit_event_by_source_id(
        source_event_id=source_event_id
    )
    testbase.assert_equal(audit_landed, True)
    return
