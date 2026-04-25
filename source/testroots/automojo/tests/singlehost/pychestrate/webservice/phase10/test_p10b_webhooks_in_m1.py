"""
.. module:: test_p10b_webhooks_in_m1
    :synopsis: Tests for P10b — 8-webhooks-in M1.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import hashlib
import hmac
import json

from typing import List

from automojo import testbase

from automojo.pychestrate.webservice.extensions.registry import (
    reset_registry_for_testing,
)
from automojo.pychestrate.webservice.messaging.event_bus import (
    EntityEvent,
    reset_for_testing as reset_event_bus,
    subscribe,
)
from automojo.pychestrate.webservice.webhooks_in import (
    GenericHmacWebhookParser,
    InboundWebhookParserProtocol,
    NormalizedEvent,
    ParsedWebhook,
    ReplayOutcome,
    SignatureAlgorithm,
    SignatureEncoding,
    SignatureHeaderSpec,
    StructuredRejection,
    WebhookConfigurationConflictError,
    WebhookConfigurationInvalidError,
    WebhookConfigurationNotFoundError,
    WebhookInEventTopics,
    WebhookProviderUnknownError,
    create_webhook,
    disable_webhook,
    dispatch_inbound_webhook,
    get_webhook,
    list_webhooks,
    publish_domain_events,
    record_delivery_or_replay,
    register_builtin_extensions as webhooks_in_register,
    verify_signature,
)
from automojo.pychestrate.webservice.extensions.registry import (
    register_factory_implementation,
    unregister_factory_implementation,
)

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
)


PROJECT_UUID = "00000000-0000-4000-8000-000000200001"
ACTOR_UUID = "00000000-0000-4000-8000-000000200002"
SECRET = b"super-shared-inbound-secret"
GENERIC_PROVIDER = "generic"


def _prepare_runtime() -> None:
    reset_registry_for_testing()
    reset_event_bus()
    webhooks_in_register()
    return


def _signed_headers(*, body: bytes, hook_name: str, delivery_id: str) -> dict:
    digest = hmac.new(
        key=SECRET, msg=body, digestmod=hashlib.sha256,
    ).hexdigest()
    rtnval = {
        "X-Pychestrate-Signature": "sha256=" + digest,
        "X-Pychestrate-Hook-Name": hook_name,
        "X-Pychestrate-Delivery-Id": delivery_id,
    }
    return rtnval


# -------------------------------------
# Parser protocol + GenericHmacWebhookParser
# -------------------------------------

def test_generic_parser_declares_provider_and_signature_specs():
    """
    **Feature: 8-webhooks-in (M1)**
    **Property: GenericHmacWebhookParser declares the
    'generic' provider, application/json, and a single
    HMAC-SHA-256 / HEX_WITH_PREFIX signature spec with the
    'sha256=' prefix.**
    """
    _prepare_runtime()
    testbase.assert_equal(
        GenericHmacWebhookParser.provider_name(), GENERIC_PROVIDER,
    )
    testbase.assert_equal(
        GenericHmacWebhookParser.accepted_content_types(),
        ("application/json",),
    )
    specs = GenericHmacWebhookParser.signature_headers()
    testbase.assert_equal(len(specs), 1)
    testbase.assert_equal(specs[0].algorithm, SignatureAlgorithm.HMAC_SHA256)
    testbase.assert_equal(specs[0].encoding, SignatureEncoding.HEX_WITH_PREFIX)
    testbase.assert_equal(specs[0].prefix, "sha256=")
    testbase.assert_equal(specs[0].weak, False)
    testbase.assert_equal(
        GenericHmacWebhookParser.delivery_id_header(),
        "X-Pychestrate-Delivery-Id",
    )
    return


def test_generic_parser_returns_parsed_webhook_for_valid_json():
    """
    **Feature: 8-webhooks-in (M1)**
    **Property: parse() returns a ParsedWebhook carrying a
    single normalized event for valid JSON.**
    """
    _prepare_runtime()
    body = json.dumps({"action": "ping", "value": 42}).encode("utf-8")
    headers = {
        "X-Pychestrate-Hook-Name": "ops",
        "X-Pychestrate-Delivery-Id": "del-1",
    }
    result = GenericHmacWebhookParser.parse(
        raw_bytes=body, headers=headers,
    )
    testbase.assert_equal(isinstance(result, ParsedWebhook), True)
    testbase.assert_equal(result.provider, GENERIC_PROVIDER)
    testbase.assert_equal(result.hook_name, "ops")
    testbase.assert_equal(result.delivery_id, "del-1")
    testbase.assert_equal(len(result.domain_events), 1)
    testbase.assert_equal(
        result.domain_events[0].topic, "entity.webhook.payload",
    )
    return


def test_generic_parser_rejects_non_json_payload():
    """
    **Feature: 8-webhooks-in (M1)**
    **Property: malformed JSON surfaces as a
    StructuredRejection with reason='payload_not_json'.**
    """
    _prepare_runtime()
    body = b"not-json{"
    result = GenericHmacWebhookParser.parse(
        raw_bytes=body, headers={"X-Pychestrate-Hook-Name": "ops"},
    )
    testbase.assert_equal(isinstance(result, StructuredRejection), True)
    testbase.assert_equal(result.reason, "payload_not_json")
    testbase.assert_equal(result.recoverable, True)
    return


# -------------------------------------
# Verification
# -------------------------------------

def test_verify_signature_accepts_canonical_match():
    """
    **Feature: 8-webhooks-in (M1)**
    **Property: verify_signature accepts a canonical
    HMAC-SHA-256 hex-with-prefix match.**
    """
    _prepare_runtime()
    body = b'{"hello":"world"}'
    headers = _signed_headers(
        body=body, hook_name="ops", delivery_id="del-2",
    )
    outcome = verify_signature(
        parser=GenericHmacWebhookParser,
        raw_bytes=body, headers=headers, shared_secret=SECRET,
    )
    testbase.assert_equal(outcome.verified, True)
    testbase.assert_equal(
        outcome.matched_header, "X-Pychestrate-Signature",
    )
    return


def test_verify_signature_rejects_invalid_digest():
    """
    **Feature: 8-webhooks-in (M1)**
    **Property: verify_signature rejects a forged digest with
    reason='signature_invalid'.**
    """
    _prepare_runtime()
    body = b'{"hello":"world"}'
    headers = {"X-Pychestrate-Signature": "sha256=" + "0" * 64}
    outcome = verify_signature(
        parser=GenericHmacWebhookParser,
        raw_bytes=body, headers=headers, shared_secret=SECRET,
    )
    testbase.assert_equal(outcome.verified, False)
    testbase.assert_equal(outcome.reason, "signature_invalid")
    return


def test_verify_signature_reports_missing_when_no_header():
    """
    **Feature: 8-webhooks-in (M1)**
    **Property: an absent signature header surfaces as
    reason='signature_missing'.**
    """
    _prepare_runtime()
    body = b'{}'
    outcome = verify_signature(
        parser=GenericHmacWebhookParser,
        raw_bytes=body, headers={}, shared_secret=SECRET,
    )
    testbase.assert_equal(outcome.verified, False)
    testbase.assert_equal(outcome.reason, "signature_missing")
    return


class _WeakOnlyParser(InboundWebhookParserProtocol):
    factory_protocol_name: str = "inbound_webhook_parser"
    protocol_schema_version: int = 1
    PRECEDENCE: int = 500

    @classmethod
    def provider_name(cls):
        return "weakonly"

    @classmethod
    def accepted_content_types(cls):
        return ("application/json",)

    @classmethod
    def signature_headers(cls):
        return (
            SignatureHeaderSpec(
                header="X-Weak-Signature",
                algorithm=SignatureAlgorithm.HMAC_SHA1,
                encoding=SignatureEncoding.HEX_WITH_PREFIX,
                prefix="sha1=",
                weak=True,
            ),
        )

    @classmethod
    def delivery_id_header(cls):
        return None

    @classmethod
    def parse(cls, *, raw_bytes, headers):
        rtnval = ParsedWebhook(
            provider="weakonly", hook_name="", delivery_id=None,
            domain_events=(
                NormalizedEvent(topic="entity.scm.push", payload={}),
            ),
        )
        return rtnval


def test_verify_signature_rejects_weak_only():
    """
    **Feature: 8-webhooks-in (M1)**
    **Property: a request that offers only a weak signature
    is rejected with reason='signature_weak'.**
    """
    _prepare_runtime()
    body = b'{"a":1}'
    weak_digest = hmac.new(
        key=SECRET, msg=body, digestmod=hashlib.sha1,
    ).hexdigest()
    outcome = verify_signature(
        parser=_WeakOnlyParser,
        raw_bytes=body,
        headers={"X-Weak-Signature": "sha1=" + weak_digest},
        shared_secret=SECRET,
    )
    testbase.assert_equal(outcome.verified, False)
    testbase.assert_equal(outcome.reason, "signature_weak")
    testbase.assert_equal(outcome.weak_only, True)
    return


# -------------------------------------
# Replay cache
# -------------------------------------

def test_replay_cache_records_then_ignores_duplicates():
    """
    **Feature: 8-webhooks-in (M1)**
    **Property: the first sighting records; the second
    surfaces REPLAY_IGNORED.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    first = record_delivery_or_replay(
        db_session=session, provider=GENERIC_PROVIDER,
        hook_name="ops", delivery_id="del-1",
    )
    session.commit()
    second = record_delivery_or_replay(
        db_session=session, provider=GENERIC_PROVIDER,
        hook_name="ops", delivery_id="del-1",
    )
    testbase.assert_equal(first, ReplayOutcome.RECORDED)
    testbase.assert_equal(second, ReplayOutcome.REPLAY_IGNORED)
    return


