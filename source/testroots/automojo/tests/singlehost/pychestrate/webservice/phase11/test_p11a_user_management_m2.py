"""
.. module:: test_p11a_user_management_m2
    :synopsis: Tests for P11a — 1-user-management M2.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime, timedelta, timezone
from typing import Iterator, List

from automojo import testbase

from automojo.errors.exceptions import SemanticError

from automojo.pychestrate.webservice.extensions.registry import (
    register_factory_implementation,
    reset_registry_for_testing,
    unregister_factory_implementation,
)
from automojo.pychestrate.webservice.identity.users import (
    directory_sync,
    group_service,
    user_service,
)
from automojo.pychestrate.webservice.identity.users.events import (
    UserEventTopics,
)
from automojo.pychestrate.webservice.identity.users.exceptions import (
    DirectoryCollisionError,
    UserAlreadyExistsError,
    UserNotFoundError,
)
from automojo.pychestrate.webservice.identity.users.factories.user_directory_source import (
    ExternalGroupRecord,
    ExternalUserRecord,
    UserDirectorySourceProtocol,
)
from automojo.pychestrate.webservice.identity.users.models import UserStatus
from automojo.pychestrate.webservice.identity.users.repositories import (
    user_repository,
)
from automojo.pychestrate.webservice.messaging.event_bus import (
    EntityEvent,
    reset_for_testing as reset_event_bus,
    subscribe,
)

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
)


ACTOR_UUID = "00000000-0000-4000-8000-000000400001"


def _prepare_runtime() -> None:
    reset_registry_for_testing()
    reset_event_bus()
    user_service.reset_for_testing()
    return


def _make_user(
        *, session, login: str, email: str, source: str = "local"
    ):
    user = user_service.create_user(
        db_session=session,
        login_name=login,
        primary_email=email,
        display_name=login.upper(),
        timezone="UTC",
        provisioning_source=source,
        external_id=login + "-ext" if source != "local" else None,
        actor_user_id=ACTOR_UUID,
    )
    return user


# -------------------------------------
# Deactivate / reactivate
# -------------------------------------

def test_deactivate_user_flips_status_emits_and_invokes_callback():
    """
    **Feature: 1-user-management (M2)**
    **Property: deactivate_user flips status to DEACTIVATED,
    emits USER_DEACTIVATED, and invokes the registered
    session-revocation callback after commit.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=UserEventTopics.USER_DEACTIVATED,
        subscriber=lambda e: received.append(e),
    )
    revoked_for: List[str] = []
    user_service.set_session_revocation_callback(
        callback=lambda user_id: revoked_for.append(user_id),
    )

    user = _make_user(session=session, login="alice", email="alice@x.com")
    deactivated = user_service.deactivate_user(
        db_session=session, user_id=str(user.user_id),
        reason="off-boarded", actor_user_id=ACTOR_UUID,
    )
    testbase.assert_equal(deactivated.status, UserStatus.DEACTIVATED)
    testbase.assert_equal(len(received), 1)
    testbase.assert_equal(revoked_for, [str(user.user_id)])
    return


def test_deactivate_user_idempotent_on_already_deactivated():
    """
    **Feature: 1-user-management (M2)**
    **Property: deactivating an already-deactivated user is a
    no-op — no second event, no second callback invocation.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=UserEventTopics.USER_DEACTIVATED,
        subscriber=lambda e: received.append(e),
    )
    revoked_for: List[str] = []
    user_service.set_session_revocation_callback(
        callback=lambda user_id: revoked_for.append(user_id),
    )
    user = _make_user(session=session, login="bob", email="bob@x.com")
    user_service.deactivate_user(
        db_session=session, user_id=str(user.user_id),
    )
    user_service.deactivate_user(
        db_session=session, user_id=str(user.user_id),
    )
    testbase.assert_equal(len(received), 1)
    testbase.assert_equal(len(revoked_for), 1)
    return


def test_reactivate_user_returns_active_and_emits():
    """
    **Feature: 1-user-management (M2)**
    **Property: reactivating a DEACTIVATED user flips status
    back to ACTIVE and emits USER_REACTIVATED.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=UserEventTopics.USER_REACTIVATED,
        subscriber=lambda e: received.append(e),
    )
    user = _make_user(session=session, login="carol", email="carol@x.com")
    user_service.deactivate_user(
        db_session=session, user_id=str(user.user_id),
    )
    record = user_service.reactivate_user(
        db_session=session, user_id=str(user.user_id),
    )
    testbase.assert_equal(record.status, UserStatus.ACTIVE)
    testbase.assert_equal(len(received), 1)
    return


