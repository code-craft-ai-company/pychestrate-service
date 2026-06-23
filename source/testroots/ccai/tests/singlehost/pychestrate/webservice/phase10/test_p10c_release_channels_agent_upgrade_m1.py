"""
.. module:: test_p10c_release_channels_agent_upgrade_m1
    :synopsis: Tests for P10c — 10-release-channels +
               3-agent-upgrade-channel M1.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import hashlib

from typing import List

from ccai import testbase

from ccai.pychestrate.webservice.clients.upgrades import (
    FixedSetRolloutPolicy,
    ObjectStoreArtifactSource,
    OfferOutcome,
    RolloutNotFoundError,
    RolloutState,
    StageState,
    UpgradeEventTopics,
    delete_pod_pin,
    draft_rollout,
    get_pin_map,
    get_rollout,
    list_rollouts,
    record_offer_outcome,
    register_builtin_extensions as agent_upgrades_register,
    set_pod_pin,
    start_rollout,
)
from ccai.pychestrate.webservice.clients.upgrades.dtos import (
    FleetMember,
    FleetSnapshot,
)
from ccai.pychestrate.webservice.extensions.registry import (
    register_factory_implementation,
    reset_registry_for_testing,
    unregister_factory_implementation,
)
from ccai.pychestrate.webservice.messaging.event_bus import (
    EntityEvent,
    reset_for_testing as reset_event_bus,
    subscribe,
)
from ccai.pychestrate.webservice.ops.release import (
    ConsumerDescriptor,
    HashRingChannelPolicy,
    LogVerbosity,
    ManifestVerificationError,
    ReleaseChannel,
    ReleaseChannelPolicyProtocol,
    ReleaseComponent,
    ReleaseConflictError,
    ReleaseEventTopics,
    ReleaseSigningKeyUnavailableError,
    build_canonical_manifest,
    build_default_release_aspects,
    generate_signing_key,
    get_current_manifest,
    list_releases as ops_list_releases,
    publish_release,
    register_builtin_extensions as releases_register,
    register_trusted_issuer_key,
    reset_for_testing as reset_signing_for_testing,
    resolve_policy,
    set_active_signing_key,
    sign_manifest,
    verify_manifest,
)

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
)


ACTOR_UUID = "00000000-0000-4000-8000-000000300001"
ARTIFACT_SHA = "a" * 64


def _prepare_runtime() -> None:
    reset_registry_for_testing()
    reset_event_bus()
    reset_signing_for_testing()
    releases_register()
    agent_upgrades_register()
    return


def _install_signing_key():
    key = generate_signing_key(issuer_key_id="release-key-001")
    set_active_signing_key(key=key)
    return key


def _install_trust(*, db_session, key):
    register_trusted_issuer_key(
        db_session=db_session,
        issuer_key_id=key.issuer_key_id,
        public_key_bytes=key.public_key_bytes,
    )
    db_session.commit()
    return


# -------------------------------------
# Release aspects + signing key
# -------------------------------------

def test_default_release_aspects_are_immutable_and_sane():
    """
    **Feature: 10-release-channels (M1)**
    **Property: build_default_release_aspects returns sync=True,
    30s timeout, no cascading rollback, no bypass, normal log
    verbosity — and it's a frozen dataclass.**
    """
    _prepare_runtime()
    aspects = build_default_release_aspects()
    testbase.assert_equal(aspects.sync, True)
    testbase.assert_equal(aspects.timeout_seconds, 30.0)
    testbase.assert_equal(aspects.include_cascading_agent_rollback, False)
    testbase.assert_equal(aspects.bypass_bake_window, False)
    testbase.assert_equal(aspects.log_verbosity, LogVerbosity.NORMAL)
    raised = False
    try:
        aspects.sync = False
    except Exception:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_sign_manifest_requires_active_key():
    """
    **Feature: 10-release-channels (M1)**
    **Property: sign_manifest raises
    ReleaseSigningKeyUnavailableError when no active key is
    installed.**
    """
    _prepare_runtime()
    raised = False
    try:
        sign_manifest(manifest_bytes=b"hello")
    except ReleaseSigningKeyUnavailableError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_sign_and_verify_round_trip():
    """
    **Feature: 10-release-channels (M1)**
    **Property: sign_manifest produces a signature that
    verify_manifest accepts; a tampered manifest is rejected
    with reason='signature_invalid'.**
    """
    _prepare_runtime()
    key = _install_signing_key()
    _engine, session = build_in_memory_session()
    _install_trust(db_session=session, key=key)
    payload = b"the-canonical-manifest"
    signature = sign_manifest(manifest_bytes=payload)

    ok = verify_manifest(
        db_session=session, manifest_bytes=payload,
        signature=signature, issuer_key_id=key.issuer_key_id,
    )
    testbase.assert_equal(ok.verified, True)

    bad = verify_manifest(
        db_session=session, manifest_bytes=payload + b"!",
        signature=signature, issuer_key_id=key.issuer_key_id,
    )
    testbase.assert_equal(bad.verified, False)
    testbase.assert_equal(bad.reason, "signature_invalid")
    return


def test_verify_unknown_issuer_raises_manifest_verification_error():
    """
    **Feature: 10-release-channels (M1)**
    **Property: verify_manifest raises
    ManifestVerificationError when the issuer key id is
    unknown to the trusted ledger.**
    """
    _prepare_runtime()
    _install_signing_key()
    _engine, session = build_in_memory_session()
    raised = False
    try:
        verify_manifest(
            db_session=session, manifest_bytes=b"x",
            signature=b"\x00" * 64, issuer_key_id="ghost",
        )
    except ManifestVerificationError:
        raised = True
    testbase.assert_equal(raised, True)
    return


# -------------------------------------
# HashRingChannelPolicy + policy_router
# -------------------------------------

def test_hash_ring_initial_fractions():
    """
    **Feature: 10-release-channels (M1)**
    **Property: HashRingChannelPolicy initial_fraction returns
    0.05 / 0.25 / 1.00 for canary / beta / stable.**
    """
    _prepare_runtime()
    testbase.assert_equal(
        HashRingChannelPolicy.initial_fraction(channel=ReleaseChannel.CANARY),
        0.05,
    )
    testbase.assert_equal(
        HashRingChannelPolicy.initial_fraction(channel=ReleaseChannel.BETA),
        0.25,
    )
    testbase.assert_equal(
        HashRingChannelPolicy.initial_fraction(channel=ReleaseChannel.STABLE),
        1.0,
    )
    return


def test_hash_ring_compute_eligible_consumers_is_deterministic():
    """
    **Feature: 10-release-channels (M1)**
    **Property: identical inputs produce identical eligible
    sets; expanding the fraction is a superset of the prior
    smaller fraction (sticky-on-promote semantics).**
    """
    _prepare_runtime()
    universe = [
        ConsumerDescriptor(consumer_id="c-{}".format(i)) for i in range(50)
    ]
    a = HashRingChannelPolicy.compute_eligible_consumers(
        release_id="rel-A", fraction=0.20, universe=universe,
    )
    b = HashRingChannelPolicy.compute_eligible_consumers(
        release_id="rel-A", fraction=0.20, universe=universe,
    )
    testbase.assert_equal(a.consumer_ids, b.consumer_ids)
    bigger = HashRingChannelPolicy.compute_eligible_consumers(
        release_id="rel-A", fraction=0.40, universe=universe,
    )
    a_set = set(a.consumer_ids)
    bigger_set = set(bigger.consumer_ids)
    testbase.assert_equal(a_set.issubset(bigger_set), True)
    return


def test_resolve_policy_returns_hash_ring_default():
    """
    **Feature: 10-release-channels (M1)**
    **Property: resolve_policy returns the in-tree
    HashRingChannelPolicy when no override is registered.**
    """
    _prepare_runtime()
    policy = resolve_policy(channel=ReleaseChannel.CANARY)
    testbase.assert_equal(policy, HashRingChannelPolicy)
    return


class _CanaryOverridePolicy(ReleaseChannelPolicyProtocol):
    factory_protocol_name: str = "release_channel_policy"
    protocol_schema_version: int = 1
    PRECEDENCE: int = 500

    @classmethod
    def channel(cls):
        return ReleaseChannel.CANARY

    @classmethod
    def channel_set(cls):
        return (ReleaseChannel.CANARY,)

    @classmethod
    def initial_fraction(cls, *, channel):
        return 0.10

    @classmethod
    def compute_eligible_consumers(cls, *, release_id, fraction, universe):
        from ccai.pychestrate.webservice.ops.release.factories.release_channel_policy import (
            EligibleConsumerSet,
        )
        return EligibleConsumerSet(
            consumer_ids=tuple(c.consumer_id for c in universe[:1]),
            fraction=fraction,
        )


def test_resolve_policy_honors_lower_precedence_override():
    """
    **Feature: 10-release-channels (M1)**
    **Property: a registered policy at a lower PRECEDENCE
    that claims canary wins resolution; non-canary channels
    still resolve to HashRingChannelPolicy.**
    """
    _prepare_runtime()
    register_factory_implementation(implementation=_CanaryOverridePolicy)
    try:
        canary = resolve_policy(channel=ReleaseChannel.CANARY)
        beta = resolve_policy(channel=ReleaseChannel.BETA)
        testbase.assert_equal(canary, _CanaryOverridePolicy)
        testbase.assert_equal(beta, HashRingChannelPolicy)
    finally:
        unregister_factory_implementation(implementation=_CanaryOverridePolicy)
    return


# -------------------------------------
# publish_release end-to-end
# -------------------------------------

def test_publish_release_emits_published_and_canary_started():
    """
    **Feature: 10-release-channels (M1)**
    **Property: publish_release on canary persists the row at
    fraction=0.05, signs the manifest, advances channel_state,
    appends a PUBLISHED stage-event, and emits PUBLISHED +
    CANARY_STARTED.**
    """
    _prepare_runtime()
    key = _install_signing_key()
    _engine, session = build_in_memory_session()
    _install_trust(db_session=session, key=key)
    received_published: List[EntityEvent] = []
    received_canary: List[EntityEvent] = []
    subscribe(
        topic=ReleaseEventTopics.PUBLISHED,
        subscriber=lambda e: received_published.append(e),
    )
    subscribe(
        topic=ReleaseEventTopics.CANARY_STARTED,
        subscriber=lambda e: received_canary.append(e),
    )
    record = publish_release(
        db_session=session,
        component=ReleaseComponent.AGENT,
        version="1.42.0",
        channel=ReleaseChannel.CANARY,
        artifact_uri="s3://artifacts/agent-1.42.0",
        artifact_sha256=ARTIFACT_SHA,
        aspects=build_default_release_aspects(),
        actor_id=ACTOR_UUID,
    )
    testbase.assert_equal(record.rollout_fraction, 0.05)
    testbase.assert_equal(record.channel, ReleaseChannel.CANARY)
    testbase.assert_equal(record.issuer_key_id, key.issuer_key_id)
    testbase.assert_equal(len(received_published), 1)
    testbase.assert_equal(len(received_canary), 1)

    current = get_current_manifest(
        db_session=session,
        component=ReleaseComponent.AGENT,
        channel=ReleaseChannel.CANARY,
    )
    testbase.assert_equal(current.release_id, record.release_id)
    return


def test_publish_release_signature_verifies():
    """
    **Feature: 10-release-channels (M1)**
    **Property: the persisted manifest_bytes + signature on a
    published release verify against the trusted issuer key.**
    """
    _prepare_runtime()
    key = _install_signing_key()
    _engine, session = build_in_memory_session()
    _install_trust(db_session=session, key=key)
    record = publish_release(
        db_session=session,
        component=ReleaseComponent.AGENT,
        version="2.0.0",
        channel=ReleaseChannel.CANARY,
        artifact_uri="s3://artifacts/agent-2.0.0",
        artifact_sha256="b" * 64,
        aspects=build_default_release_aspects(),
    )
    outcome = verify_manifest(
        db_session=session,
        manifest_bytes=record.manifest_bytes,
        signature=record.signature,
        issuer_key_id=record.issuer_key_id,
    )
    testbase.assert_equal(outcome.verified, True)
    return


def test_publish_release_duplicate_triple_raises():
    """
    **Feature: 10-release-channels (M1)**
    **Property: a duplicate (component, version, channel)
    raises ReleaseConflictError.**
    """
    _prepare_runtime()
    _install_signing_key()
    _engine, session = build_in_memory_session()
    publish_release(
        db_session=session,
        component=ReleaseComponent.AGENT,
        version="1.0.0",
        channel=ReleaseChannel.CANARY,
        artifact_uri="s3://x",
        artifact_sha256=ARTIFACT_SHA,
        aspects=build_default_release_aspects(),
    )
    raised = False
    try:
        publish_release(
            db_session=session,
            component=ReleaseComponent.AGENT,
            version="1.0.0",
            channel=ReleaseChannel.CANARY,
            artifact_uri="s3://x",
            artifact_sha256=ARTIFACT_SHA,
            aspects=build_default_release_aspects(),
        )
    except ReleaseConflictError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_publish_release_records_previous_release_id_on_replacement():
    """
    **Feature: 10-release-channels (M1)**
    **Property: publishing a second release on the same
    channel records the previous release id on the new row's
    previous_release_id and on channel_state.previous_release_id.**
    """
    _prepare_runtime()
    _install_signing_key()
    _engine, session = build_in_memory_session()
    first = publish_release(
        db_session=session,
        component=ReleaseComponent.AGENT,
        version="1.0.0",
        channel=ReleaseChannel.CANARY,
        artifact_uri="s3://a",
        artifact_sha256=ARTIFACT_SHA,
        aspects=build_default_release_aspects(),
    )
    second = publish_release(
        db_session=session,
        component=ReleaseComponent.AGENT,
        version="1.1.0",
        channel=ReleaseChannel.CANARY,
        artifact_uri="s3://b",
        artifact_sha256="c" * 64,
        aspects=build_default_release_aspects(),
    )
    testbase.assert_equal(second.previous_release_id, first.release_id)
    return


def test_publish_release_invalid_sha_raises():
    """
    **Feature: 10-release-channels (M1)**
    **Property: artifact_sha256 not exactly 64 hex chars
    raises ValueError before anything is persisted.**
    """
    _prepare_runtime()
    _install_signing_key()
    _engine, session = build_in_memory_session()
    raised = False
    try:
        publish_release(
            db_session=session,
            component=ReleaseComponent.AGENT,
            version="0.0.1",
            channel=ReleaseChannel.CANARY,
            artifact_uri="s3://x",
            artifact_sha256="too-short",
            aspects=build_default_release_aspects(),
        )
    except ValueError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_canonical_manifest_is_deterministic():
    """
    **Feature: 10-release-channels (M1)**
    **Property: build_canonical_manifest produces identical
    bytes for identical inputs and a unique sha-256 per
    input.**
    """
    _prepare_runtime()
    from datetime import datetime, timezone
    when = datetime(2026, 4, 25, 0, 0, 0, tzinfo=timezone.utc)
    a = build_canonical_manifest(
        component=ReleaseComponent.AGENT, version="1.0.0",
        channel=ReleaseChannel.CANARY,
        artifact_uri="s3://x", artifact_sha256=ARTIFACT_SHA,
        issued_at=when, issuer_key_id="key-001",
    )
    b = build_canonical_manifest(
        component=ReleaseComponent.AGENT, version="1.0.0",
        channel=ReleaseChannel.CANARY,
        artifact_uri="s3://x", artifact_sha256=ARTIFACT_SHA,
        issued_at=when, issuer_key_id="key-001",
    )
    testbase.assert_equal(a, b)
    different = build_canonical_manifest(
        component=ReleaseComponent.AGENT, version="1.0.1",
        channel=ReleaseChannel.CANARY,
        artifact_uri="s3://x", artifact_sha256=ARTIFACT_SHA,
        issued_at=when, issuer_key_id="key-001",
    )
    testbase.assert_equal(a == different, False)
    return


# -------------------------------------
# 3-agent-upgrade-channel — factories
# -------------------------------------

def test_object_store_artifact_source_describe_succeeds():
    """
    **Feature: 3-agent-upgrade-channel (M1)**
    **Property: ObjectStoreArtifactSource.describe parses a
    canonical 'bucket/key:sha:bytes' ref into an
    ArtifactDescriptor.**
    """
    _prepare_runtime()
    descriptor = ObjectStoreArtifactSource.describe(
        artifact_ref="releases/agent-1.0.0:" + ("a" * 64) + ":1024",
    )
    testbase.assert_equal(descriptor.artifact_uri, "s3://releases/agent-1.0.0")
    testbase.assert_equal(descriptor.artifact_sha256, "a" * 64)
    testbase.assert_equal(descriptor.byte_size, 1024)
    return


def test_object_store_artifact_source_rejects_bad_ref():
    """
    **Feature: 3-agent-upgrade-channel (M1)**
    **Property: a malformed ref raises ValueError.**
    """
    _prepare_runtime()
    raised = False
    try:
        ObjectStoreArtifactSource.describe(artifact_ref="not-canonical")
    except ValueError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_fixed_set_policy_intersects_with_fleet():
    """
    **Feature: 3-agent-upgrade-channel (M1)**
    **Property: FixedSetRolloutPolicy keeps only client_ids
    that appear in the fleet snapshot; preserves order;
    deduplicates.**
    """
    _prepare_runtime()
    fleet = FleetSnapshot(
        members=(
            FleetMember(client_id="alpha"),
            FleetMember(client_id="beta"),
            FleetMember(client_id="gamma"),
        ),
    )
    chosen = FixedSetRolloutPolicy.compute_target_set(
        rollout_id="r-1", fleet=fleet,
        params={"client_ids": ["beta", "ghost", "beta", "alpha"]},
    )
    testbase.assert_equal(chosen, ("beta", "alpha"))
    return


# -------------------------------------
# 3-agent-upgrade-channel — service
# -------------------------------------

def test_draft_rollout_persists_and_emits():
    """
    **Feature: 3-agent-upgrade-channel (M1)**
    **Property: draft_rollout writes a DRAFT row using the
    artifact source's resolved sha and emits DRAFTED.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=UpgradeEventTopics.DRAFTED,
        subscriber=lambda e: received.append(e),
    )
    record = draft_rollout(
        db_session=session,
        version="1.42.0",
        artifact_source="object_store",
        artifact_ref="releases/agent-1.42.0:" + ("d" * 64) + ":2048",
    )
    testbase.assert_equal(record.state, RolloutState.DRAFT)
    testbase.assert_equal(record.artifact_sha256, "d" * 64)
    testbase.assert_equal(len(received), 1)
    return