def test_replay_cache_distinct_keys_record_independently():
    """
    **Feature: 8-webhooks-in (M1)**
    **Property: distinct (provider, hook_name, delivery_id)
    triples each RECORD on first sight.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    a = record_delivery_or_replay(
        db_session=session, provider=GENERIC_PROVIDER,
        hook_name="ops", delivery_id="A",
    )
    b = record_delivery_or_replay(
        db_session=session, provider=GENERIC_PROVIDER,
        hook_name="ops", delivery_id="B",
    )
    c = record_delivery_or_replay(
        db_session=session, provider=GENERIC_PROVIDER,
        hook_name="other", delivery_id="A",
    )
    testbase.assert_equal(a, ReplayOutcome.RECORDED)
    testbase.assert_equal(b, ReplayOutcome.RECORDED)
    testbase.assert_equal(c, ReplayOutcome.RECORDED)
    return


# -------------------------------------
# Configuration service
# -------------------------------------

def test_create_webhook_persists_and_emits():
    """
    **Feature: 8-webhooks-in (M1)**
    **Property: create_webhook persists, returns a populated
    view, and emits CONFIGURED.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=WebhookInEventTopics.CONFIGURED,
        subscriber=lambda e: received.append(e),
    )
    view = create_webhook(
        db_session=session, project_id=PROJECT_UUID,
        provider=GENERIC_PROVIDER, hook_name="ops",
        secret_ref="webhooks.in.generic.ops.secret",
        actor_id=ACTOR_UUID,
    )
    testbase.assert_equal(view.provider, GENERIC_PROVIDER)
    testbase.assert_equal(view.hook_name, "ops")
    testbase.assert_equal(view.enabled, True)
    testbase.assert_equal(len(received), 1)
    return


