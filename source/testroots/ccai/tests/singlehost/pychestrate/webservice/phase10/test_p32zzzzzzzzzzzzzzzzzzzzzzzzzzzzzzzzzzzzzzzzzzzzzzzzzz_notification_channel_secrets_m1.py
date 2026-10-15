"""
.. module:: test_notification_channel_secrets_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: A notification channel keeps secrets in the vault and nowhere else (audit ORG-F08).

.. moduleauthor:: Code Craft AI LLC

A channel's password or webhook address used to be stored as plain text in the channel's ``config`` (the only way to make one work, since the
``secret://`` resolver was a stub that handed the sender a ``{name, version}`` dictionary instead of the secret). Now a secret setting is stored in
the secrets vault and the channel keeps a ``secret://`` reference; the dispatcher reads the vault when it sends, and the plaintext is not stored,
logged, put on an envelope or an event.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import uuid as uuidmod

from typing import Any, ClassVar, Dict, List, Mapping, Tuple

from ccai import testbase

from ccai.pychestrate.core.defaults import new_uuid
from ccai.pychestrate.webservice.extensions import registry
from ccai.pychestrate.webservice.notifications import register_builtin_extensions as register_notifications
from ccai.pychestrate.webservice.notifications import service as notification_service
from ccai.pychestrate.webservice.notifications.channel_config import MASKED_VALUE
from ccai.pychestrate.webservice.notifications.exceptions import (
    ChannelConfigInvalidError,
    ChannelInUseError,
    ChannelSecretAccessDeniedError,
    NotificationDispatchError,
)
from ccai.pychestrate.webservice.notifications.restapi.v1 import channels_routes
from ccai.pychestrate.webservice.notifications.factories.channel import (
    ChannelConfigField,
    ChannelDeliveryOutcome,
    NotificationChannelProtocol,
)
from ccai.pychestrate.webservice.notifications.models import (
    ChannelScopeLevel,
    DispatchOutcome,
    NotificationChannel,
    NotificationDeadLetter,
    NotificationDispatchAttempt,
)
from ccai.pychestrate.webservice.persistence.schema import PychestratePhase1Base
from ccai.pychestrate.webservice.projects.models import Project
from ccai.pychestrate.webservice.secrets import secrets_service
from ccai.pychestrate.webservice.secrets.exceptions import SecretNotFoundError
from ccai.pychestrate.webservice.secrets.kek_loader import KekHandle, reset_active_kek_for_testing, set_active_kek
from ccai.pychestrate.webservice.secrets.models import SecretRecord, SecretScopeKind, SecretVersion
from ccai.pychestrate.webservice.secrets.secret_bytes import SecretBytes
from ccai.pychestrate.webservice.secrets.secrets_aspects import build_default_aspects
from ccai.pychestrate.webservice.security.auth.models import AuthProviderKind
from ccai.pychestrate.webservice.security.auth.session_service import AuthPrincipal
from ccai.pychestrate.webservice.security.rbac.models import BindingScope, PrincipalKind, RbacRole, RbacRoleBinding, RoleSource
from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import build_in_memory_session, reset_phase1_runtime


TOKEN: str = "tok-9f3a1c77-the-secret-value"
PASSWORD: str = "hunter2-correct-horse"
PROJECT_ID: str = "0f6c2c1e-7777-4000-8000-00000000000a"


class _SecretRecorder(NotificationChannelProtocol):
    """A channel with one secret setting that records what its sender is handed."""

    factory_protocol_name: ClassVar[str] = "notification_channel"
    protocol_schema_version: ClassVar[int] = 1
    channel_kind: ClassVar[str] = "test_secret_recorder"
    PRECEDENCE: ClassVar[int] = 1000
    config_fields: ClassVar[Tuple[ChannelConfigField, ...]] = (
        ChannelConfigField(name="endpoint", label="Endpoint", field_type="url"),
        ChannelConfigField(name="token", label="Token", secret=True),
    )
    seen: ClassVar[List[Dict[str, Any]]] = []

    @classmethod
    def send(cls, *, channel_config: Mapping[str, Any], recipient: str, subject: str, body: str) -> ChannelDeliveryOutcome:
        cls.seen.append(dict(channel_config))
        return ChannelDeliveryOutcome(delivered=True, error_message="", latency_ms=1)


def _principal(user_id: str) -> AuthPrincipal:
    return AuthPrincipal(user_id=user_id, session_id="sess-chsec", provider_kind=AuthProviderKind.LOCAL, provider_name="local")


def _world() -> Tuple[Any, AuthPrincipal]:
    """A fresh registry, a KEK, an in-memory database and a system administrator who may store secrets."""
    reset_phase1_runtime()
    register_notifications()
    registry.register_factory_implementation(implementation=_SecretRecorder)
    _SecretRecorder.seen = []
    reset_active_kek_for_testing()
    set_active_kek(kek=KekHandle(kek_id="test-kek-chsec", key_material=SecretBytes(b"K" * 32), source="test"))
    _engine, session = build_in_memory_session()
    admin_id = str(uuidmod.uuid4())
    role = RbacRole(role_id=new_uuid(), role_name="system-admin", source=RoleSource.BUILTIN, source_name="CorePermissionExtension", description="")
    session.add(role)
    session.flush()
    session.add(RbacRoleBinding(
        binding_id=new_uuid(), role_id=role.role_id, principal_kind=PrincipalKind.USER, principal_id=admin_id,
        scope_kind=BindingScope.SYSTEM, scope_id=None, inherits_into_project=False, created_by=None,
    ))
    session.add(Project(project_id=PROJECT_ID, slug="alpha", display_name="Alpha"))
    session.commit()
    return session, _principal(admin_id)


def _recorder(session: Any, admin: AuthPrincipal, name: str = "hook", **kwargs: Any) -> NotificationChannel:
    return notification_service.create_channel(
        db_session=session, name=name, kind="test_secret_recorder", scope_level=ChannelScopeLevel.SYSTEM, project_id=None,
        config=kwargs.pop("config", {"endpoint": "https://example.test/hook"}), actor_user_id=None,
        secrets=kwargs.pop("secrets", {"token": TOKEN}), principal=admin,
    )


def _send(session: Any, channel: NotificationChannel) -> Any:
    return notification_service.dispatch_envelope(
        db_session=session, channel_id=str(channel.channel_id), recipient="ops", event_topic="entity.run.failed",
        template_name="run_failed", payload={"run_id": "r-1", "project_slug": "alpha"},
    )


def _vault_secret(session: Any, name: str) -> str:
    read = secrets_service.read_secret_for_service(db_session=session, secret_ref=name, service_identity="test")
    try:
        return read.plaintext.reveal().decode("utf-8")
    finally:
        read.plaintext.close()


def _everything_stored(session: Any) -> str:
    """Every value of every row of every table, as one string."""
    parts: List[str] = []
    for table in PychestratePhase1Base.metadata.sorted_tables:
        for row in session.execute(table.select()).fetchall():
            parts.append(repr(tuple(row)))
    return "\n".join(parts)


def test_a_secret_given_as_plain_text_is_refused_and_nothing_is_stored():
    """
    **Feature: notification channel secrets (ORG-F08)**
    **Property: a secret setting sent as plain text in ``config`` is refused with a message that says where to put it; no channel and no vault
    secret is created.**
    """
    session, admin = _world()
    try:
        notification_service.create_channel(
            db_session=session, name="mail", kind="smtp_email", scope_level=ChannelScopeLevel.SYSTEM, project_id=None,
            config={"host": "smtp.example.test", "port": 587, "from_address": "p@example.test", "username": "u", "password": PASSWORD},
            actor_user_id=None, principal=admin,
        )
        refusal = ""
    except ChannelConfigInvalidError as xcpt:
        refusal = str(xcpt)

    testbase.assert_equal(
        (
            "cannot be given as plain text" in refusal and "Send the value in 'secrets'" in refusal and "no secret named" not in refusal and PASSWORD not in refusal,
            session.query(NotificationChannel).count(), session.query(SecretRecord).count(),
        ),
        (True, 0, 0),
    )
    session.close()
    return


def test_a_new_secret_goes_to_the_vault_and_the_channel_keeps_only_a_reference():
    """
    **Feature: notification channel secrets (ORG-F08)**
    **Property: a secret sent in ``secrets`` is stored in the vault under ``notifications.channel.<id>.<setting>`` (service-wide for a system
    channel, the project's for a project channel); the channel's config holds a ``secret://`` reference; the value is in no table in plain text and
    the REST view shows the reference.**
    """
    session, admin = _world()
    system_channel = _recorder(session, admin, name="system-hook")
    project_channel = notification_service.create_channel(
        db_session=session, name="project-hook", kind="test_secret_recorder", scope_level=ChannelScopeLevel.PROJECT, project_id=PROJECT_ID,
        config={"endpoint": "https://example.test/p"}, actor_user_id=None, secrets={"token": "project-token-value"}, principal=admin,
    )
    expected_name = "notifications.channel.{}.token".format(system_channel.channel_id)
    record = session.query(SecretRecord).filter(SecretRecord.secret_ref == expected_name).first()
    project_record = session.query(SecretRecord).filter(SecretRecord.secret_ref == "notifications.channel.{}.token".format(project_channel.channel_id)).first()
    shown = notification_service.describe_channel(channel=system_channel)
    stored_text = _everything_stored(session)

    testbase.assert_equal(
        (
            system_channel.config["token"], system_channel.config["endpoint"], _vault_secret(session, expected_name),
            record.scope_kind, project_record.scope_kind, shown, TOKEN in stored_text, "project-token-value" in stored_text,
        ),
        (
            "secret://" + expected_name, "https://example.test/hook", TOKEN,
            SecretScopeKind.ORG, SecretScopeKind.PROJECT,
            {"config": {"endpoint": "https://example.test/hook", "token": "secret://" + expected_name}, "unprotected_secret_fields": []},
            False, False,
        ),
    )
    session.close()
    return


def test_sending_reads_the_vault_and_the_plaintext_reaches_only_the_sender():
    """
    **Feature: notification channel secrets (ORG-F08)**
    **Property: the sender is handed the vault's current value; after the send the value is in no table (envelope, attempt, dead letter, outbox).**
    """
    session, admin = _world()
    channel = _recorder(session, admin)
    _send(session, channel)

    testbase.assert_equal(
        (_SecretRecorder.seen[0]["token"], _SecretRecorder.seen[0]["endpoint"], TOKEN in _everything_stored(session)),
        (TOKEN, "https://example.test/hook", False),
    )
    session.close()
    return


def test_rotating_a_secret_is_followed_by_the_channel():
    """
    **Feature: notification channel secrets (ORG-F08)**
    **Property: a new value in ``secrets`` is a new version of the channel's own vault secret; the reference does not change and the next send
    uses the new value.**
    """
    session, admin = _world()
    channel = _recorder(session, admin)
    reference_before = channel.config["token"]
    notification_service.update_channel(db_session=session, channel_id=str(channel.channel_id), secrets={"token": "rotated-value"}, principal=admin)
    _send(session, channel)
    name = reference_before[len("secret://"):]
    versions = session.query(SecretVersion).join(SecretRecord, SecretRecord.secret_ref == name).count()

    testbase.assert_equal(
        (channel.config["token"] == reference_before, _SecretRecorder.seen[-1]["token"], versions >= 2, "rotated-value" in _everything_stored(session)),
        (True, "rotated-value", True, False),
    )
    session.close()
    return


def test_a_missing_secret_fails_the_delivery_readably_and_never_shows_a_value():
    """
    **Feature: notification channel secrets (ORG-F08)**
    **Property: when the vault secret has gone, the delivery is recorded as failed and parked, with a message naming the channel and the setting;
    nothing raises into the caller of the router and no value appears.**
    """
    session, admin = _world()
    channel = _recorder(session, admin, name="gone-hook")
    name = channel.config["token"][len("secret://"):]
    secrets_service.delete_secret(db_session=session, principal=admin, secret_ref=name, aspects=build_default_aspects())
    try:
        _send(session, channel)
        raised = False
    except NotificationDispatchError:
        raised = True
    attempt = session.query(NotificationDispatchAttempt).first()

    testbase.assert_equal(
        (
            raised, attempt.outcome, "gone-hook" in attempt.error_message and "'token'" in attempt.error_message and "Notifications page" in attempt.error_message,
            session.query(NotificationDeadLetter).count(), len(_SecretRecorder.seen),
        ),
        (True, DispatchOutcome.FAILED, True, 1, 0),
    )
    session.close()
    return


def test_replaying_a_parked_delivery_reads_the_vault_too():
    """
    **Feature: notification channel secrets (ORG-F08)**
    **Property: a dead-lettered delivery replayed after its secret is restored reaches the sender with the plaintext, not with ``secret://`` text.**
    """
    session, admin = _world()
    channel = _recorder(session, admin, name="replay-hook")
    name = channel.config["token"][len("secret://"):]
    secrets_service.delete_secret(db_session=session, principal=admin, secret_ref=name, aspects=build_default_aspects())
    try:
        _send(session, channel)
    except NotificationDispatchError:
        pass
    envelope_id = str(session.query(NotificationDeadLetter).first().envelope_id)
    notification_service.update_channel(db_session=session, channel_id=str(channel.channel_id), secrets={"token": "restored-value"}, principal=admin)
    notification_service.replay_dead_letter(db_session=session, envelope_id=envelope_id)

    testbase.assert_equal(
        (_SecretRecorder.seen[-1]["token"], session.query(NotificationDeadLetter).count()),
        ("restored-value", 0),
    )
    session.close()
    return


def test_an_existing_vault_secret_can_be_used_only_by_someone_who_may_read_it():
    """
    **Feature: notification channel secrets (ORG-F08)**
    **Property: ``config.<setting> = "secret://<name>"`` binds an existing vault secret for a user who may read it; a user who may not is refused;
    a name that does not exist, or one with a pinned version, is refused with a message.**
    """
    session, admin = _world()
    secrets_service.put_secret(db_session=session, principal=admin, secret_ref="shared.hook.token", plaintext=SecretBytes(b"shared-token"), aspects=build_default_aspects())
    session.commit()
    stranger = _principal(str(uuidmod.uuid4()))

    def attempt(who: AuthPrincipal, ref: str) -> str:
        try:
            made = notification_service.create_channel(
                db_session=session, name="bound-{}".format(uuidmod.uuid4().hex[:6]), kind="test_secret_recorder", scope_level=ChannelScopeLevel.SYSTEM,
                project_id=None, config={"endpoint": "https://example.test/h", "token": ref}, actor_user_id=None, principal=who,
            )
            return "made:" + made.config["token"]
        except ChannelSecretAccessDeniedError:
            return "denied"
        except ChannelConfigInvalidError as xcpt:
            return "invalid:" + str(xcpt)

    results = (
        attempt(admin, "secret://shared.hook.token"),
        attempt(stranger, "secret://shared.hook.token"),
        attempt(admin, "secret://no.such.secret"),
        attempt(admin, "secret://shared.hook.token#v2"),
    )
    testbase.assert_equal(
        (results[0], results[1], "no secret named no.such.secret" in results[2], "current version" in results[3]),
        ("made:secret://shared.hook.token", "denied", True, True),
    )
    session.close()
    return


def test_every_problem_with_the_settings_is_reported_at_once():
    """
    **Feature: notification channel secrets (ORG-F08)**
    **Property: a missing required setting, an unknown setting, a wrong shape and an address that is not http(s) are all named in one refusal, so a
    form can show them together; a ``file://`` address is refused.**
    """
    session, admin = _world()
    problems: List[str] = []
    for kind, config, secrets in (
        ("smtp_email", {"hots": "x", "port": "abc"}, None),
        ("slack_webhook", {}, {"url": "file:///etc/passwd"}),
        ("generic_webhook", {"url": "ftp://example.test/x"}, None),
    ):
        try:
            notification_service.create_channel(
                db_session=session, name="bad-" + kind, kind=kind, scope_level=ChannelScopeLevel.SYSTEM, project_id=None,
                config=config, actor_user_id=None, secrets=secrets, principal=admin,
            )
        except ChannelConfigInvalidError as xcpt:
            problems.append(str(xcpt))
    text = "\n".join(problems)

    testbase.assert_equal(
        (
            "'hots' is not a setting" in text, "Mail server ('host') is required" in text, "From address ('from_address') is required" in text,
            "Port ('port') must be a whole number" in text, "Webhook URL ('url') must be an address starting http:// or https://" in text,
            "Address ('url') must be an address starting http:// or https://" in text, session.query(NotificationChannel).count(),
        ),
        (True, True, True, True, True, True, 0),
    )
    session.close()
    return


def test_a_channel_made_before_secrets_went_to_the_vault_still_sends_but_is_shown_masked():
    """
    **Feature: notification channel secrets (ORG-F08)**
    **Property: a channel that still holds its password as plain text keeps sending (upgrading breaks nothing), but every read shows it masked and
    lists it under ``unprotected_secret_fields`` so the page can ask for it to be replaced; replacing it moves it into the vault.**
    """
    session, admin = _world()
    legacy = NotificationChannel(
        channel_id=new_uuid(), name="legacy", kind="test_secret_recorder", scope_level=ChannelScopeLevel.SYSTEM, project_id=None,
        config={"endpoint": "https://example.test/old", "token": "legacy-plain-token"}, disabled=False,
    )
    session.add(legacy)
    session.commit()
    shown = notification_service.describe_channel(channel=legacy)
    _send(session, legacy)
    sent = _SecretRecorder.seen[-1]["token"]
    notification_service.update_channel(db_session=session, channel_id=str(legacy.channel_id), secrets={"token": "moved-token"}, principal=admin)
    after = notification_service.describe_channel(channel=legacy)

    testbase.assert_equal(
        (shown["config"]["token"], shown["unprotected_secret_fields"], sent, after["unprotected_secret_fields"], after["config"]["token"].startswith("secret://"), "legacy-plain-token" in _everything_stored(session)),
        (MASKED_VALUE, ["token"], "legacy-plain-token", [], True, False),
    )
    session.close()
    return


def test_a_channel_cannot_be_deleted_while_a_rule_sends_through_it_and_takes_only_its_own_secrets():
    """
    **Feature: notification channel secrets (ORG-F08)**
    **Property: deleting a channel is refused (naming the rule) while a routing rule uses it; once the rule is gone the channel and the vault secrets
    the service stored for it are removed, and a vault secret it merely pointed at stays.**
    """
    session, admin = _world()
    secrets_service.put_secret(db_session=session, principal=admin, secret_ref="shared.keep.token", plaintext=SecretBytes(b"keep"), aspects=build_default_aspects())
    session.commit()
    own = _recorder(session, admin, name="own")
    bound = _recorder(session, admin, name="bound", config={"endpoint": "https://example.test/b", "token": "secret://shared.keep.token"}, secrets={})
    rule = notification_service.create_routing_rule(
        db_session=session, project_id=None, event_pattern="entity.run.failed", template_name="run_failed", channel_ids=[str(own.channel_id)],
        recipients=["ops"], filter_tag_expression=None, rate_limit_per_minute=None, actor_user_id=None,
    )
    own_name = own.config["token"][len("secret://"):]
    try:
        notification_service.delete_channel(db_session=session, channel_id=str(own.channel_id), principal=admin)
        refusal = ""
    except ChannelInUseError as xcpt:
        refusal = str(xcpt)
    notification_service.delete_routing_rule(db_session=session, rule_id=str(rule.rule_id))
    notification_service.delete_channel(db_session=session, channel_id=str(own.channel_id), principal=admin)
    notification_service.delete_channel(db_session=session, channel_id=str(bound.channel_id), principal=admin)
    try:
        _vault_secret(session, own_name)
        own_left = True
    except SecretNotFoundError:
        own_left = False

    testbase.assert_equal(
        ("entity.run.failed" in refusal, own_left, _vault_secret(session, "shared.keep.token"), session.query(NotificationChannel).count()),
        (True, False, "keep", 0),
    )
    session.close()
    return


def test_a_test_message_reports_the_outcome_and_cannot_be_used_by_a_rule():
    """
    **Feature: notification channel secrets (ORG-F08)**
    **Property: a test message goes through the channel (secrets and all) and returns delivered or the reason; the ``channel_test`` template is
    never routed for a real event.**
    """
    from ccai.pychestrate.webservice.notifications import router

    session, admin = _world()
    channel = _recorder(session, admin, name="probe")
    good = notification_service.send_test_message(db_session=session, channel_id=str(channel.channel_id), recipient="ops", sent_by="an admin")
    secrets_service.delete_secret(db_session=session, principal=admin, secret_ref=channel.config["token"][len("secret://"):], aspects=build_default_aspects())
    bad = notification_service.send_test_message(db_session=session, channel_id=str(channel.channel_id), recipient="ops", sent_by="an admin")
    rule = notification_service.create_routing_rule(
        db_session=session, project_id=None, event_pattern="entity.run.*", template_name="channel_test", channel_ids=[str(channel.channel_id)],
        recipients=["ops"], filter_tag_expression=None, rate_limit_per_minute=None, actor_user_id=None,
    )
    routed = router.route_event(db_session=session, topic="entity.run.failed", payload={"project_id": None, "run_id": "r-1", "project_slug": "alpha"})
    reasons = sorted(str(getattr(outcome, "skipped_reason", "")) for outcome in routed)

    testbase.assert_equal(
        (good.delivered, bad.delivered, "probe" in bad.error_message, _SecretRecorder.seen[-1]["token"] == TOKEN, reasons),
        (True, False, True, True, ["template_not_for_event"]),
    )
    session.close()
    return


class _Request:
    """The parts of a webworks request the channel routes read."""

    def __init__(self, *, session: Any, admin: AuthPrincipal, body: Any = None, channel_id: str = "") -> None:
        self.path = "/api/v1/notifications/channels"
        self.path_params = {"channel_id": channel_id}
        self.query_params = type("Q", (), {"get": lambda self, key, default=None: default})()
        self._body = body
        self.db_session = session
        self.auth_principal = admin
        self.actor_user_id = admin.user_id

    def json(self) -> Any:
        return self._body


def _body(response: Any) -> Any:
    return json.loads(response.body.decode("utf-8")) if response.body else None


def test_the_rest_create_keeps_secrets_in_the_vault_and_shows_only_references():
    """
    **Feature: notification channel secrets (ORG-F08)**
    **Property: POST with secrets answers 201 with a secret:// reference in config; the value is in neither the create answer, the read
    answer nor the list answer; a plain-text secret is a 400 problem that carries the list of problems.**
    """
    session, admin = _world()
    created = channels_routes.handle_create_channel(_Request(session=session, admin=admin, body={
        "name": "rest-hook", "kind": "test_secret_recorder", "scope_level": "SYSTEM",
        "config": {"endpoint": "https://example.test/rest"}, "secrets": {"token": TOKEN},
    }))
    channel_id = _body(created)["channel_id"]
    read = channels_routes.handle_read_channel(_Request(session=session, admin=admin, channel_id=channel_id))
    listed = channels_routes.handle_list_channels(_Request(session=session, admin=admin))
    refused = channels_routes.handle_create_channel(_Request(session=session, admin=admin, body={
        "name": "plain", "kind": "test_secret_recorder", "scope_level": "SYSTEM", "config": {"endpoint": "https://example.test/x", "token": "plain-text-token"},
    }))
    refusal = _body(refused)

    testbase.assert_equal(
        (
            created.status_code, _body(created)["config"]["token"].startswith("secret://notifications.channel."),
            TOKEN in created.body.decode() + read.body.decode() + listed.body.decode(),
            refused.status_code, "cannot be given as plain text" in refusal["detail"], len(refusal["problems"]),
        ),
        (201, True, False, 400, True, 1),
    )
    session.close()
    return


def test_the_rest_change_delete_and_test_routes():
    """
    **Feature: notification channel secrets (ORG-F08)**
    **Property: PATCH switches a channel off and rotates its secret and refuses unknown members; the test route reports delivery (400 without a
    recipient, 404 for an unknown channel); DELETE is 409 while a rule uses the channel, then 204, then 404.**
    """
    session, admin = _world()
    created = channels_routes.handle_create_channel(_Request(session=session, admin=admin, body={
        "name": "rest-ops", "kind": "test_secret_recorder", "scope_level": "SYSTEM", "config": {"endpoint": "https://example.test/r"}, "secrets": {"token": TOKEN},
    }))
    channel_id = _body(created)["channel_id"]
    off = channels_routes.handle_update_channel(_Request(session=session, admin=admin, channel_id=channel_id, body={"disabled": True}))
    rotated = channels_routes.handle_update_channel(_Request(session=session, admin=admin, channel_id=channel_id, body={"secrets": {"token": "second-value"}}))
    unknown = channels_routes.handle_update_channel(_Request(session=session, admin=admin, channel_id=channel_id, body={"name": "x"}))
    empty = channels_routes.handle_update_channel(_Request(session=session, admin=admin, channel_id=channel_id, body={}))
    tested = channels_routes.handle_test_channel(_Request(session=session, admin=admin, channel_id=channel_id, body={"recipient": "ops"}))
    no_recipient = channels_routes.handle_test_channel(_Request(session=session, admin=admin, channel_id=channel_id, body={}))
    missing = channels_routes.handle_test_channel(_Request(session=session, admin=admin, channel_id=str(uuidmod.uuid4()), body={"recipient": "ops"}))
    rule = notification_service.create_routing_rule(
        db_session=session, project_id=None, event_pattern="entity.run.failed", template_name="run_failed", channel_ids=[channel_id],
        recipients=["ops"], filter_tag_expression=None, rate_limit_per_minute=None, actor_user_id=None,
    )
    in_use = channels_routes.handle_delete_channel(_Request(session=session, admin=admin, channel_id=channel_id))
    notification_service.delete_routing_rule(db_session=session, rule_id=str(rule.rule_id))
    deleted = channels_routes.handle_delete_channel(_Request(session=session, admin=admin, channel_id=channel_id))
    again = channels_routes.handle_delete_channel(_Request(session=session, admin=admin, channel_id=channel_id))

    testbase.assert_equal(
        (
            _body(off)["disabled"], rotated.status_code, "second-value" in rotated.body.decode(), unknown.status_code, empty.status_code,
            _body(tested), no_recipient.status_code, missing.status_code, in_use.status_code, deleted.status_code, again.status_code,
        ),
        (True, 200, False, 400, 400, {"delivered": True, "error_message": "", "latency_ms": 1}, 400, 404, 409, 204, 404),
    )
    session.close()
    return