def test_reactivate_user_idempotent_on_active():
    """
    **Feature: 1-user-management (M2)**
    **Property: reactivating an ACTIVE user is a no-op and
    emits nothing.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=UserEventTopics.USER_REACTIVATED,
        subscriber=lambda e: received.append(e),
    )
    user = _make_user(session=session, login="dave", email="dave@x.com")
    user_service.reactivate_user(
        db_session=session, user_id=str(user.user_id),
    )
    testbase.assert_equal(len(received), 0)
    return


# -------------------------------------
# list_users — filters + cursor pagination
# -------------------------------------

def test_list_users_status_filter():
    """
    **Feature: 1-user-management (M2)**
    **Property: list_users(status=DEACTIVATED) returns only
    deactivated rows.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    a = _make_user(session=session, login="active1", email="a1@x.com")
    b = _make_user(session=session, login="active2", email="a2@x.com")
    c = _make_user(session=session, login="dropped", email="d@x.com")
    user_service.deactivate_user(
        db_session=session, user_id=str(c.user_id),
    )
    page = user_service.list_users(
        db_session=session, status=UserStatus.DEACTIVATED,
    )
    logins = sorted(u.login_name for u in page.users)
    testbase.assert_equal(logins, ["dropped"])
    testbase.assert_equal(page.next_cursor, None)
    return


def test_list_users_login_prefix_filter_is_case_insensitive():
    """
    **Feature: 1-user-management (M2)**
    **Property: list_users(login_prefix='AL') matches every
    login starting with 'al' regardless of case.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    _make_user(session=session, login="alice", email="alice@x.com")
    _make_user(session=session, login="bob", email="bob@x.com")
    page = user_service.list_users(
        db_session=session, login_prefix="AL",
    )
    logins = sorted(u.login_name for u in page.users)
    testbase.assert_equal(logins, ["alice"])
    return


def test_list_users_cursor_pagination_round_trips():
    """
    **Feature: 1-user-management (M2)**
    **Property: paging through list_users with the previous
    page's next_cursor returns the next stable batch and
    surfaces every user exactly once.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    for i in range(5):
        _make_user(
            session=session,
            login="user{}".format(i),
            email="user{}@x.com".format(i),
        )
    page_one = user_service.list_users(db_session=session, limit=2)
    page_two = user_service.list_users(
        db_session=session, cursor=page_one.next_cursor, limit=2,
    )
    page_three = user_service.list_users(
        db_session=session, cursor=page_two.next_cursor, limit=2,
    )
    all_logins = (
        [u.login_name for u in page_one.users]
        + [u.login_name for u in page_two.users]
        + [u.login_name for u in page_three.users]
    )
    testbase.assert_equal(sorted(all_logins), [
        "user0", "user1", "user2", "user3", "user4",
    ])
    testbase.assert_equal(page_three.next_cursor, None)
    return


