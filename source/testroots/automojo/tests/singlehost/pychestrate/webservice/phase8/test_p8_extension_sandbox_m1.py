"""
.. module:: test_p8_extension_sandbox_m1
    :synopsis: Tests for P8 — E-extension-sandbox M1.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import List

from automojo import testbase

from automojo.pychestrate.webservice.extensions.registry import (
    reset_registry_for_testing,
)
from automojo.pychestrate.webservice.extensions.sandbox import (
    CAPABILITY_VOCABULARY,
    CapabilityAuthority,
    CapabilityGrantSource,
    CapabilityVocabulary,
    ExtensionManifest,
    SandboxEventTopics,
    UnknownCapabilityError,
    get_capability_authority,
    grant_capability,
    list_grants_for_extension,
    reload_authority_from_db,
    reset_authority_for_testing,
    revoke_capability,
)
from automojo.pychestrate.webservice.messaging.event_bus import (
    EntityEvent,
    reset_for_testing as reset_event_bus,
    subscribe,
)

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
)


ACTOR_UUID = "00000000-0000-4000-8000-000000070001"
EXT_NAME = "pychestrate-ext-sample"


def _prepare_runtime() -> None:
    reset_registry_for_testing()
    reset_event_bus()
    reset_authority_for_testing()
    return


# -------------------------------------
# Vocabulary
# -------------------------------------

def test_vocabulary_is_closed_set():
    """
    **Feature: E-extension-sandbox (M1)**
    **Property: CAPABILITY_VOCABULARY contains exactly the
    five M1 entries.**
    """
    _prepare_runtime()
    expected = frozenset({
        CapabilityVocabulary.READ_SECRETS,
        CapabilityVocabulary.WRITE_ARTIFACTS,
        CapabilityVocabulary.DISPATCH_JOBS,
        CapabilityVocabulary.NET_OUTBOUND,
        CapabilityVocabulary.PROCESS_SUBPROCESS,
    })
    testbase.assert_equal(CAPABILITY_VOCABULARY, expected)
    return


# -------------------------------------
# CapabilityAuthority
# -------------------------------------

def test_authority_singleton_returns_same_instance():
    """
    **Feature: E-extension-sandbox (M1)**
    **Property: get_capability_authority returns the same
    instance across calls; reset_authority_for_testing drops
    it.**
    """
    _prepare_runtime()
    a = get_capability_authority()
    b = get_capability_authority()
    testbase.assert_equal(a is b, True)
    reset_authority_for_testing()
    c = get_capability_authority()
    testbase.assert_equal(c is a, False)
    return


def test_reload_from_manifests_replaces_active_set():
    """
    **Feature: E-extension-sandbox (M1)**
    **Property: reload_from_manifests replaces the active set
    with the manifest-declared grants.**
    """
    _prepare_runtime()
    authority = get_capability_authority()
    authority.reload_from_manifests(manifests=[
        ExtensionManifest(
            ext_name="ext-a",
            declared_capabilities=frozenset({
                CapabilityVocabulary.DISPATCH_JOBS,
                CapabilityVocabulary.NET_OUTBOUND,
            }),
        ),
        ExtensionManifest(
            ext_name="ext-b",
            declared_capabilities=frozenset({
                CapabilityVocabulary.READ_SECRETS,
            }),
        ),
    ])
    testbase.assert_equal(
        authority.granted_for(ext_name="ext-a"),
        frozenset({"dispatch:jobs", "net:outbound"}),
    )
    testbase.assert_equal(
        authority.granted_for(ext_name="ext-b"),
        frozenset({"read:secrets"}),
    )

    # Re-reload with a smaller set replaces, doesn't merge.
    authority.reload_from_manifests(manifests=[
        ExtensionManifest(ext_name="ext-a", declared_capabilities=frozenset()),
    ])
    testbase.assert_equal(
        authority.granted_for(ext_name="ext-a"), frozenset(),
    )
    # ext-b is no longer in the active set after replacement.
    testbase.assert_equal(
        authority.granted_for(ext_name="ext-b"), frozenset(),
    )
    return


def test_reload_unknown_capability_raises():
    """
    **Feature: E-extension-sandbox (M1)**
    **Property: a manifest declaring an unknown capability
    raises UnknownCapabilityError listing the offending
    string.**
    """
    _prepare_runtime()
    authority = get_capability_authority()
    raised = False
    try:
        authority.reload_from_manifests(manifests=[
            ExtensionManifest(
                ext_name="bad",
                declared_capabilities=frozenset({"talk:to:martians"}),
            ),
        ])
    except UnknownCapabilityError as xcpt:
        raised = True
        testbase.assert_equal("talk:to:martians" in str(xcpt), True)
    testbase.assert_equal(raised, True)
    return


def test_in_memory_grant_revoke_round_trip():
    """
    **Feature: E-extension-sandbox (M1)**
    **Property: grant_capability_in_memory adds the capability,
    revoke_capability_in_memory removes it, and
    granted_for reflects each step.**
    """
    _prepare_runtime()
    authority = get_capability_authority()
    authority.grant_capability_in_memory(
        ext_name="ext-c",
        capability=CapabilityVocabulary.DISPATCH_JOBS,
    )
    authority.grant_capability_in_memory(
        ext_name="ext-c",
        capability=CapabilityVocabulary.NET_OUTBOUND,
    )
    testbase.assert_equal(
        authority.granted_for(ext_name="ext-c"),
        frozenset({"dispatch:jobs", "net:outbound"}),
    )
    authority.revoke_capability_in_memory(
        ext_name="ext-c", capability=CapabilityVocabulary.DISPATCH_JOBS,
    )
    testbase.assert_equal(
        authority.granted_for(ext_name="ext-c"),
        frozenset({"net:outbound"}),
    )
    return


def test_in_memory_grant_unknown_capability_raises():
    """
    **Feature: E-extension-sandbox (M1)**
    **Property: grant_capability_in_memory rejects an unknown
    capability.**
    """
    _prepare_runtime()
    authority = get_capability_authority()
    raised = False
    try:
        authority.grant_capability_in_memory(
            ext_name="ext-x", capability="talk:to:martians",
        )
    except UnknownCapabilityError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_authorize_factory_call_passthrough():
    """
    **Feature: E-extension-sandbox (M1)**
    **Property: authorize_factory_call returns True for the
    zero-capability default; True when granted set covers
    requirements; False when missing.**
    """
    _prepare_runtime()
    authority = get_capability_authority()
    # Zero-capability default — no protocol requirements.
    testbase.assert_equal(
        authority.authorize_factory_call(
            ext_name="ext-d", protocol_name="some_protocol",
        ),
        True,
    )

    authority.declare_protocol_requirements(
        protocol_name="dispatch_strategy",
        required={CapabilityVocabulary.DISPATCH_JOBS},
    )
    testbase.assert_equal(
        authority.authorize_factory_call(
            ext_name="ext-d", protocol_name="dispatch_strategy",
        ),
        False,
    )

    authority.grant_capability_in_memory(
        ext_name="ext-d", capability=CapabilityVocabulary.DISPATCH_JOBS,
    )
    testbase.assert_equal(
        authority.authorize_factory_call(
            ext_name="ext-d", protocol_name="dispatch_strategy",
        ),
        True,
    )
    return


def test_authorize_hook_delivery_passthrough():
    """
    **Feature: E-extension-sandbox (M1)**
    **Property: authorize_hook_delivery is a subset check
    against the topic's requirements.**
    """
    _prepare_runtime()
    authority = get_capability_authority()
    authority.declare_topic_requirements(
        topic="entity.run.completed",
        required={CapabilityVocabulary.READ_SECRETS},
    )
    testbase.assert_equal(
        authority.authorize_hook_delivery(
            ext_name="ext-e", topic="entity.run.completed",
        ),
        False,
    )
    authority.grant_capability_in_memory(
        ext_name="ext-e", capability=CapabilityVocabulary.READ_SECRETS,
    )
    testbase.assert_equal(
        authority.authorize_hook_delivery(
            ext_name="ext-e", topic="entity.run.completed",
        ),
        True,
    )
    return


def test_snapshot_state_returns_frozen_view():
    """
    **Feature: E-extension-sandbox (M1)**
    **Property: snapshot_state returns the current vocabulary +
    active map + protocol/topic requirement maps.**
    """
    _prepare_runtime()
    authority = get_capability_authority()
    authority.grant_capability_in_memory(
        ext_name="ext-f",
        capability=CapabilityVocabulary.WRITE_ARTIFACTS,
    )
    authority.declare_protocol_requirements(
        protocol_name="artifact_writer",
        required={CapabilityVocabulary.WRITE_ARTIFACTS},
    )
    state = authority.snapshot_state()
    testbase.assert_equal(state.vocabulary, CAPABILITY_VOCABULARY)
    testbase.assert_equal(
        state.active.get("ext-f"), frozenset({"write:artifacts"}),
    )
    testbase.assert_equal(
        state.protocol_requirements.get("artifact_writer"),
        frozenset({"write:artifacts"}),
    )
    return


# -------------------------------------
# Persistence-backed grant / revoke service
# -------------------------------------

def test_grant_capability_persists_and_emits():
    """
    **Feature: E-extension-sandbox (M1)**
    **Property: grant_capability persists a row, adds the
    capability to the in-memory authority, and emits
    extension.capability_granted.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=SandboxEventTopics.GRANTED,
        subscriber=lambda e: received.append(e),
    )
    view = grant_capability(
        db_session=session, ext_name=EXT_NAME,
        capability=CapabilityVocabulary.DISPATCH_JOBS,
        source=CapabilityGrantSource.ADMIN,
        actor_id=ACTOR_UUID,
    )
    testbase.assert_equal(view.is_active, True)
    testbase.assert_equal(view.source, "admin")
    testbase.assert_equal(view.capability, "dispatch:jobs")
    testbase.assert_equal(len(received), 1)
    authority = get_capability_authority()
    testbase.assert_equal(
        "dispatch:jobs" in authority.granted_for(ext_name=EXT_NAME), True,
    )
    return


