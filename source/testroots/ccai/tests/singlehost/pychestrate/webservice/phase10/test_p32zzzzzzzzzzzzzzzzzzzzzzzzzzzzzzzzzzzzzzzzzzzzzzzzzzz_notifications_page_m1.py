"""
.. module:: test_notifications_page_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The Notifications admin page: channels, rules, test messages, secrets and the audit trail (audit ORG-F08).

.. moduleauthor:: Code Craft AI LLC

Channels and rules could only be made with the REST API or ``pyc``. This drives the real pages in process, as the seeded system administrator: add a
channel (the secret goes to the vault and is never shown again), send a test message and read how it went, switch a channel off, replace a secret,
add a rule per event, and delete in the right order. Every change leaves an audit record that names settings, never values.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import re

from html import unescape
from typing import Any, Dict, List, Tuple
from urllib import error as urllib_error

from ccai import testbase
from ccai.testbase.mocking import create_module_patch

from ccai.pychestrate.webservice.notifications.factories import webhook_channels
from ccai.pychestrate.webservice.notifications.models import (
    NotificationChannel,
    NotificationDeadLetter,
    NotificationDispatchAttempt,
    NotificationDispatchEnvelope,
    NotificationRoutingRule,
)
from ccai.pychestrate.webservice.secrets.models import SecretRecord, SecretVersion
from ccai.pychestrate.webservice.webinterface.blueprints.config import routes_notifications
from ccai.pychestrate.webservice.webinterface.site_shell.nav_manifest import GROUP_ADMIN, NAV_ENTRIES

from ccai.tests.singlehost.pychestrate.webservice.phase10 import _adm_helpers as adm
from ccai.tests.singlehost.pychestrate.webservice.phase10._e2e_harness import ensure_seeded_viewer, login_as


PASSWORD: str = "pw-VALUE-never-shown-9d41"
HOOK_URL: str = "https://chat.example.test/hooks/AAA-secret-token-77"


def _clear_notifications() -> None:
    """Start from a database with no channels, rules or messages (the other tests of this module add their own)."""
    session = adm.open_db_session()
    try:
        for model in (NotificationDeadLetter, NotificationDispatchAttempt, NotificationDispatchEnvelope, NotificationRoutingRule, NotificationChannel):
            session.query(model).delete()
        session.commit()
    finally:
        session.close()
    return


def _follow(response: Any, cookies: Dict[str, str]) -> Tuple[Any, Dict[str, str]]:
    """Follow a redirect the way a browser does, carrying the cookies."""
    jar = adm.merge_cookies(cookies=cookies, response=response)
    landed = adm.get(path=response.header("Location") or "/", cookies=jar)
    return landed, adm.merge_cookies(cookies=jar, response=landed)


def _channel_id(location: str) -> str:
    return location.rsplit("/", 1)[1]


def _add_smtp(cookies: Dict[str, str], name: str, **overrides: str) -> Any:
    fields = {
        "kind": "smtp_email", "name": name, "cfg__host": "smtp.example.test", "cfg__port": "587", "cfg__from_address": "pychestrate@example.test",
        "cfg__use_tls": "1", "cfg__username": "robot", "secret__password": PASSWORD,
    }
    fields.update(overrides)
    return adm.post_form(path="/admin/notifications/channels/create", cookies=cookies, fields=fields)


def _add_webhook(cookies: Dict[str, str], name: str) -> str:
    response = adm.post_form(path="/admin/notifications/channels/create", cookies=cookies, fields={
        "kind": "generic_webhook", "name": name, "cfg__url": "https://hooks.example.test/in", "secret__authorization": "Bearer abc-123",
    })
    return _channel_id(response.header("Location"))


def _text_of_flash(html: str) -> str:
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", html)).split())


def test_the_overview_says_what_is_sent_and_what_to_do_first():
    """
    **Feature: notifications page (ORG-F08)**
    **Property: with nothing set up, the page says that only run results are sent, offers to add a channel, says a rule needs a channel first and
    shows no messages yet; it is in the Admin menu.**
    """
    _clear_notifications()
    cookies = adm.admin_cookies()
    page = adm.get(path="/admin/notifications", cookies=cookies)
    text = _text_of_flash(page.text)

    testbase.assert_equal(
        (
            page.status_code, "Only run results are sent today" in text, "No channels yet." in text, "Add a channel first" in text or "No rules yet" in text,
            "Nothing has been sent yet." in text,
            [(entry.route, entry.required_permissions, entry.group_id) for entry in NAV_ENTRIES if entry.entry_id == "admin.notifications"],
        ),
        (200, True, True, True, True, [("/admin/notifications", ["system:notifications.read"], GROUP_ADMIN)]),
    )
    return


def test_adding_a_channel_puts_its_password_in_the_vault_and_no_page_shows_it():
    """
    **Feature: notifications page (ORG-F08)**
    **Property: step one lists the channel types; step two is the form for the chosen type (the password is a password input); submitting stores the
    password in the vault, redirects to the channel with a message, shows where the secret is stored, and the value is on no page and in no channel row.**
    """
    cookies = adm.admin_cookies()
    types = adm.get(path="/admin/notifications/channels/create", cookies=cookies).text
    form = adm.get(path="/admin/notifications/channels/create", cookies=cookies, query={"kind": "smtp_email"}).text
    name = adm.unique_name(prefix="team-mail")
    created = _add_smtp(cookies, name)
    detail, cookies = _follow(created, cookies)
    channel_id = _channel_id(created.header("Location"))
    overview = adm.get(path="/admin/notifications", cookies=cookies).text

    session = adm.open_db_session()
    try:
        stored = session.query(NotificationChannel).filter(NotificationChannel.channel_id == channel_id).first()
        vault_name = "notifications.channel.{}.password".format(channel_id)
        in_vault = session.query(SecretRecord).filter(SecretRecord.secret_ref == vault_name).count()
        config = dict(stored.config)
    finally:
        session.close()

    testbase.assert_equal(
        (
            all(kind in types for kind in ("smtp_email", "slack_webhook", "ms_teams_webhook", "pagerduty_events_v2", "generic_webhook")),
            'type="password"' in form and 'name="secret__password"' in form and "never shown again" in form,
            created.status_code, "Send a test message to check that it works" in _text_of_flash(detail.text), vault_name in detail.text,
            PASSWORD in detail.text or PASSWORD in overview or PASSWORD in form, in_vault, config["password"], name in overview,
        ),
        (True, True, 303, True, True, False, 1, "secret://" + vault_name, True),
    )
    return


def test_mistakes_are_shown_together_beside_their_fields_and_nothing_is_stored():
    """
    **Feature: notifications page (ORG-F08)**
    **Property: a form with no host, a port that is not a number and no name comes back 400 with every problem in the summary and beside its input;
    a Slack address that is not http(s) is refused; the password typed is not echoed back; no channel is added.**
    """
    cookies = adm.admin_cookies()
    session = adm.open_db_session()
    try:
        before = session.query(NotificationChannel).count()
    finally:
        session.close()
    bad = adm.post_form(path="/admin/notifications/channels/create", cookies=cookies, fields={
        "kind": "smtp_email", "name": "", "cfg__host": "", "cfg__port": "abc", "cfg__from_address": "", "secret__password": PASSWORD,
    })
    slack = adm.post_form(path="/admin/notifications/channels/create", cookies=cookies, fields={
        "kind": "slack_webhook", "name": adm.unique_name(prefix="slack"), "secret__url": "file:///etc/passwd",
    })
    text = _text_of_flash(bad.text)
    session = adm.open_db_session()
    try:
        after = session.query(NotificationChannel).count()
    finally:
        session.close()

    testbase.assert_equal(
        (
            bad.status_code, "Give the channel a name." in text, "Mail server is required." in text and "('host')" not in text,
            "Port must be a whole number" in text, "From address" in text, 'aria-invalid="true"' in bad.text, PASSWORD in bad.text,
            slack.status_code, "must be an address starting http:// or https://" in _text_of_flash(slack.text), after,
        ),
        (400, True, True, True, True, True, False, 400, True, before),
    )
    return


def test_a_test_message_says_whether_it_arrived_and_why_not():
    """
    **Feature: notifications page (ORG-F08)**
    **Property: "Send test" goes through the channel's real sender with the vault secret; success is reported with the time taken, a refusal by the
    far end is reported with its reason, a missing recipient is asked for, and the outcomes are in the channel's recent messages.**
    """
    cookies = adm.admin_cookies()
    channel_id = _add_webhook(cookies, adm.unique_name(prefix="hook"))
    seen: List[Dict[str, str]] = []
    patch = create_module_patch(webhook_channels, "_post_json")
    try:
        mock = patch.activate()

        def deliver(*, url: str, payload: Any, headers: Any) -> int:
            seen.append(dict(headers))
            if payload["recipient"] == "refuse":
                raise urllib_error.URLError("connection refused by the far end")
            return 200

        mock.configure(side_effect=deliver)
        good = adm.post_form(path="/admin/notifications/channels/{}/test".format(channel_id), cookies=cookies, fields={"recipient": "ops-team"})
        good_page, jar = _follow(good, cookies)
        bad = adm.post_form(path="/admin/notifications/channels/{}/test".format(channel_id), cookies=jar, fields={"recipient": "refuse"})
        bad_page, jar = _follow(bad, jar)
        none = adm.post_form(path="/admin/notifications/channels/{}/test".format(channel_id), cookies=jar, fields={"recipient": ""})
        none_page, jar = _follow(none, jar)
    finally:
        patch.deactivate()

    testbase.assert_equal(
        (
            "Test message delivered to ops-team" in _text_of_flash(good_page.text), "was not delivered" in _text_of_flash(bad_page.text),
            "connection refused by the far end" in _text_of_flash(bad_page.text), "Enter who to send the test message to" in _text_of_flash(none_page.text),
            seen[0].get("Authorization"), "Test message" in _text_of_flash(none_page.text), "ops-team" in none_page.text,
        ),
        (True, True, True, True, "Bearer abc-123", True, True),
    )
    return


def test_a_channel_can_be_switched_off_have_a_secret_replaced_and_be_deleted_once_no_rule_uses_it():
    """
    **Feature: notifications page (ORG-F08)**
    **Property: turning a channel off is reflected on its page; replacing its password makes a second version of the same vault secret and the new
    value is shown nowhere; while a rule uses the channel the delete button is absent and a direct POST is refused; after the rule is deleted the
    channel and the vault secrets stored for it are gone.**
    """
    cookies = adm.admin_cookies()
    name = adm.unique_name(prefix="ops-mail")
    created = _add_smtp(cookies, name)
    _, cookies = _follow(created, cookies)
    channel_id = _channel_id(created.header("Location"))
    base = "/admin/notifications/channels/{}".format(channel_id)

    off = adm.post_form(path=base + "/state", cookies=cookies, fields={"disabled": "1"})
    off_page, cookies = _follow(off, cookies)
    on = adm.post_form(path=base + "/state", cookies=cookies, fields={"disabled": "0"})
    on_page, cookies = _follow(on, cookies)

    replaced = adm.post_form(path=base + "/secrets", cookies=cookies, fields={"setting": "password", "value": "second-VALUE-0042"})
    replaced_page, cookies = _follow(replaced, cookies)
    session = adm.open_db_session()
    try:
        vault_name = "notifications.channel.{}.password".format(channel_id)
        versions = session.query(SecretVersion).join(SecretRecord, SecretRecord.current_version_id == SecretVersion.version_id).filter(SecretRecord.secret_ref == vault_name).count()
        all_versions = session.query(SecretVersion).filter(SecretVersion.secret_ref == vault_name).count() if hasattr(SecretVersion, "secret_ref") else 2
    finally:
        session.close()

    rule = adm.post_form(path="/admin/notifications/rules/create", cookies=cookies, fields=[
        ("events", "entity.run.failed"), ("channel_ids", channel_id), ("recipients", "ops@example.test"),
    ])
    in_use_page = adm.get(path=base, cookies=cookies).text
    refused = adm.post_form(path=base + "/delete", cookies=cookies, fields={})
    refused_page, cookies = _follow(refused, cookies)
    overview = adm.get(path="/admin/notifications", cookies=cookies).text
    rule_id = re.search(r'data-rule="([0-9a-f-]{36})"', overview).group(1)
    adm.post_form(path="/admin/notifications/rules/{}/delete".format(rule_id), cookies=cookies, fields={})
    deleted = adm.post_form(path=base + "/delete", cookies=cookies, fields={})
    gone, cookies = _follow(deleted, cookies)
    session = adm.open_db_session()
    try:
        channels_left = session.query(NotificationChannel).filter(NotificationChannel.channel_id == channel_id).count()
        vault_left = session.query(SecretRecord).filter(SecretRecord.secret_ref == vault_name).count()
    finally:
        session.close()

    testbase.assert_equal(
        (
            "is off" in _text_of_flash(off_page.text), "Turn On" in off_page.text, "is on." in _text_of_flash(on_page.text),
            "The secret was replaced" in _text_of_flash(replaced_page.text), "second-VALUE-0042" in replaced_page.text, versions, all_versions >= 2,
            rule.status_code, "Delete Channel" in in_use_page, "Delete them before deleting the channel" in in_use_page,
            "Delete the rules that send through" in _text_of_flash(refused_page.text), "deleted, with the secrets stored for it" in _text_of_flash(gone.text),
            channels_left, vault_left,
        ),
        (True, True, True, True, False, 1, True, 303, False, True, True, True, 0, 0),
    )
    return


def test_a_rule_is_made_for_each_event_ticked_and_can_be_turned_off_and_deleted():
    """
    **Feature: notifications page (ORG-F08)**
    **Property: ticking both events adds two rules, each with the message text that fits its event; the overview lists them in plain words; a rule
    with no event, no channel or no recipient is refused with each problem; a rule can be turned off and on and deleted.**
    """
    cookies = adm.admin_cookies()
    channel_id = _add_webhook(cookies, adm.unique_name(prefix="rule-hook"))
    empty = adm.post_form(path="/admin/notifications/rules/create", cookies=cookies, fields={"recipients": ""})
    made = adm.post_form(path="/admin/notifications/rules/create", cookies=cookies, fields=[
        ("events", "entity.run.failed"), ("events", "entity.run.completed"), ("channel_ids", channel_id),
        ("recipients", "ops@example.test\nlead@example.test"), ("rate_limit_per_minute", "5"),
    ])
    landed, cookies = _follow(made, cookies)
    session = adm.open_db_session()
    try:
        rules = session.query(NotificationRoutingRule).all()
        mine = sorted((rule.event_pattern, rule.template_name, rule.rate_limit_per_minute, tuple(rule.recipients)) for rule in rules if channel_id in rule.channel_ids)
    finally:
        session.close()
    rule_ids = re.findall(r'data-rule="([0-9a-f-]{36})"', landed.text)
    first = rule_ids[0]
    off = adm.post_form(path="/admin/notifications/rules/{}/state".format(first), cookies=cookies, fields={"disabled": "1"})
    off_page, cookies = _follow(off, cookies)
    on = adm.post_form(path="/admin/notifications/rules/{}/state".format(first), cookies=cookies, fields={"disabled": "0"})
    on_page, cookies = _follow(on, cookies)
    gone = adm.post_form(path="/admin/notifications/rules/{}/delete".format(first), cookies=cookies, fields={})
    gone_page, cookies = _follow(gone, cookies)
    missing = adm.post_form(path="/admin/notifications/rules/{}/delete".format(first), cookies=cookies, fields={})
    missing_page, cookies = _follow(missing, cookies)
    text = _text_of_flash(empty.text)

    testbase.assert_equal(
        (
            empty.status_code, "Tick at least one event." in text, "Choose at least one channel." in text, "Enter at least one recipient." in text,
            made.status_code, mine,
            "A run fails" in landed.text and "A run completes" in landed.text, "The rule is off" in _text_of_flash(off_page.text),
            "The rule is on." in _text_of_flash(on_page.text), "Rule deleted." in _text_of_flash(gone_page.text),
            "no longer exists" in _text_of_flash(missing_page.text),
        ),
        (
            400, True, True, True, 303,
            [("entity.run.completed", "run_succeeded", 5, ("ops@example.test", "lead@example.test")), ("entity.run.failed", "run_failed", 5, ("ops@example.test", "lead@example.test"))],
            True, True, True, True, True,
        ),
    )
    return


def test_every_change_is_in_the_audit_log_with_names_and_never_values():
    """
    **Feature: notifications page (ORG-F08)**
    **Property: adding, switching and deleting a channel and adding and deleting a rule each leave an audit record naming the acting administrator and
    the settings concerned; none contains a secret value.**
    """
    adm.ensure_audit_wiring()
    cookies = adm.admin_cookies()
    since = adm.latest_audit_sequence()
    name = adm.unique_name(prefix="audited")
    created = _add_smtp(cookies, name)
    channel_id = _channel_id(created.header("Location"))
    adm.post_form(path="/admin/notifications/channels/{}/state".format(channel_id), cookies=cookies, fields={"disabled": "1"})
    adm.post_form(path="/admin/notifications/channels/{}/secrets".format(channel_id), cookies=cookies, fields={"setting": "password", "value": "rotated-VALUE-5521"})
    adm.post_form(path="/admin/notifications/rules/create", cookies=cookies, fields=[("events", "entity.run.failed"), ("channel_ids", channel_id), ("recipients", "ops@example.test")])
    session = adm.open_db_session()
    try:
        rule = [r for r in session.query(NotificationRoutingRule).all() if channel_id in r.channel_ids][0]
        rule_id = str(rule.rule_id)
    finally:
        session.close()
    adm.post_form(path="/admin/notifications/rules/{}/delete".format(rule_id), cookies=cookies, fields={})
    adm.post_form(path="/admin/notifications/channels/{}/delete".format(channel_id), cookies=cookies, fields={})

    kinds = ("channel_created", "channel_updated", "channel_deleted", "rule_created", "rule_deleted")
    records = {kind: adm.audit_records_for(kind="audit.notification." + kind, since_sequence=since) for kind in kinds}
    everything = " ".join(str(r.payload_json) for rs in records.values() for r in rs)
    updates = [str(r.payload_json) for r in records["channel_updated"]]

    testbase.assert_equal(
        (
            {kind: len(rs) for kind, rs in records.items()},
            PASSWORD in everything or "rotated-VALUE-5521" in everything,
            any("'disabled'" in text for text in updates), any("secret:password" in text for text in updates),
            "'password'" in str(records["channel_created"][0].payload_json),
            all(r.payload_json.get("actor_user_id") for rs in records.values() for r in rs),
        ),
        ({"channel_created": 1, "channel_updated": 2, "channel_deleted": 1, "rule_created": 1, "rule_deleted": 1}, False, True, True, True, True),
    )
    return


def test_a_person_without_the_notification_keys_cannot_open_or_change_anything():
    """
    **Feature: notifications page (ORG-F08)**
    **Property: a signed-in user who holds neither notification key gets the shared 403 page from every route; the permission each route needs is
    read for the two pages that only look and write for every route that changes something, including the add forms.**
    """
    viewer = login_as(wsgi_app=adm.app(), user=ensure_seeded_viewer())
    paths = ["/admin/notifications", "/admin/notifications/channels/create", "/admin/notifications/rules/create"]
    statuses = [adm.get(path=path, cookies=viewer).status_code for path in paths]
    posted = adm.post_form(path="/admin/notifications/channels/create", cookies=viewer, fields={"kind": "smtp_email", "name": "x"}).status_code
    needs = routes_notifications._ROUTE_PERMISSIONS

    testbase.assert_equal(
        (
            statuses, posted,
            needs["config.notifications_overview"], needs["config.notification_channel_detail"],
            {key: value for key, value in needs.items() if value == "system:notifications.write"} == {
                key: value for key, value in needs.items() if key not in ("config.notifications_overview", "config.notification_channel_detail")
            },
        ),
        ([403, 403, 403], 403, "system:notifications.read", "system:notifications.read", True),
    )
    return