def test_list_users_invalid_limit_raises():
    """
    **Feature: 1-user-management (M2)**
    **Property: a non-positive limit raises ValueError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    raised = False
    try:
        user_service.list_users(db_session=session, limit=0)
    except ValueError:
        raised = True
    testbase.assert_equal(raised, True)
    return


# -------------------------------------
# Email re-verification
# -------------------------------------

def test_request_and_confirm_email_change_round_trips():
    """
    **Feature: 1-user-management (M2)**
    **Property: request_email_change issues a fresh token; the
    confirm path swaps primary_email and emits USER_UPDATED.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=UserEventTopics.USER_UPDATED,
        subscriber=lambda e: received.append(e),
    )
    user = _make_user(session=session, login="erin", email="erin@x.com")
    challenge = user_service.request_email_change(
        db_session=session, user_id=str(user.user_id),
        new_email="erin.new@x.com",
    )
    testbase.assert_equal(len(challenge.token) > 0, True)
    user_service.confirm_email_change(
        db_session=session, token=challenge.token,
    )
    refreshed = user_service.read_user(
        db_session=session, user_id=str(user.user_id),
    )
    testbase.assert_equal(refreshed.primary_email, "erin.new@x.com")
    # request emit + confirm emit + create emit (USER_UPDATED matches both).
    request_phases = [
        e.payload.get("phase") for e in received
        if e.payload.get("field") == "primary_email"
    ]
    testbase.assert_equal(
        sorted(request_phases), ["verification_requested", "verified"],
    )
    return


def test_request_email_change_rejects_duplicate_email():
    """
    **Feature: 1-user-management (M2)**
    **Property: requesting an email change to an address held
    by a different user raises UserAlreadyExistsError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    a = _make_user(session=session, login="ana", email="ana@x.com")
    _make_user(session=session, login="zoe", email="zoe@x.com")
    raised = False
    try:
        user_service.request_email_change(
            db_session=session, user_id=str(a.user_id),
            new_email="zoe@x.com",
        )
    except UserAlreadyExistsError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_request_email_change_requires_active_user():
    """
    **Feature: 1-user-management (M2)**
    **Property: a deactivated user cannot start an email
    change; SemanticError surfaces.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    user = _make_user(session=session, login="frank", email="frank@x.com")
    user_service.deactivate_user(
        db_session=session, user_id=str(user.user_id),
    )
    raised = False
    try:
        user_service.request_email_change(
            db_session=session, user_id=str(user.user_id),
            new_email="frank.new@x.com",
        )
    except SemanticError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_confirm_email_change_with_unknown_token_raises():
    """
    **Feature: 1-user-management (M2)**
    **Property: confirming with an unrecognized token raises
    SemanticError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    raised = False
    try:
        user_service.confirm_email_change(
            db_session=session, token="not-a-real-token",
        )
    except SemanticError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_confirm_email_change_rejects_expired_token():
    """
    **Feature: 1-user-management (M2)**
    **Property: a token whose row is past expires_at fails
    confirm with SemanticError and the row is dropped.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    user = _make_user(session=session, login="gary", email="gary@x.com")
    challenge = user_service.request_email_change(
        db_session=session, user_id=str(user.user_id),
        new_email="gary.new@x.com",
    )
    # Push the row's expires_at into the past directly via repository.
    import hashlib
    token_hash = hashlib.sha256(challenge.token.encode("ascii")).digest()
    row = user_repository.find_email_verification_by_token(
        db_session=session, token_hash=token_hash,
    )
    row.expires_at = datetime.now(tz=timezone.utc) - timedelta(hours=1)
    session.flush()
    session.commit()

    raised = False
    try:
        user_service.confirm_email_change(
            db_session=session, token=challenge.token,
        )
    except SemanticError:
        raised = True
    testbase.assert_equal(raised, True)
    follow_up = user_repository.find_email_verification_by_token(
        db_session=session, token_hash=token_hash,
    )
    testbase.assert_equal(follow_up, None)
    return