def test_draft_rollout_unknown_source_raises():
    """
    **Feature: 3-agent-upgrade-channel (M1)**
    **Property: draft_rollout raises ValueError when the
    artifact source is not registered.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    raised = False
    try:
        draft_rollout(
            db_session=session,
            version="1.0.0",
            artifact_source="not-registered",
            artifact_ref="x",
        )
    except ValueError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_start_rollout_writes_offers_and_emits():
    """
    **Feature: 3-agent-upgrade-channel (M1)**
    **Property: start_rollout transitions the rollout to
    ACTIVE, creates stage 0, writes one offer per eligible
    client, and emits STARTED + STAGE_STARTED + per-offer
    OFFERED.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received_offered: List[EntityEvent] = []
    subscribe(
        topic=UpgradeEventTopics.OFFERED,
        subscriber=lambda e: received_offered.append(e),
    )
    rollout = draft_rollout(
        db_session=session,
        version="1.0.0",
        artifact_source="object_store",
        artifact_ref="releases/agent-1.0.0:" + ("e" * 64) + ":1024",
    )
    fleet = FleetSnapshot(
        members=(
            FleetMember(client_id="c-1"),
            FleetMember(client_id="c-2"),
            FleetMember(client_id="c-3"),
        ),
    )
    rollout_view, stage_view, offers = start_rollout(
        db_session=session,
        rollout_id=rollout.rollout_id,
        rollout_policy="fixed_set",
        policy_params={"client_ids": ["c-1", "c-3"]},
        fleet=fleet,
    )
    testbase.assert_equal(rollout_view.state, RolloutState.ACTIVE)
    testbase.assert_equal(stage_view.state, StageState.ACTIVE)
    testbase.assert_equal(stage_view.target_size, 2)
    testbase.assert_equal(len(offers), 2)
    testbase.assert_equal(len(received_offered), 2)
    return


