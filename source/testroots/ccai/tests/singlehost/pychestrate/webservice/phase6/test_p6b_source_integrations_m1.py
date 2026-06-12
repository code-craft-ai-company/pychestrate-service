"""
.. module:: test_p6b_source_integrations_m1
    :synopsis: Tests for P6b — 6-source-integrations M1.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import hashlib
import hmac
import json

from typing import List

from ccai import testbase

from ccai.pychestrate.core.defaults import new_uuid

from ccai.pychestrate.webservice.extensions.registry import (
    reset_registry_for_testing,
)
from ccai.pychestrate.webservice.messaging.event_bus import (
    EntityEvent,
    reset_for_testing as reset_event_bus,
    subscribe,
)
from ccai.pychestrate.webservice.orchestration.source import (
    GithubScmProvider,
    ScmConfigNotFoundError,
    ScmEventKind,
    ScmPayloadInvalidError,
    ScmProviderNotFoundError,
    ScmSignatureInvalidError,
    SourceEventTopics,
    SourceIntegrationsAspects,
    WebhookAckState,
    get_last_seen_head,
    get_project_config,
    handle_webhook,
    list_recent_deliveries,
    record_last_seen_head,
    register_builtin_extensions as source_register,
    set_project_config,
)

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
)


PROJECT_UUID = "00000000-0000-4000-8000-000000020001"
SECRET = b"super-shared-secret"
DELIVERY_ID = "delivery-abc-123"


def _prepare_runtime() -> None:
    reset_registry_for_testing()
    reset_event_bus()
    source_register()
    return


def _sign_body(*, body: bytes, secret: bytes = SECRET) -> str:
    digest = hmac.new(
        key=secret, msg=body, digestmod=hashlib.sha256,
    ).hexdigest()
    rtnval = "sha256=" + digest
    return rtnval


def _build_push_body(*, repo_key: str, ref: str, commit_sha: str) -> bytes:
    payload = {
        "repository": {"full_name": repo_key},
        "ref": ref,
        "after": commit_sha,
        "pusher": {"name": "alice"},
    }
    rtnval = json.dumps(payload).encode("utf-8")
    return rtnval


def _build_push_headers(*, delivery_id: str, signature: str) -> dict:
    rtnval = {
        "X-GitHub-Delivery": delivery_id,
        "X-GitHub-Event": "push",
        "X-Hub-Signature-256": signature,
    }
    return rtnval


# -------------------------------------
# Provider primitives
# -------------------------------------

def test_github_provider_verifies_valid_signature():
    """
    **Feature: 6-source-integrations (M1)**
    **Property: GithubScmProvider.verify_signature accepts a
    correctly computed HMAC-SHA-256 signature and rejects a
    tampered body.**
    """
    _prepare_runtime()
    body = b'{"hello":"world"}'
    signature = _sign_body(body=body)
    headers = GithubScmProvider.normalize_headers(raw_headers={
        "X-GitHub-Delivery": "abc",
        "X-GitHub-Event": "push",
        "X-Hub-Signature-256": signature,
    })
    testbase.assert_equal(
        GithubScmProvider.verify_signature(
            secret=SECRET, raw_body=body, headers=headers,
        ),
        True,
    )
    testbase.assert_equal(
        GithubScmProvider.verify_signature(
            secret=SECRET, raw_body=b'{"tampered":true}', headers=headers,
        ),
        False,
    )
    return


def test_github_provider_parses_push_payload():
    """
    **Feature: 6-source-integrations (M1)**
    **Property: GithubScmProvider.parse_event extracts repo +
    ref + commit_sha + pusher from a push payload.**
    """
    _prepare_runtime()
    payload = {
        "repository": {"full_name": "acme/widgets"},
        "ref": "refs/heads/main",
        "after": "deadbeef",
        "pusher": {"name": "bob"},
        "forced": True,
    }
    headers = GithubScmProvider.normalize_headers(raw_headers={
        "X-GitHub-Event": "push",
    })
    parsed = GithubScmProvider.parse_event(
        headers=headers, payload=payload,
    )
    testbase.assert_equal(parsed.event_kind, ScmEventKind.PUSH)
    testbase.assert_equal(parsed.push.repo_key, "acme/widgets")
    testbase.assert_equal(parsed.push.ref, "refs/heads/main")
    testbase.assert_equal(parsed.push.commit_sha, "deadbeef")
    testbase.assert_equal(parsed.push.pusher_actor, "bob")
    testbase.assert_equal(parsed.push.is_force_push, True)
    return


def test_github_provider_parses_pull_request_payload():
    """
    **Feature: 6-source-integrations (M1)**
    **Property: GithubScmProvider.parse_event extracts the PR
    head ref + sha + base ref + action.**
    """
    _prepare_runtime()
    payload = {
        "action": "opened",
        "number": 42,
        "repository": {"full_name": "acme/widgets"},
        "pull_request": {
            "head": {"ref": "feature/x", "sha": "feedface"},
            "base": {"ref": "main"},
            "title": "add feature x",
        },
    }
    headers = GithubScmProvider.normalize_headers(raw_headers={
        "X-GitHub-Event": "pull_request",
    })
    parsed = GithubScmProvider.parse_event(
        headers=headers, payload=payload,
    )
    testbase.assert_equal(parsed.event_kind, ScmEventKind.PULL_REQUEST)
    testbase.assert_equal(parsed.pull_request.pr_number, 42)
    testbase.assert_equal(parsed.pull_request.head_ref, "feature/x")
    testbase.assert_equal(parsed.pull_request.head_commit_sha, "feedface")
    testbase.assert_equal(parsed.pull_request.action, "opened")
    return


# -------------------------------------
# set_project_config
# -------------------------------------

def test_set_project_config_persists_and_emits():
    """
    **Feature: 6-source-integrations (M1)**
    **Property: set_project_config persists the row and emits
    entity.source.project_config_set.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=SourceEventTopics.PROJECT_CONFIG_SET,
        subscriber=lambda e: received.append(e),
    )
    view = set_project_config(
        db_session=session,
        project_id=PROJECT_UUID,
        provider_name="github",
        repo_key="acme/widgets",
        pipeline_file_path=".pychestrate/pipeline.yaml",
    )
    testbase.assert_equal(view.provider_name, "github")
    testbase.assert_equal(view.repo_key, "acme/widgets")
    testbase.assert_equal(len(received), 1)
    return