def test_create_webhook_unknown_provider_raises():
    """
    **Feature: 8-webhooks-in (M1)**
    **Property: creating against a provider with no
    registered parser raises WebhookProviderUnknownError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    raised = False
    try:
        create_webhook(
            db_session=session, project_id=PROJECT_UUID,
            provider="not-a-provider", hook_name="ops",
            secret_ref="x",
        )
    except WebhookProviderUnknownError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_create_webhook_duplicate_raises():
    """
    **Feature: 8-webhooks-in (M1)**
    **Property: a duplicate (project, provider, hook_name)
    raises WebhookConfigurationConflictError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    create_webhook(
        db_session=session, project_id=PROJECT_UUID,
        provider=GENERIC_PROVIDER, hook_name="dup",
        secret_ref="x",
    )
    raised = False
    try:
        create_webhook(
            db_session=session, project_id=PROJECT_UUID,
            provider=GENERIC_PROVIDER, hook_name="dup",
            secret_ref="x",
        )
    except WebhookConfigurationConflictError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_create_webhook_empty_fields_raise():
    """
    **Feature: 8-webhooks-in (M1)**
    **Property: empty hook_name / provider / secret_ref each
    raise WebhookConfigurationInvalidError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    raised_count = 0
    for kwargs in (
        {"provider": GENERIC_PROVIDER, "hook_name": "", "secret_ref": "x"},
        {"provider": "", "hook_name": "ops", "secret_ref": "x"},
        {"provider": GENERIC_PROVIDER, "hook_name": "ops", "secret_ref": ""},
    ):
        try:
            create_webhook(
                db_session=session, project_id=PROJECT_UUID,
                **kwargs,
            )
        except WebhookConfigurationInvalidError:
            raised_count = raised_count + 1
    testbase.assert_equal(raised_count, 3)
    return


def test_disable_webhook_idempotent_and_emits():
    """
    **Feature: 8-webhooks-in (M1)**
    **Property: disable_webhook flips enabled=False, stamps
    disabled_at, emits once, and is idempotent.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=WebhookInEventTopics.CONFIGURATION_DISABLED,
        subscriber=lambda e: received.append(e),
    )
    cfg = create_webhook(
        db_session=session, project_id=PROJECT_UUID,
        provider=GENERIC_PROVIDER, hook_name="ops",
        secret_ref="x",
    )
    disabled = disable_webhook(
        db_session=session, webhook_id=cfg.webhook_id,
    )
    testbase.assert_equal(disabled.enabled, False)
    testbase.assert_equal(disabled.disabled_at is not None, True)
    # Idempotent — second call should not emit again.
    disable_webhook(
        db_session=session, webhook_id=cfg.webhook_id,
    )
    testbase.assert_equal(len(received), 1)
    return