def test_grant_capability_unknown_raises():
    """
    **Feature: E-extension-sandbox (M1)**
    **Property: grant_capability rejects an unknown capability
    with UnknownCapabilityError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    raised = False
    try:
        grant_capability(
            db_session=session, ext_name=EXT_NAME,
            capability="talk:to:martians",
        )
    except UnknownCapabilityError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_revoke_capability_persists_and_emits():
    """
    **Feature: E-extension-sandbox (M1)**
    **Property: revoke_capability stamps revoked_at, drops the
    in-memory bit, and emits extension.capability_revoked.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=SandboxEventTopics.REVOKED,
        subscriber=lambda e: received.append(e),
    )
    grant_capability(
        db_session=session, ext_name=EXT_NAME,
        capability=CapabilityVocabulary.DISPATCH_JOBS,
        actor_id=ACTOR_UUID,
    )
    revoked = revoke_capability(
        db_session=session, ext_name=EXT_NAME,
        capability=CapabilityVocabulary.DISPATCH_JOBS,
        actor_id=ACTOR_UUID, reason="reduce blast radius",
    )
    testbase.assert_equal(revoked.is_active, False)
    testbase.assert_equal(revoked.revoked_reason, "reduce blast radius")
    testbase.assert_equal(len(received), 1)
    authority = get_capability_authority()
    testbase.assert_equal(
        "dispatch:jobs" in authority.granted_for(ext_name=EXT_NAME), False,
    )
    return