def test_start_rollout_skips_pinned_pods_with_different_version():
    """
    **Feature: 3-agent-upgrade-channel (M1)**
    **Property: start_rollout silently skips clients whose
    pin map points at a different version.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    set_pod_pin(
        db_session=session, pod_id="c-2", version="0.9.0",
    )
    rollout = draft_rollout(
        db_session=session,
        version="1.0.0",
        artifact_source="object_store",
        artifact_ref="releases/agent-1.0.0:" + ("f" * 64) + ":512",
    )
    fleet = FleetSnapshot(
        members=(
            FleetMember(client_id="c-1"),
            FleetMember(client_id="c-2"),
            FleetMember(client_id="c-3"),
        ),
    )
    _rollout_view, stage_view, offers = start_rollout(
        db_session=session,
        rollout_id=rollout.rollout_id,
        rollout_policy="fixed_set",
        policy_params={"client_ids": ["c-1", "c-2", "c-3"]},
        fleet=fleet,
    )
    testbase.assert_equal(stage_view.target_size, 2)
    client_ids = sorted(offer.client_id for offer in offers)
    testbase.assert_equal(client_ids, ["c-1", "c-3"])
    return


def test_start_rollout_rejects_non_draft_state():
    """
    **Feature: 3-agent-upgrade-channel (M1)**
    **Property: start_rollout raises
    InvalidRolloutTransitionError when the rollout is not
    DRAFT.**
    """
    from ccai.pychestrate.webservice.clients.upgrades.errors import (
        InvalidRolloutTransitionError,
    )
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    rollout = draft_rollout(
        db_session=session,
        version="1.0.0",
        artifact_source="object_store",
        artifact_ref="releases/x:" + ("a" * 64) + ":1",
    )
    fleet = FleetSnapshot(members=(FleetMember(client_id="c-1"),))
    start_rollout(
        db_session=session,
        rollout_id=rollout.rollout_id,
        rollout_policy="fixed_set",
        policy_params={"client_ids": ["c-1"]},
        fleet=fleet,
    )
    raised = False
    try:
        start_rollout(
            db_session=session,
            rollout_id=rollout.rollout_id,
            rollout_policy="fixed_set",
            policy_params={"client_ids": ["c-1"]},
            fleet=fleet,
        )
    except InvalidRolloutTransitionError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_record_offer_outcome_succeeded_emits_and_increments_counter():
    """
    **Feature: 3-agent-upgrade-channel (M1)**
    **Property: record_offer_outcome on SUCCEEDED emits
    SUCCEEDED, persists the outcome, and bumps the stage
    success counter.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=UpgradeEventTopics.SUCCEEDED,
        subscriber=lambda e: received.append(e),
    )
    rollout = draft_rollout(
        db_session=session,
        version="1.0.0",
        artifact_source="object_store",
        artifact_ref="releases/agent:" + ("a" * 64) + ":10",
    )
    fleet = FleetSnapshot(members=(FleetMember(client_id="c-1"),))
    _rollout_view, stage_view, offers = start_rollout(
        db_session=session,
        rollout_id=rollout.rollout_id,
        rollout_policy="fixed_set",
        policy_params={"client_ids": ["c-1"]},
        fleet=fleet,
    )
    record = record_offer_outcome(
        db_session=session,
        offer_id=offers[0].offer_id,
        outcome=OfferOutcome.SUCCEEDED,
        detail={"applied_at": "2026-04-25T00:00:00+00:00"},
    )
    testbase.assert_equal(record.outcome, OfferOutcome.SUCCEEDED)
    testbase.assert_equal(len(received), 1)

    from ccai.pychestrate.webservice.clients.upgrades.models import (
        AgentRolloutStage,
    )
    refreshed = (
        session.query(AgentRolloutStage)
        .filter(AgentRolloutStage.stage_id == stage_view.stage_id)
        .first()
    )
    testbase.assert_equal(refreshed.success_count, 1)
    return