def test_get_webhook_unknown_raises():
    """
    **Feature: 8-webhooks-in (M1)**
    **Property: get_webhook on a missing id raises
    WebhookConfigurationNotFoundError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    raised = False
    try:
        get_webhook(
            db_session=session,
            webhook_id="00000000-0000-4000-8000-000000abcdef",
        )
    except WebhookConfigurationNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_list_webhooks_filters_enabled_only():
    """
    **Feature: 8-webhooks-in (M1)**
    **Property: list_webhooks(enabled_only=True) drops the
    disabled rows.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    a = create_webhook(
        db_session=session, project_id=PROJECT_UUID,
        provider=GENERIC_PROVIDER, hook_name="alpha",
        secret_ref="x",
    )
    create_webhook(
        db_session=session, project_id=PROJECT_UUID,
        provider=GENERIC_PROVIDER, hook_name="beta",
        secret_ref="y",
    )
    disable_webhook(db_session=session, webhook_id=a.webhook_id)

    full = list_webhooks(db_session=session, project_id=PROJECT_UUID)
    enabled = list_webhooks(
        db_session=session, project_id=PROJECT_UUID, enabled_only=True,
    )
    testbase.assert_equal(len(full), 2)
    testbase.assert_equal(len(enabled), 1)
    testbase.assert_equal(enabled[0].hook_name, "beta")
    return


# -------------------------------------
# Dispatcher
# -------------------------------------