def test_revoke_unknown_grant_raises():
    """
    **Feature: E-extension-sandbox (M1)**
    **Property: revoke_capability against a (ext_name,
    capability) pair with no row raises
    UnknownCapabilityError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    raised = False
    try:
        revoke_capability(
            db_session=session, ext_name="unknown-ext",
            capability=CapabilityVocabulary.DISPATCH_JOBS,
            actor_id=ACTOR_UUID, reason="x",
        )
    except UnknownCapabilityError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_grant_then_revoke_then_grant_revives_row():
    """
    **Feature: E-extension-sandbox (M1)**
    **Property: re-granting a previously-revoked capability
    revives the same row (revoked_at cleared) and re-emits
    GRANTED.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    grant_capability(
        db_session=session, ext_name=EXT_NAME,
        capability=CapabilityVocabulary.NET_OUTBOUND,
    )
    revoke_capability(
        db_session=session, ext_name=EXT_NAME,
        capability=CapabilityVocabulary.NET_OUTBOUND,
        actor_id=ACTOR_UUID, reason="temporary",
    )
    revived = grant_capability(
        db_session=session, ext_name=EXT_NAME,
        capability=CapabilityVocabulary.NET_OUTBOUND,
        actor_id=ACTOR_UUID,
    )
    testbase.assert_equal(revived.is_active, True)
    testbase.assert_equal(revived.revoked_at is None, True)
    rows = list_grants_for_extension(
        db_session=session, ext_name=EXT_NAME,
    )
    testbase.assert_equal(len(rows), 1)
    return