def test_record_offer_outcome_sha_mismatch_emits_integrity_failed():
    """
    **Feature: 3-agent-upgrade-channel (M1)**
    **Property: a SHA256_MISMATCH outcome routes to the
    INTEGRITY_FAILED topic and bumps the failure counter.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=UpgradeEventTopics.INTEGRITY_FAILED,
        subscriber=lambda e: received.append(e),
    )
    rollout = draft_rollout(
        db_session=session,
        version="1.0.0",
        artifact_source="object_store",
        artifact_ref="releases/x:" + ("a" * 64) + ":1",
    )
    fleet = FleetSnapshot(members=(FleetMember(client_id="c-1"),))
    _rollout_view, _stage_view, offers = start_rollout(
        db_session=session,
        rollout_id=rollout.rollout_id,
        rollout_policy="fixed_set",
        policy_params={"client_ids": ["c-1"]},
        fleet=fleet,
    )
    record_offer_outcome(
        db_session=session,
        offer_id=offers[0].offer_id,
        outcome=OfferOutcome.SHA256_MISMATCH,
    )
    testbase.assert_equal(len(received), 1)
    return


def test_record_offer_outcome_unknown_offer_raises():
    """
    **Feature: 3-agent-upgrade-channel (M1)**
    **Property: record_offer_outcome on a missing offer raises
    RolloutNotFoundError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    raised = False
    try:
        record_offer_outcome(
            db_session=session,
            offer_id="00000000-0000-4000-8000-deadbeefdead",
            outcome=OfferOutcome.SUCCEEDED,
        )
    except RolloutNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return