def test_set_project_config_unknown_provider_raises():
    """
    **Feature: 6-source-integrations (M1)**
    **Property: set_project_config rejects an unregistered
    provider with ScmProviderNotFoundError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    raised = False
    try:
        set_project_config(
            db_session=session,
            project_id=PROJECT_UUID,
            provider_name="unknown-vcs",
            repo_key="acme/widgets",
        )
    except ScmProviderNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_get_project_config_unknown_raises():
    """
    **Feature: 6-source-integrations (M1)**
    **Property: get_project_config on an unconfigured project
    raises ScmConfigNotFoundError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    raised = False
    try:
        get_project_config(db_session=session, project_id=PROJECT_UUID)
    except ScmConfigNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return


# -------------------------------------
# handle_webhook
# -------------------------------------

def test_handle_webhook_accepts_valid_push_and_emits():
    """
    **Feature: 6-source-integrations (M1)**
    **Property: handle_webhook verifies the signature, persists
    the delivery, parses the push, and emits
    entity.source.webhook.received.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received_received: List[EntityEvent] = []
    subscribe(
        topic=SourceEventTopics.WEBHOOK_RECEIVED,
        subscriber=lambda e: received_received.append(e),
    )
    set_project_config(
        db_session=session,
        project_id=PROJECT_UUID,
        provider_name="github",
        repo_key="acme/widgets",
    )
    body = _build_push_body(
        repo_key="acme/widgets", ref="refs/heads/main",
        commit_sha="cafebabe",
    )
    signature = _sign_body(body=body)
    result = handle_webhook(
        db_session=session,
        project_id=PROJECT_UUID,
        raw_headers=_build_push_headers(
            delivery_id=DELIVERY_ID, signature=signature,
        ),
        raw_body=body,
        aspects=SourceIntegrationsAspects(secret=SECRET),
    )
    testbase.assert_equal(result.state, WebhookAckState.ACCEPTED)
    testbase.assert_equal(result.event_kind, ScmEventKind.PUSH)
    testbase.assert_equal(result.delivery_id, DELIVERY_ID)
    testbase.assert_equal(result.parsed.push.commit_sha, "cafebabe")
    testbase.assert_equal(len(received_received), 1)
    return


def test_handle_webhook_dedups_repeat_delivery():
    """
    **Feature: 6-source-integrations (M1)**
    **Property: handle_webhook returns DEDUPED + emits
    entity.source.webhook.deduped on a second arrival of the
    same delivery id; the original delivery row is the only
    one persisted.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received_received: List[EntityEvent] = []
    received_deduped: List[EntityEvent] = []
    subscribe(
        topic=SourceEventTopics.WEBHOOK_RECEIVED,
        subscriber=lambda e: received_received.append(e),
    )
    subscribe(
        topic=SourceEventTopics.WEBHOOK_DEDUPED,
        subscriber=lambda e: received_deduped.append(e),
    )
    set_project_config(
        db_session=session,
        project_id=PROJECT_UUID,
        provider_name="github",
        repo_key="acme/widgets",
    )
    body = _build_push_body(
        repo_key="acme/widgets", ref="refs/heads/main",
        commit_sha="aaaa1111",
    )
    signature = _sign_body(body=body)
    headers = _build_push_headers(
        delivery_id=DELIVERY_ID, signature=signature,
    )
    handle_webhook(
        db_session=session, project_id=PROJECT_UUID,
        raw_headers=headers, raw_body=body,
        aspects=SourceIntegrationsAspects(secret=SECRET),
    )
    second = handle_webhook(
        db_session=session, project_id=PROJECT_UUID,
        raw_headers=headers, raw_body=body,
        aspects=SourceIntegrationsAspects(secret=SECRET),
    )
    testbase.assert_equal(second.state, WebhookAckState.DEDUPED)
    testbase.assert_equal(len(received_received), 1)
    testbase.assert_equal(len(received_deduped), 1)

    deliveries = list_recent_deliveries(
        db_session=session, project_id=PROJECT_UUID,
    )
    testbase.assert_equal(len(deliveries), 1)
    return


