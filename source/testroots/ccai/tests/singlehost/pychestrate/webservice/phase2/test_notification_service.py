"""
.. module:: test_notification_service
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for 2-notification-hub M1 service surface.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai import testbase

from ccai.pychestrate.webservice.messaging.event_bus import subscribe
from ccai.pychestrate.webservice.notifications import service as notification_service
from ccai.pychestrate.webservice.notifications.exceptions import (
    ChannelAlreadyExistsError,
    ChannelNotFoundError,
)
from ccai.pychestrate.webservice.notifications.factories import smtp_email
from ccai.pychestrate.webservice.notifications.models import ChannelScopeLevel

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
)
from ccai.tests.singlehost.pychestrate.webservice.phase2.fixtures import (
    reset_phase2_runtime,
)


class _CapturingSmtpClient:
    """
        Minimal stand-in for ``smtplib.SMTP`` used to capture sends.
    """

    def __init__(self) -> None:
        self.sent_messages = []
        self.tls_started = False
        self.logged_in = False
        self.quit_called = False
        return

    def starttls(self):
        self.tls_started = True
        return

    def login(self, username, password):
        self.logged_in = True
        return

    def send_message(self, message):
        self.sent_messages.append(message)
        return

    def quit(self):
        self.quit_called = True
        return


def _install_capturing_smtp() -> _CapturingSmtpClient:
    """
        Replace :func:`smtp_email._open_smtp_client` with a capturing stub.
    """
    client = _CapturingSmtpClient()
    smtp_email._open_smtp_client = lambda *, host, port: client
    return client


def test_create_channel_round_trip_and_duplicate_conflict():
    """
    **Feature: 2-notification-hub (M1)**
    **Property: create_channel persists a row; a duplicate name in the
    same scope raises ChannelAlreadyExistsError.**
    """
    reset_phase2_runtime()
    _engine, session = build_in_memory_session()

    channel = notification_service.create_channel(
        db_session=session,
        name="ops-mail",
        kind="smtp_email",
        scope_level=ChannelScopeLevel.SYSTEM,
        project_id=None,
        config={"host": "smtp.example.com", "port": 25, "from_address": "ops@example.com"},
        actor_user_id=None,
    )
    testbase.assert_equal(channel.name, "ops-mail")

    fetched = notification_service.read_channel(
        db_session=session, channel_id=str(channel.channel_id),
    )
    testbase.assert_equal(fetched.kind, "smtp_email")

    raised = False
    try:
        notification_service.create_channel(
            db_session=session,
            name="ops-mail",
            kind="smtp_email",
            scope_level=ChannelScopeLevel.SYSTEM,
            project_id=None,
            config={"host": "smtp.example.com", "port": 25, "from_address": "ops@example.com"},
            actor_user_id=None,
        )
    except ChannelAlreadyExistsError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_read_channel_missing_raises():
    """
    **Feature: 2-notification-hub (M1)**
    **Property: read_channel on an unknown id raises ChannelNotFoundError.**
    """
    reset_phase2_runtime()
    _engine, session = build_in_memory_session()

    raised = False
    try:
        notification_service.read_channel(
            db_session=session,
            channel_id="00000000-0000-0000-0000-000000000000",
        )
    except ChannelNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_dispatch_envelope_delivers_and_publishes():
    """
    **Feature: 2-notification-hub (M1)**
    **Property: dispatch_envelope sends via the SMTP channel stub and
    publishes entity.notification.dispatched.**
    """
    reset_phase2_runtime()
    capturing = _install_capturing_smtp()
    _engine, session = build_in_memory_session()

    received = []
    subscribe(
        topic="entity.notification.dispatched",
        subscriber=lambda e: received.append(e),
    )

    channel = notification_service.create_channel(
        db_session=session,
        name="ops-mail",
        kind="smtp_email",
        scope_level=ChannelScopeLevel.SYSTEM,
        project_id=None,
        config={"host": "smtp.example.com", "port": 25, "from_address": "ops@example.com"},
        actor_user_id=None,
    )

    envelope = notification_service.dispatch_envelope(
        db_session=session,
        channel_id=str(channel.channel_id),
        recipient="oncall@example.com",
        event_topic="entity.run.failed",
        template_name="run_failed",
        payload={"run_id": "run-123", "project_slug": "demo", "reason": "timeout"},
    )

    testbase.assert_equal(envelope.recipient, "oncall@example.com")
    testbase.assert_equal(envelope.template_name, "run_failed")
    testbase.assert_equal(len(capturing.sent_messages), 1)
    testbase.assert_equal(len(received), 1)
    return