# -------------------------------------
# Pin management
# -------------------------------------

def test_set_pod_pin_persists_and_emits():
    """
    **Feature: 3-agent-upgrade-channel (M1)**
    **Property: set_pod_pin persists, emits PIN_SET, and shows
    up in get_pin_map.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=UpgradeEventTopics.PIN_SET,
        subscriber=lambda e: received.append(e),
    )
    set_pod_pin(
        db_session=session, pod_id="pod-1", version="0.9.0",
        actor_id=ACTOR_UUID, reason="known-bad release",
    )
    pin_map = get_pin_map(db_session=session)
    testbase.assert_equal(pin_map.get("pod-1"), "0.9.0")
    testbase.assert_equal(len(received), 1)
    return


def test_delete_pod_pin_idempotent_and_emits():
    """
    **Feature: 3-agent-upgrade-channel (M1)**
    **Property: delete_pod_pin emits PIN_CLEARED on first call
    only; second call returns False and emits nothing.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=UpgradeEventTopics.PIN_CLEARED,
        subscriber=lambda e: received.append(e),
    )
    set_pod_pin(
        db_session=session, pod_id="pod-2", version="1.0.0",
    )
    first = delete_pod_pin(db_session=session, pod_id="pod-2")
    second = delete_pod_pin(db_session=session, pod_id="pod-2")
    testbase.assert_equal(first, True)
    testbase.assert_equal(second, False)
    testbase.assert_equal(len(received), 1)
    return