def test_update_profile_changes_display_and_emits():
    """
    **Feature: 1-user-management (M2)**
    **Property: update_profile changes display_name + timezone
    and emits USER_UPDATED.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=UserEventTopics.USER_UPDATED,
        subscriber=lambda e: received.append(e),
    )
    user = _make_user(session=session, login="hank", email="hank@x.com")
    user_service.update_profile(
        db_session=session, user_id=str(user.user_id),
        display_name="Hank Esq.", timezone_name="America/Los_Angeles",
    )
    refreshed = user_service.read_user(
        db_session=session, user_id=str(user.user_id),
    )
    testbase.assert_equal(refreshed.display_name, "Hank Esq.")
    testbase.assert_equal(refreshed.timezone, "America/Los_Angeles")
    profile_emits = [
        e for e in received if e.payload.get("field") == "profile"
    ]
    testbase.assert_equal(len(profile_emits), 1)
    return


# -------------------------------------
# Group CRUD + membership
# -------------------------------------

def test_create_group_persists_and_emits():
    """
    **Feature: 1-user-management (M2)**
    **Property: create_group persists, emits GROUP_CREATED,
    and surfaces the row via get_group with empty membership.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=UserEventTopics.GROUP_CREATED,
        subscriber=lambda e: received.append(e),
    )
    view = group_service.create_group(
        db_session=session, group_name="ops", description="Ops Group",
        actor_user_id=ACTOR_UUID,
    )
    testbase.assert_equal(view.group_name, "ops")
    testbase.assert_equal(view.member_user_ids, ())
    testbase.assert_equal(len(received), 1)
    return


def test_create_group_duplicate_raises():
    """
    **Feature: 1-user-management (M2)**
    **Property: creating a duplicate group_name raises
    GroupAlreadyExistsError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    group_service.create_group(
        db_session=session, group_name="dup",
    )
    raised = False
    try:
        group_service.create_group(
            db_session=session, group_name="dup",
        )
    except group_service.GroupAlreadyExistsError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_add_and_remove_user_from_group_emits_and_idempotent():
    """
    **Feature: 1-user-management (M2)**
    **Property: add/remove emit GROUP_MEMBERSHIP_CHANGED on
    the first transition and are idempotent on the second.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=UserEventTopics.GROUP_MEMBERSHIP_CHANGED,
        subscriber=lambda e: received.append(e),
    )
    user = _make_user(session=session, login="ivy", email="ivy@x.com")
    group = group_service.create_group(
        db_session=session, group_name="qa",
    )
    group_service.add_user_to_group(
        db_session=session, group_id=group.group_id,
        user_id=str(user.user_id),
    )
    group_service.add_user_to_group(
        db_session=session, group_id=group.group_id,
        user_id=str(user.user_id),
    )
    testbase.assert_equal(len(received), 1)
    group_service.remove_user_from_group(
        db_session=session, group_id=group.group_id,
        user_id=str(user.user_id),
    )
    group_service.remove_user_from_group(
        db_session=session, group_id=group.group_id,
        user_id=str(user.user_id),
    )
    testbase.assert_equal(len(received), 2)
    return


def test_add_user_to_unknown_group_raises():
    """
    **Feature: 1-user-management (M2)**
    **Property: add_user_to_group on a missing group_id raises
    GroupNotFoundError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    user = _make_user(session=session, login="jane", email="jane@x.com")
    raised = False
    try:
        group_service.add_user_to_group(
            db_session=session,
            group_id="00000000-0000-4000-8000-deadbeefdead",
            user_id=str(user.user_id),
        )
    except group_service.GroupNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_add_unknown_user_to_group_raises():
    """
    **Feature: 1-user-management (M2)**
    **Property: add_user_to_group on a missing user_id raises
    UserNotFoundError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    group = group_service.create_group(
        db_session=session, group_name="orphan",
    )
    raised = False
    try:
        group_service.add_user_to_group(
            db_session=session,
            group_id=group.group_id,
            user_id="00000000-0000-4000-8000-deadbeefdead",
        )
    except UserNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_delete_group_idempotent_and_emits():
    """
    **Feature: 1-user-management (M2)**
    **Property: delete_group emits GROUP_DELETED on the first
    transition and returns False on the second.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=UserEventTopics.GROUP_DELETED,
        subscriber=lambda e: received.append(e),
    )
    group = group_service.create_group(
        db_session=session, group_name="trash",
    )
    first = group_service.delete_group(
        db_session=session, group_id=group.group_id,
    )
    second = group_service.delete_group(
        db_session=session, group_id=group.group_id,
    )
    testbase.assert_equal(first, True)
    testbase.assert_equal(second, False)
    testbase.assert_equal(len(received), 1)
    return


def test_list_groups_for_user_returns_only_member_groups():
    """
    **Feature: 1-user-management (M2)**
    **Property: list_groups_for_user only returns groups the
    user is currently a member of.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    user = _make_user(session=session, login="kate", email="kate@x.com")
    g1 = group_service.create_group(db_session=session, group_name="A")
    g2 = group_service.create_group(db_session=session, group_name="B")
    group_service.create_group(db_session=session, group_name="C")
    group_service.add_user_to_group(
        db_session=session, group_id=g1.group_id,
        user_id=str(user.user_id),
    )
    group_service.add_user_to_group(
        db_session=session, group_id=g2.group_id,
        user_id=str(user.user_id),
    )
    groups = group_service.list_groups_for_user(
        db_session=session, user_id=str(user.user_id),
    )
    names = sorted(g.group_name for g in groups)
    testbase.assert_equal(names, ["A", "B"])
    return