def test_list_grants_active_only_filter():
    """
    **Feature: E-extension-sandbox (M1)**
    **Property: list_grants_for_extension can filter to active
    rows only.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    grant_capability(
        db_session=session, ext_name=EXT_NAME,
        capability=CapabilityVocabulary.DISPATCH_JOBS,
    )
    grant_capability(
        db_session=session, ext_name=EXT_NAME,
        capability=CapabilityVocabulary.NET_OUTBOUND,
    )
    revoke_capability(
        db_session=session, ext_name=EXT_NAME,
        capability=CapabilityVocabulary.DISPATCH_JOBS,
        actor_id=ACTOR_UUID, reason="x",
    )
    all_rows = list_grants_for_extension(
        db_session=session, ext_name=EXT_NAME,
    )
    active_rows = list_grants_for_extension(
        db_session=session, ext_name=EXT_NAME, active_only=True,
    )
    testbase.assert_equal(len(all_rows), 2)
    testbase.assert_equal(len(active_rows), 1)
    testbase.assert_equal(active_rows[0].capability, "net:outbound")
    return


# -------------------------------------
# reload_authority_from_db
# -------------------------------------

def test_reload_authority_from_db_replays_active_grants():
    """
    **Feature: E-extension-sandbox (M1)**
    **Property: reload_authority_from_db replays every active
    ledger row into the in-memory authority. Revoked rows are
    skipped.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    grant_capability(
        db_session=session, ext_name="ext-replay-1",
        capability=CapabilityVocabulary.DISPATCH_JOBS,
    )
    grant_capability(
        db_session=session, ext_name="ext-replay-1",
        capability=CapabilityVocabulary.NET_OUTBOUND,
    )
    grant_capability(
        db_session=session, ext_name="ext-replay-2",
        capability=CapabilityVocabulary.WRITE_ARTIFACTS,
    )
    revoke_capability(
        db_session=session, ext_name="ext-replay-1",
        capability=CapabilityVocabulary.NET_OUTBOUND,
        actor_id=ACTOR_UUID, reason="rotate",
    )

    # Drop the in-memory state and reload from the ledger.
    reset_authority_for_testing()
    received: List[EntityEvent] = []
    subscribe(
        topic=SandboxEventTopics.AUTHORITY_RELOADED,
        subscriber=lambda e: received.append(e),
    )
    reload_authority_from_db(db_session=session)
    authority = get_capability_authority()
    testbase.assert_equal(
        authority.granted_for(ext_name="ext-replay-1"),
        frozenset({"dispatch:jobs"}),
    )
    testbase.assert_equal(
        authority.granted_for(ext_name="ext-replay-2"),
        frozenset({"write:artifacts"}),
    )
    testbase.assert_equal(len(received), 1)
    return