def test_handle_webhook_rejects_invalid_signature():
    """
    **Feature: 6-source-integrations (M1)**
    **Property: handle_webhook with a tampered body raises
    ScmSignatureInvalidError after emitting the rejected topic.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received_rejected: List[EntityEvent] = []
    subscribe(
        topic=SourceEventTopics.WEBHOOK_REJECTED,
        subscriber=lambda e: received_rejected.append(e),
    )
    set_project_config(
        db_session=session,
        project_id=PROJECT_UUID,
        provider_name="github",
        repo_key="acme/widgets",
    )
    body = _build_push_body(
        repo_key="acme/widgets", ref="refs/heads/main",
        commit_sha="bbbb2222",
    )
    bad_signature = _sign_body(body=b'{"tampered":true}')
    raised = False
    try:
        handle_webhook(
            db_session=session, project_id=PROJECT_UUID,
            raw_headers=_build_push_headers(
                delivery_id=DELIVERY_ID, signature=bad_signature,
            ),
            raw_body=body,
            aspects=SourceIntegrationsAspects(secret=SECRET),
        )
    except ScmSignatureInvalidError:
        raised = True
    testbase.assert_equal(raised, True)
    testbase.assert_equal(len(received_rejected), 1)
    return


def test_handle_webhook_unconfigured_project_raises():
    """
    **Feature: 6-source-integrations (M1)**
    **Property: handle_webhook against an unconfigured project
    raises ScmConfigNotFoundError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    body = b"{}"
    raised = False
    try:
        handle_webhook(
            db_session=session, project_id=PROJECT_UUID,
            raw_headers={"X-GitHub-Delivery": "x"},
            raw_body=body,
            aspects=SourceIntegrationsAspects(secret=SECRET),
        )
    except ScmConfigNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_handle_webhook_oversized_body_raises():
    """
    **Feature: 6-source-integrations (M1)**
    **Property: handle_webhook with a > 1 MiB body raises
    ScmPayloadInvalidError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    set_project_config(
        db_session=session,
        project_id=PROJECT_UUID,
        provider_name="github",
        repo_key="acme/widgets",
    )
    big_body = b"x" * (1 * 1024 * 1024 + 1)
    raised = False
    try:
        handle_webhook(
            db_session=session, project_id=PROJECT_UUID,
            raw_headers=_build_push_headers(
                delivery_id=DELIVERY_ID,
                signature=_sign_body(body=big_body),
            ),
            raw_body=big_body,
            aspects=SourceIntegrationsAspects(secret=SECRET),
        )
    except ScmPayloadInvalidError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_handle_webhook_rejects_missing_delivery_id():
    """
    **Feature: 6-source-integrations (M1)**
    **Property: handle_webhook without a delivery-id header
    raises ScmPayloadInvalidError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    set_project_config(
        db_session=session,
        project_id=PROJECT_UUID,
        provider_name="github",
        repo_key="acme/widgets",
    )
    body = _build_push_body(
        repo_key="acme/widgets", ref="refs/heads/main",
        commit_sha="cccc3333",
    )
    raised = False
    try:
        handle_webhook(
            db_session=session, project_id=PROJECT_UUID,
            raw_headers={
                "X-GitHub-Event": "push",
                "X-Hub-Signature-256": _sign_body(body=body),
            },
            raw_body=body,
            aspects=SourceIntegrationsAspects(secret=SECRET),
        )
    except ScmPayloadInvalidError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_handle_webhook_invokes_pipeline_document_fetcher_on_push():
    """
    **Feature: 6-source-integrations (M1)**
    **Property: when an aspects fetcher is supplied, a valid
    push event invokes it with (repo_key, ref, commit_sha) and
    forwards the returned bytes on the result; the
    pipeline-triggered topic + last-seen-head update fire.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received_triggered: List[EntityEvent] = []
    received_last_seen: List[EntityEvent] = []
    subscribe(
        topic=SourceEventTopics.PIPELINE_TRIGGERED,
        subscriber=lambda e: received_triggered.append(e),
    )
    subscribe(
        topic=SourceEventTopics.LAST_SEEN_HEAD_UPDATED,
        subscriber=lambda e: received_last_seen.append(e),
    )
    set_project_config(
        db_session=session,
        project_id=PROJECT_UUID,
        provider_name="github",
        repo_key="acme/widgets",
    )
    body = _build_push_body(
        repo_key="acme/widgets", ref="refs/heads/main",
        commit_sha="dddd4444",
    )
    fetcher_calls: List[tuple] = []

    def fake_fetcher(repo_key: str, ref: str, commit_sha: str) -> bytes:
        fetcher_calls.append((repo_key, ref, commit_sha))
        return b"schema_version: 1\nname: ci\nstages: []\n"

    result = handle_webhook(
        db_session=session, project_id=PROJECT_UUID,
        raw_headers=_build_push_headers(
            delivery_id=DELIVERY_ID, signature=_sign_body(body=body),
        ),
        raw_body=body,
        aspects=SourceIntegrationsAspects(
            secret=SECRET,
            pipeline_document_fetcher=fake_fetcher,
        ),
    )
    testbase.assert_equal(result.state, WebhookAckState.ACCEPTED)
    testbase.assert_equal(len(fetcher_calls), 1)
    testbase.assert_equal(
        fetcher_calls[0],
        ("acme/widgets", "refs/heads/main", "dddd4444"),
    )
    testbase.assert_equal(
        result.pipeline_document_bytes is not None, True,
    )
    testbase.assert_equal(len(received_triggered), 1)
    # last-seen-head was upserted as part of the push handling.
    head = get_last_seen_head(
        db_session=session, project_id=PROJECT_UUID,
        ref="refs/heads/main",
    )
    testbase.assert_equal(head is not None, True)
    testbase.assert_equal(head.commit_sha, "dddd4444")
    return


# -------------------------------------
# last_seen_head helpers
# -------------------------------------

def test_record_last_seen_head_upserts():
    """
    **Feature: 6-source-integrations (M1)**
    **Property: record_last_seen_head inserts the row on first
    call, updates on second.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    first = record_last_seen_head(
        db_session=session, project_id=PROJECT_UUID,
        ref="refs/heads/main", commit_sha="aaaa",
    )
    second = record_last_seen_head(
        db_session=session, project_id=PROJECT_UUID,
        ref="refs/heads/main", commit_sha="bbbb",
    )
    testbase.assert_equal(first.commit_sha, "aaaa")
    testbase.assert_equal(second.commit_sha, "bbbb")
    head = get_last_seen_head(
        db_session=session, project_id=PROJECT_UUID,
        ref="refs/heads/main",
    )
    testbase.assert_equal(head.commit_sha, "bbbb")
    return


def test_get_last_seen_head_unknown_returns_none():
    """
    **Feature: 6-source-integrations (M1)**
    **Property: get_last_seen_head returns None on miss (no
    exception — this is a polling helper).**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    head = get_last_seen_head(
        db_session=session, project_id=PROJECT_UUID,
        ref="refs/heads/missing",
    )
    testbase.assert_equal(head is None, True)
    return