# -------------------------------------
# Directory sync
# -------------------------------------

class _StubDirectorySource(UserDirectorySourceProtocol):
    """
        Test-only directory source. The stub class variable
        ``_records`` is populated by each test before the
        sync runs.
    """
    factory_protocol_name: str = "user_directory_source"
    protocol_schema_version: int = 1
    PRECEDENCE: int = 100

    SOURCE_NAME: str = "stubdir"
    USERS: List[ExternalUserRecord] = []
    GROUPS: List[ExternalGroupRecord] = []

    @classmethod
    def source_name(cls) -> str:
        return cls.SOURCE_NAME

    @classmethod
    def iter_user_records(cls) -> Iterator[ExternalUserRecord]:
        return iter(cls.USERS)

    @classmethod
    def iter_group_records(cls) -> Iterator[ExternalGroupRecord]:
        return iter(cls.GROUPS)


def test_run_directory_sync_creates_updates_and_deactivates():
    """
    **Feature: 1-user-management (M2)**
    **Property: a sync against a stub source creates new
    rows, updates display_name on a changed record, and
    deactivates rows that vanished from the source.**
    """
    _prepare_runtime()
    register_factory_implementation(implementation=_StubDirectorySource)
    try:
        _engine, session = build_in_memory_session()

        # Seed pre-existing source-owned rows.
        existing_alpha = user_service.create_user(
            db_session=session,
            login_name="alpha", primary_email="alpha@x.com",
            display_name="alpha", timezone="UTC",
            provisioning_source=_StubDirectorySource.SOURCE_NAME,
            external_id="ext-alpha", actor_user_id=ACTOR_UUID,
        )
        existing_gone = user_service.create_user(
            db_session=session,
            login_name="gone", primary_email="gone@x.com",
            display_name="gone", timezone="UTC",
            provisioning_source=_StubDirectorySource.SOURCE_NAME,
            external_id="ext-gone", actor_user_id=ACTOR_UUID,
        )

        _StubDirectorySource.USERS = [
            ExternalUserRecord(
                external_id="ext-alpha", login_name="alpha",
                primary_email="alpha@x.com",
                display_name="Alpha v2", timezone="UTC", is_active=True,
            ),
            ExternalUserRecord(
                external_id="ext-beta", login_name="beta",
                primary_email="beta@x.com",
                display_name="Beta", timezone="UTC", is_active=True,
            ),
        ]
        _StubDirectorySource.GROUPS = []

        report = directory_sync.run_directory_sync(
            db_session=session,
            source_name=_StubDirectorySource.SOURCE_NAME,
            actor_user_id=ACTOR_UUID,
        )
        testbase.assert_equal(sorted(report.users_created), ["ext-beta"])
        testbase.assert_equal(sorted(report.users_updated), ["ext-alpha"])
        testbase.assert_equal(sorted(report.users_deactivated), ["ext-gone"])
        gone_refreshed = user_service.read_user(
            db_session=session, user_id=str(existing_gone.user_id),
        )
        testbase.assert_equal(gone_refreshed.status, UserStatus.DEACTIVATED)
        alpha_refreshed = user_service.read_user(
            db_session=session, user_id=str(existing_alpha.user_id),
        )
        testbase.assert_equal(alpha_refreshed.display_name, "Alpha v2")
    finally:
        _StubDirectorySource.USERS = []
        _StubDirectorySource.GROUPS = []
        unregister_factory_implementation(
            implementation=_StubDirectorySource,
        )
    return