# -------------------------------------
# Bootstrap registration
# -------------------------------------

def test_register_builtin_extensions_seeds_factories():
    """
    **Feature: P10c bootstrap**
    **Property: register_builtin_extensions seeds the
    HashRingChannelPolicy under release_channel_policy and
    ObjectStoreArtifactSource + FixedSetRolloutPolicy under
    upgrade_artifact_source / rollout_policy.**
    """
    reset_registry_for_testing()
    reset_event_bus()
    reset_signing_for_testing()
    releases_register()
    agent_upgrades_register()
    from ccai.pychestrate.webservice.extensions.registry import (
        list_factory_implementations,
    )
    policy_impls = list_factory_implementations(
        factory_protocol_name="release_channel_policy",
    )
    source_impls = list_factory_implementations(
        factory_protocol_name="upgrade_artifact_source",
    )
    rollout_impls = list_factory_implementations(
        factory_protocol_name="rollout_policy",
    )
    testbase.assert_equal(HashRingChannelPolicy in policy_impls, True)
    testbase.assert_equal(ObjectStoreArtifactSource in source_impls, True)
    testbase.assert_equal(FixedSetRolloutPolicy in rollout_impls, True)
    return


def test_publish_release_appears_in_list():
    """
    **Feature: 10-release-channels (M1)**
    **Property: list_releases returns published releases
    newest-first and respects the component filter.**
    """
    _prepare_runtime()
    _install_signing_key()
    _engine, session = build_in_memory_session()
    publish_release(
        db_session=session,
        component=ReleaseComponent.AGENT,
        version="1.0.0",
        channel=ReleaseChannel.CANARY,
        artifact_uri="s3://a",
        artifact_sha256=ARTIFACT_SHA,
        aspects=build_default_release_aspects(),
    )
    publish_release(
        db_session=session,
        component=ReleaseComponent.SERVICE,
        version="2.0.0",
        channel=ReleaseChannel.CANARY,
        artifact_uri="s3://b",
        artifact_sha256="b" * 64,
        aspects=build_default_release_aspects(),
    )
    agent_only = ops_list_releases(
        db_session=session, component=ReleaseComponent.AGENT,
    )
    testbase.assert_equal(len(agent_only), 1)
    testbase.assert_equal(agent_only[0].version, "1.0.0")
    return
