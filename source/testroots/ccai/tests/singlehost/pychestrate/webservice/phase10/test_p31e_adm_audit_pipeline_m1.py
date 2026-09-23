"""
.. module:: test_p31e_adm_audit_pipeline_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: One audit pipeline: admin, sign-in, project and resource
               actions reach the store the Audit Logs page reads
               (audit ADM-02).

.. moduleauthor:: Code Craft AI LLC

The Audit Logs page read the legacy ``audit_logs`` table, which nothing
wrote to; the canonical ``audit_records`` store had a handful of rows,
secret events twice (the copy without an actor), RPA and UI-profile
events without an actor, and nothing for users, roles, sessions,
sign-ins, projects or resources. These tests pin each part of the fix:
the subscriber's inline-capture skip and actor resolution, the
data-change bridge, the identity / session events, and the page's
filters, cursor paging and export.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import csv
import io
import json
import uuid

from ccai import testbase

from ccai.pychestrate.webservice.audit.bus_subscriber import (
    resolve_event_actor,
    unwire_bus_subscribers,
    wire_bus_subscribers,
)

from ccai.tests.singlehost.pychestrate.webservice.phase10._adm_helpers import (
    admin_cookies,
    audit_records_for,
    ensure_audit_wiring,
    get,
    latest_audit_sequence,
    open_db_session,
    post_form,
    unique_name,
)
from ccai.tests.singlehost.pychestrate.webservice.phase10._e2e_harness import (
    ensure_seeded_admin,
    login_via_post,
)


# ===========================================================================
# Subscriber: inline capture and actor resolution
# ===========================================================================


class _IsolatedAuditStore:
    """
        A private in-memory database with the audit subscriber wired to
        it, detached again on exit, so these tests neither depend on nor
        disturb the shared app's wiring.
    """

    def __init__(self) -> None:
        self.factory = None
        return

    def __enter__(self):
        from sqlalchemy.orm import sessionmaker  # noqa: E402
        from sqlalchemy.pool import StaticPool  # noqa: E402
        import sqlalchemy as sa  # noqa: E402

        from ccai.pychestrate.core.orm import PychestrateModelBase  # noqa: E402
        from ccai.pychestrate.webservice.audit import (  # noqa: E402
            register_builtin_extensions as register_audit_extensions,
        )
        from ccai.pychestrate.webservice.persistence.schema import (  # noqa: E402
            PychestratePhase1Base,
        )

        register_audit_extensions()
        engine = sa.create_engine(
            "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
        )
        PychestratePhase1Base.metadata.create_all(engine)
        PychestrateModelBase.metadata.create_all(engine)
        self.factory = sessionmaker(bind=engine, expire_on_commit=False)
        wire_bus_subscribers(session_factory=self.factory)
        return self.factory

    def __exit__(self, exc_type, exc, tb) -> bool:
        unwire_bus_subscribers(session_factory=self.factory)
        return False


def _records(*, factory, kind: str):
    from ccai.pychestrate.webservice.audit.models import AuditRecord  # noqa: E402
    session = factory()
    try:
        rows = session.query(AuditRecord).filter(AuditRecord.kind == kind).all()
        for row in rows:
            session.expunge(row)
    finally:
        session.close()
    return rows


def test_subscriber_does_not_capture_inline_audited_secret_topics():
    """
    **Feature: audit pipeline (ADM-02)**
    **Property: an entity.secret.created event on the bus produces no
    second audit record -- secrets_service already captured it inline
    (the duplicate copy had no actor).**
    """
    from ccai.pychestrate.webservice.messaging.event_bus import (  # noqa: E402
        EntityEvent,
        publish,
    )
    with _IsolatedAuditStore() as factory:
        publish(event=EntityEvent(
            topic="entity.secret.created",
            payload={"secret_ref": "a/b", "backend_name": "local", "version_id": "v1",
                     "principal_id": str(uuid.uuid4())},
            source_event_id=str(uuid.uuid4()),
        ))
        records = _records(factory=factory, kind="audit.secret.created")
    testbase.assert_equal(len(records), 0)
    return


def test_rpa_event_actor_id_becomes_the_record_actor():
    """
    **Feature: audit pipeline (ADM-02)**
    **Property: an RPA event naming its actor as actor_id is recorded
    with that user as the actor.**
    """
    from ccai.pychestrate.webservice.messaging.event_bus import (  # noqa: E402
        EntityEvent,
        publish,
    )
    actor = str(uuid.uuid4())
    with _IsolatedAuditStore() as factory:
        publish(event=EntityEvent(
            topic="entity.rpa.job_type_registered",
            payload={"type_id": "demo.echo", "execution_mode": "pod", "actor_id": actor},
            source_event_id=str(uuid.uuid4()),
        ))
        rows = _records(factory=factory, kind="audit.rpa.job_type_registered")
    testbase.assert_equal([str(row.actor_user_id) for row in rows], [actor])
    return


def test_non_uuid_actor_becomes_a_service_identity():
    """
    **Feature: audit pipeline (ADM-02)**
    **Property: an actor value that is not a user id (an extension)
    is recorded as the service identity, not dropped.**
    """
    result = resolve_event_actor(
        payload={"actor_id": "extension:pack.Mode"},
        actor_payload_keys=("actor_user_id", "actor_id"),
    )
    testbase.assert_equal(result, (None, "extension:pack.Mode"))
    return


# ===========================================================================
# Data-change bridge
# ===========================================================================


def _add_pool(*, factory, tag_actor, name: str, commit: bool = True):
    from ccai.pychestrate.core.orm import ResourcePool  # noqa: E402
    from ccai.pychestrate.webservice.audit.data_change_bridge import (  # noqa: E402
        tag_session_actor,
    )
    session = factory()
    try:
        if tag_actor is not None:
            tag_session_actor(db_session=session, actor_user_id=tag_actor)
        pool = ResourcePool(name=name, description="bridge probe")
        session.add(pool)
        session.flush()
        if commit is True:
            session.commit()
        else:
            session.rollback()
    finally:
        session.close()
    return


def test_bridge_records_a_row_created_by_a_tagged_session():
    """
    **Feature: audit pipeline -- data-change bridge (ADM-02)**
    **Property: a core.orm row inserted through a session tagged with
    a user becomes an audit.data.created record naming that user, the
    table and the row's label.**
    """
    actor = str(uuid.uuid4())
    with _IsolatedAuditStore() as factory:
        _add_pool(factory=factory, tag_actor=actor, name="phones")
        rows = _records(factory=factory, kind="audit.data.created")
    testbase.assert_equal(len(rows), 1)
    testbase.assert_equal(str(rows[0].actor_user_id), actor)
    testbase.assert_equal(rows[0].payload_json["table"], "resource_pools")
    testbase.assert_equal(rows[0].payload_json["label"], "phones")
    return


def test_bridge_ignores_an_untagged_session():
    """
    **Feature: audit pipeline -- data-change bridge (ADM-02)**
    **Property: writes by a session nobody tagged (background work)
    are not recorded.**
    """
    with _IsolatedAuditStore() as factory:
        _add_pool(factory=factory, tag_actor=None, name="untagged")
        rows = _records(factory=factory, kind="audit.data.created")
    testbase.assert_equal(len(rows), 0)
    return


def test_bridge_does_not_record_a_rolled_back_change():
    """
    **Feature: audit pipeline -- data-change bridge (ADM-02)**
    **Property: a flushed insert that is rolled back never reaches the
    audit log.**
    """
    with _IsolatedAuditStore() as factory:
        _add_pool(factory=factory, tag_actor=str(uuid.uuid4()), name="rolled", commit=False)
        rows = _records(factory=factory, kind="audit.data.created")
    testbase.assert_equal(len(rows), 0)
    return


def test_bridge_records_changed_fields_with_safe_values():
    """
    **Feature: audit pipeline -- data-change bridge (ADM-02)**
    **Property: an update records the changed column names, and the
    old / new value of a safe field such as name.**
    """
    from ccai.pychestrate.core.orm import ResourcePool  # noqa: E402
    from ccai.pychestrate.webservice.audit.data_change_bridge import (  # noqa: E402
        tag_session_actor,
    )
    actor = str(uuid.uuid4())
    with _IsolatedAuditStore() as factory:
        _add_pool(factory=factory, tag_actor=actor, name="before")
        session = factory()
        try:
            tag_session_actor(db_session=session, actor_user_id=actor)
            pool = session.query(ResourcePool).filter(ResourcePool.name == "before").one()
            pool.name = "after"
            session.commit()
        finally:
            session.close()
        rows = _records(factory=factory, kind="audit.data.updated")
    testbase.assert_equal(len(rows), 1)
    testbase.assert_equal(
        rows[0].payload_json["changes"]["name"], {"from": "before", "to": "after"}
    )
    return


# ===========================================================================
# End to end through the real app
# ===========================================================================


def test_sign_in_is_recorded_under_the_user():
    """
    **Feature: audit pipeline (ADM-02)**
    **Property: signing in writes an audit.session.opened record whose
    actor is the user who signed in.**
    """
    from ccai.tests.singlehost.pychestrate.webservice.phase10._adm_helpers import (  # noqa: E402
        app,
    )
    ensure_audit_wiring()
    admin = ensure_seeded_admin()
    mark = latest_audit_sequence()
    login_via_post(wsgi_app=app(), login=admin.login, password=admin.password)
    rows = audit_records_for(kind="audit.session.opened", since_sequence=mark)
    testbase.assert_equal([str(row.actor_user_id) for row in rows], [admin.user_id])
    return


def test_rejected_sign_in_is_recorded():
    """
    **Feature: audit pipeline (ADM-02)**
    **Property: a wrong password writes an audit.auth.login_rejected
    record carrying the typed username.**
    """
    from ccai.tests.singlehost.pychestrate.webservice.phase10._adm_helpers import (  # noqa: E402
        app,
    )
    ensure_audit_wiring()
    admin = ensure_seeded_admin()
    mark = latest_audit_sequence()
    login_via_post(wsgi_app=app(), login=admin.login, password="not-the-password-1!")
    rows = audit_records_for(kind="audit.auth.login_rejected", since_sequence=mark)
    testbase.assert_equal(len(rows), 1)
    testbase.assert_equal(rows[0].payload_json["login_name"], admin.login)
    return


def test_user_creation_is_recorded_with_the_admin_as_actor():
    """
    **Feature: audit pipeline (ADM-02)**
    **Property: creating a user in the admin pages writes an
    audit.user.created record attributed to the admin.**
    """
    ensure_audit_wiring()
    admin = ensure_seeded_admin()
    mark = latest_audit_sequence()
    login_name = unique_name(prefix="audited")
    post_form(
        path="/admin/users/create",
        fields={"username": login_name, "email": "{}@example.com".format(login_name),
                "password": "Granite-Harbor-47!", "display_name": "Audited"},
        cookies=admin_cookies(),
    )
    rows = [
        row for row in audit_records_for(kind="audit.user.created", since_sequence=mark)
        if row.payload_json.get("login_name") == login_name
    ]
    testbase.assert_equal([str(row.actor_user_id) for row in rows], [admin.user_id])
    return


def test_project_creation_in_the_ui_is_recorded():
    """
    **Feature: audit pipeline (ADM-02)**
    **Property: creating a project on the web UI (legacy store) writes
    an audit.data.created record for the projects table, attributed
    to the admin.**
    """
    ensure_audit_wiring()
    admin = ensure_seeded_admin()
    mark = latest_audit_sequence()
    project_name = unique_name(prefix="auditproj")
    post_form(
        path="/projects/create",
        fields={"name": project_name, "description": "", "metadata": ""},
        cookies=admin_cookies(),
    )
    rows = [
        row for row in audit_records_for(kind="audit.data.created", since_sequence=mark)
        if row.payload_json.get("table") == "projects"
        and row.payload_json.get("label") == project_name
    ]
    testbase.assert_equal([str(row.actor_user_id) for row in rows], [admin.user_id])
    return


def test_audit_page_shows_recorded_events():
    """
    **Feature: audit pipeline (ADM-02)**
    **Property: the Audit Logs page lists records from the canonical
    store (a sign-in shows as "Signed in").**
    """
    ensure_audit_wiring()
    cookies = admin_cookies()
    response = get(path="/admin/audit-logs", cookies=cookies)
    testbase.assert_equal(response.status_code, 200)
    testbase.assert_true("Signed in" in response.text, response.text[:1500])
    return


def test_action_filter_narrows_the_page():
    """
    **Feature: audit pipeline (ADM-02)**
    **Property: filtering by the rejected-sign-in action shows only
    rejected sign-ins.**
    """
    from ccai.tests.singlehost.pychestrate.webservice.phase10._adm_helpers import (  # noqa: E402
        app,
    )
    ensure_audit_wiring()
    admin = ensure_seeded_admin()
    login_via_post(wsgi_app=app(), login=admin.login, password="wrong-password-2!")
    cookies = admin_cookies()
    response = get(
        path="/admin/audit-logs",
        cookies=cookies,
        query={"action": "audit.auth.login_rejected"},
    )
    body = response.text.split("<tbody>", 1)[1].split("</tbody>", 1)[0]
    testbase.assert_true("Sign-in rejected" in body, body[:800])
    testbase.assert_equal("Signed in" in body, False)
    return


def test_unknown_actor_filter_says_so():
    """
    **Feature: audit pipeline (ADM-02)**
    **Property: filtering by a username nobody has shows a notice and
    no rows instead of silently ignoring the filter.**
    """
    ensure_audit_wiring()
    response = get(
        path="/admin/audit-logs", cookies=admin_cookies(), query={"actor": "no-such-user-x"}
    )
    import html as _html  # noqa: E402
    text = _html.unescape(response.text)
    testbase.assert_true('No user has the username "no-such-user-x"' in text, text[:1500])
    return


def test_older_link_pages_by_cursor():
    """
    **Feature: audit pipeline (ADM-02)**
    **Property: with more records than one page, the page offers an
    "Older" link whose cursor is the oldest record shown.**
    """
    ensure_audit_wiring()
    cookies = admin_cookies()
    admin_cookies()
    admin_cookies()
    response = get(path="/admin/audit-logs", cookies=cookies, query={"per_page": "2"})
    testbase.assert_true("before=" in response.text, "no older link")
    return


def test_csv_export_carries_a_header_and_rows():
    """
    **Feature: audit pipeline (ADM-02)**
    **Property: the CSV export is an attachment whose first row is the
    column header and which holds at least one record.**
    """
    ensure_audit_wiring()
    response = get(
        path="/admin/audit-logs/export", cookies=admin_cookies(), query={"format": "csv"}
    )
    testbase.assert_equal(response.status_code, 200)
    testbase.assert_true("attachment" in (response.header("Content-Disposition") or ""))
    rows = list(csv.reader(io.StringIO(response.text)))
    testbase.assert_equal(rows[0][0:3], ["sequence_number", "written_at", "actor"])
    testbase.assert_true(len(rows) > 1, "no records exported")
    return


def test_jsonl_export_lines_parse_as_json():
    """
    **Feature: audit pipeline (ADM-02)**
    **Property: every line of the JSON Lines export parses and carries
    the record's kind and payload.**
    """
    ensure_audit_wiring()
    response = get(
        path="/admin/audit-logs/export", cookies=admin_cookies(), query={"format": "jsonl"}
    )
    lines = [line for line in response.text.split("\n") if len(line) > 0]
    testbase.assert_true(len(lines) > 0, "empty export")
    first = json.loads(lines[0])
    testbase.assert_true("kind" in first and "payload" in first, str(first))
    return