def test_run_directory_sync_creates_groups_and_membership():
    """
    **Feature: 1-user-management (M2)**
    **Property: a sync that includes a group record creates
    the group and reconciles its membership against
    member_external_ids.**
    """
    _prepare_runtime()
    register_factory_implementation(implementation=_StubDirectorySource)
    try:
        _engine, session = build_in_memory_session()
        _StubDirectorySource.USERS = [
            ExternalUserRecord(
                external_id="ext-1", login_name="user1",
                primary_email="u1@x.com",
                display_name="User1", timezone="UTC", is_active=True,
            ),
            ExternalUserRecord(
                external_id="ext-2", login_name="user2",
                primary_email="u2@x.com",
                display_name="User2", timezone="UTC", is_active=True,
            ),
        ]
        _StubDirectorySource.GROUPS = [
            ExternalGroupRecord(
                external_id="g-1", group_name="ops-stub",
                description="Ops",
                member_external_ids=("ext-1", "ext-2"),
            ),
        ]
        report = directory_sync.run_directory_sync(
            db_session=session,
            source_name=_StubDirectorySource.SOURCE_NAME,
        )
        testbase.assert_equal(sorted(report.users_created), ["ext-1", "ext-2"])
        testbase.assert_equal(report.groups_created, ("ops-stub",))
        testbase.assert_equal(report.groups_membership_changed, ("ops-stub",))

        groups = group_service.list_groups(db_session=session)
        ops = [g for g in groups if g.group_name == "ops-stub"][0]
        testbase.assert_equal(len(ops.member_user_ids), 2)
    finally:
        _StubDirectorySource.USERS = []
        _StubDirectorySource.GROUPS = []
        unregister_factory_implementation(
            implementation=_StubDirectorySource,
        )
    return


def test_run_directory_sync_rejects_duplicate_logins():
    """
    **Feature: 1-user-management (M2)**
    **Property: two source records with the same login_name
    surface as DirectoryCollisionError.**
    """
    _prepare_runtime()
    register_factory_implementation(implementation=_StubDirectorySource)
    try:
        _engine, session = build_in_memory_session()
        _StubDirectorySource.USERS = [
            ExternalUserRecord(
                external_id="ext-1", login_name="dup",
                primary_email="u1@x.com",
                display_name="A", timezone="UTC", is_active=True,
            ),
            ExternalUserRecord(
                external_id="ext-2", login_name="dup",
                primary_email="u2@x.com",
                display_name="B", timezone="UTC", is_active=True,
            ),
        ]
        _StubDirectorySource.GROUPS = []
        raised = False
        try:
            directory_sync.run_directory_sync(
                db_session=session,
                source_name=_StubDirectorySource.SOURCE_NAME,
            )
        except DirectoryCollisionError:
            raised = True
        testbase.assert_equal(raised, True)
    finally:
        _StubDirectorySource.USERS = []
        _StubDirectorySource.GROUPS = []
        unregister_factory_implementation(
            implementation=_StubDirectorySource,
        )
    return


def test_run_directory_sync_unknown_source_raises():
    """
    **Feature: 1-user-management (M2)**
    **Property: a source name with no registered factory raises
    ValueError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    raised = False
    try:
        directory_sync.run_directory_sync(
            db_session=session, source_name="nope-not-real",
        )
    except ValueError:
        raised = True
    testbase.assert_equal(raised, True)
    return