def test_dispatch_inbound_webhook_publishes_normalized_events():
    """
    **Feature: 8-webhooks-in (M1)**
    **Property: a verified, parseable request publishes the
    normalized event(s), emits DISPATCHED, and reports
    status='dispatched'.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    create_webhook(
        db_session=session, project_id=PROJECT_UUID,
        provider=GENERIC_PROVIDER, hook_name="ops",
        secret_ref="webhooks.in.generic.ops.secret",
    )
    received_dispatch: List[EntityEvent] = []
    received_payload: List[EntityEvent] = []
    subscribe(
        topic=WebhookInEventTopics.DISPATCHED,
        subscriber=lambda e: received_dispatch.append(e),
    )
    subscribe(
        topic="entity.webhook.payload",
        subscriber=lambda e: received_payload.append(e),
    )
    body = json.dumps({"hello": "world"}).encode("utf-8")
    headers = _signed_headers(
        body=body, hook_name="ops", delivery_id="del-100",
    )
    result = dispatch_inbound_webhook(
        db_session=session, provider=GENERIC_PROVIDER,
        hook_name="ops", raw_bytes=body, headers=headers,
        shared_secret=SECRET,
    )
    testbase.assert_equal(result.status, "dispatched")
    testbase.assert_equal(result.domain_event_count, 1)
    testbase.assert_equal(len(received_dispatch), 1)
    testbase.assert_equal(len(received_payload), 1)
    testbase.assert_equal(
        received_payload[0].payload["webhook_provider"], GENERIC_PROVIDER,
    )
    return


def test_dispatch_inbound_webhook_rejects_invalid_signature():
    """
    **Feature: 8-webhooks-in (M1)**
    **Property: a forged signature surfaces a 'rejected' result
    with reason='signature_invalid' and emits FAILED.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    create_webhook(
        db_session=session, project_id=PROJECT_UUID,
        provider=GENERIC_PROVIDER, hook_name="ops",
        secret_ref="x",
    )
    received_failed: List[EntityEvent] = []
    subscribe(
        topic=WebhookInEventTopics.FAILED,
        subscriber=lambda e: received_failed.append(e),
    )
    body = b'{"a":1}'
    bad_headers = {
        "X-Pychestrate-Signature": "sha256=" + "0" * 64,
        "X-Pychestrate-Hook-Name": "ops",
        "X-Pychestrate-Delivery-Id": "del-x",
    }
    result = dispatch_inbound_webhook(
        db_session=session, provider=GENERIC_PROVIDER,
        hook_name="ops", raw_bytes=body, headers=bad_headers,
        shared_secret=SECRET,
    )
    testbase.assert_equal(result.status, "rejected")
    testbase.assert_equal(result.rejection.reason, "signature_invalid")
    testbase.assert_equal(len(received_failed), 1)
    return


def test_dispatch_inbound_webhook_short_circuits_on_replay():
    """
    **Feature: 8-webhooks-in (M1)**
    **Property: a duplicate delivery returns
    status='replay_ignored' with no domain events on the
    second hit and emits REPLAY_IGNORED.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    create_webhook(
        db_session=session, project_id=PROJECT_UUID,
        provider=GENERIC_PROVIDER, hook_name="ops",
        secret_ref="x",
    )
    received_replay: List[EntityEvent] = []
    received_payload: List[EntityEvent] = []
    subscribe(
        topic=WebhookInEventTopics.REPLAY_IGNORED,
        subscriber=lambda e: received_replay.append(e),
    )
    subscribe(
        topic="entity.webhook.payload",
        subscriber=lambda e: received_payload.append(e),
    )
    body = json.dumps({"hello": "world"}).encode("utf-8")
    headers = _signed_headers(
        body=body, hook_name="ops", delivery_id="del-replay",
    )
    first = dispatch_inbound_webhook(
        db_session=session, provider=GENERIC_PROVIDER,
        hook_name="ops", raw_bytes=body, headers=headers,
        shared_secret=SECRET,
    )
    second = dispatch_inbound_webhook(
        db_session=session, provider=GENERIC_PROVIDER,
        hook_name="ops", raw_bytes=body, headers=headers,
        shared_secret=SECRET,
    )
    testbase.assert_equal(first.status, "dispatched")
    testbase.assert_equal(second.status, "replay_ignored")
    testbase.assert_equal(len(received_replay), 1)
    testbase.assert_equal(len(received_payload), 1)
    return


def test_dispatch_inbound_webhook_unknown_provider_returns_404():
    """
    **Feature: 8-webhooks-in (M1)**
    **Property: a request against an unregistered provider
    surfaces status='rejected' with reason='provider_unknown'
    and status_code=404.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    body = b'{"a":1}'
    result = dispatch_inbound_webhook(
        db_session=session, provider="not-a-provider",
        hook_name="ops", raw_bytes=body, headers={},
        shared_secret=SECRET,
    )
    testbase.assert_equal(result.status, "rejected")
    testbase.assert_equal(result.rejection.reason, "provider_unknown")
    testbase.assert_equal(result.rejection.status_code, 404)
    return


def test_dispatch_inbound_webhook_missing_configuration_rejects():
    """
    **Feature: 8-webhooks-in (M1)**
    **Property: a request without an enabled configuration
    surfaces reason='configuration_not_found'.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    body = json.dumps({"a": 1}).encode("utf-8")
    headers = _signed_headers(body=body, hook_name="ops", delivery_id="d1")
    result = dispatch_inbound_webhook(
        db_session=session, provider=GENERIC_PROVIDER,
        hook_name="ops", raw_bytes=body, headers=headers,
        shared_secret=SECRET,
    )
    testbase.assert_equal(result.status, "rejected")
    testbase.assert_equal(
        result.rejection.reason, "configuration_not_found",
    )
    return


def test_dispatch_inbound_webhook_disabled_configuration_rejects():
    """
    **Feature: 8-webhooks-in (M1)**
    **Property: disabling a configuration causes subsequent
    deliveries to surface reason='configuration_not_found'.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    cfg = create_webhook(
        db_session=session, project_id=PROJECT_UUID,
        provider=GENERIC_PROVIDER, hook_name="ops",
        secret_ref="x",
    )
    disable_webhook(db_session=session, webhook_id=cfg.webhook_id)
    body = json.dumps({"a": 1}).encode("utf-8")
    headers = _signed_headers(
        body=body, hook_name="ops", delivery_id="del-disabled",
    )
    result = dispatch_inbound_webhook(
        db_session=session, provider=GENERIC_PROVIDER,
        hook_name="ops", raw_bytes=body, headers=headers,
        shared_secret=SECRET,
    )
    testbase.assert_equal(result.status, "rejected")
    testbase.assert_equal(
        result.rejection.reason, "configuration_not_found",
    )
    return


def test_dispatch_inbound_webhook_mtls_required_without_subject_rejects():
    """
    **Feature: 8-webhooks-in (M1)**
    **Property: a configuration with mtls_required=True
    rejects requests that arrive without a peer subject.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    create_webhook(
        db_session=session, project_id=PROJECT_UUID,
        provider=GENERIC_PROVIDER, hook_name="ops",
        secret_ref="x", mtls_required=True,
    )
    body = json.dumps({"a": 1}).encode("utf-8")
    headers = _signed_headers(
        body=body, hook_name="ops", delivery_id="del-mtls",
    )
    result = dispatch_inbound_webhook(
        db_session=session, provider=GENERIC_PROVIDER,
        hook_name="ops", raw_bytes=body, headers=headers,
        shared_secret=SECRET, mtls_subject=None,
    )
    testbase.assert_equal(result.status, "rejected")
    testbase.assert_equal(result.rejection.reason, "mtls_required")
    return


# -------------------------------------
# Catch-and-reclassify boundary
# -------------------------------------

class _CrashingParser(InboundWebhookParserProtocol):
    factory_protocol_name: str = "inbound_webhook_parser"
    protocol_schema_version: int = 1
    PRECEDENCE: int = 100

    @classmethod
    def provider_name(cls):
        return "crashy"

    @classmethod
    def accepted_content_types(cls):
        return ("application/json",)

    @classmethod
    def signature_headers(cls):
        return (
            SignatureHeaderSpec(
                header="X-Pychestrate-Signature",
                algorithm=SignatureAlgorithm.HMAC_SHA256,
                encoding=SignatureEncoding.HEX_WITH_PREFIX,
                prefix="sha256=",
                weak=False,
            ),
        )

    @classmethod
    def delivery_id_header(cls):
        return "X-Pychestrate-Delivery-Id"

    @classmethod
    def parse(cls, *, raw_bytes, headers):
        raise KeyError("action")


def test_dispatcher_catches_parser_crash_and_reclassifies():
    """
    **Feature: 8-webhooks-in (M1)**
    **Property: an uncaught exception inside parse() is
    reclassified as a StructuredRejection with
    reason='parser_crashed' and recoverable=True.**
    """
    _prepare_runtime()
    register_factory_implementation(implementation=_CrashingParser)
    try:
        _engine, session = build_in_memory_session()
        create_webhook(
            db_session=session, project_id=PROJECT_UUID,
            provider="crashy", hook_name="ops",
            secret_ref="x",
        )
        body = json.dumps({"a": 1}).encode("utf-8")
        headers = _signed_headers(
            body=body, hook_name="ops", delivery_id="del-crash",
        )
        result = dispatch_inbound_webhook(
            db_session=session, provider="crashy",
            hook_name="ops", raw_bytes=body, headers=headers,
            shared_secret=SECRET,
        )
        testbase.assert_equal(result.status, "rejected")
        testbase.assert_equal(result.rejection.reason, "parser_crashed")
        testbase.assert_equal(result.rejection.recoverable, True)
    finally:
        unregister_factory_implementation(implementation=_CrashingParser)
    return


# -------------------------------------
# Normalization
# -------------------------------------

def test_publish_domain_events_decorates_with_correlation_keys():
    """
    **Feature: 8-webhooks-in (M1)**
    **Property: publish_domain_events stamps webhook_provider
    / webhook_hook_name / webhook_id / webhook_request_id on
    every event payload before it goes onto the bus.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic="entity.scm.push",
        subscriber=lambda e: received.append(e),
    )
    parsed = ParsedWebhook(
        provider="generic", hook_name="ops",
        delivery_id="del-norm",
        domain_events=(
            NormalizedEvent(
                topic="entity.scm.push",
                payload={"branch": "main"},
            ),
        ),
    )
    count = publish_domain_events(
        db_session=session, parsed=parsed,
        webhook_id="00000000-0000-4000-8000-00000000aaaa",
        request_id="req-1",
    )
    session.commit()
    testbase.assert_equal(count, 1)
    testbase.assert_equal(len(received), 1)
    payload = received[0].payload
    testbase.assert_equal(payload["webhook_provider"], "generic")
    testbase.assert_equal(payload["webhook_hook_name"], "ops")
    testbase.assert_equal(payload["webhook_request_id"], "req-1")
    testbase.assert_equal(payload["branch"], "main")
    return


# -------------------------------------
# Bootstrap registration
# -------------------------------------

def test_register_builtin_extensions_registers_generic_parser():
    """
    **Feature: 8-webhooks-in (M1)**
    **Property: register_builtin_extensions seeds the
    GenericHmacWebhookParser under inbound_webhook_parser.**
    """
    reset_registry_for_testing()
    reset_event_bus()
    webhooks_in_register()
    from automojo.pychestrate.webservice.extensions.registry import (
        list_factory_implementations,
    )
    impls = list_factory_implementations(
        factory_protocol_name="inbound_webhook_parser",
    )
    names = [impl.provider_name() for impl in impls]
    testbase.assert_equal("generic" in names, True)
    return
