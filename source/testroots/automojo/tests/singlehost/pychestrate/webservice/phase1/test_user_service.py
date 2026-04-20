"""
.. module:: test_user_service
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for 1-user-management user_service.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo import testbase

from automojo.errors.exceptions import SemanticError

from automojo.pychestrate.webservice.identity.users import user_service
from automojo.pychestrate.webservice.identity.users.exceptions import (
    UserAlreadyExistsError,
    UserNotFoundError,
)
from automojo.pychestrate.webservice.messaging.event_bus import (
    EntityEvent,
    subscribe,
)

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
    reset_phase1_runtime,
)


def test_create_user_round_trip_and_event():
    """
    **Feature: 1-user-management**
    **Property: create_user round-trips through read_user and publishes
    entity.user.created after commit.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()

    received = []
    subscribe(
        topic="entity.user.created",
        subscriber=lambda evt: received.append(evt),
    )

    created = user_service.create_user(
        db_session=session,
        login_name="alice",
        primary_email="alice@example.com",
        display_name="Alice",
        timezone="UTC",
        provisioning_source="local",
        external_id=None,
        actor_user_id=None,
    )

    fetched = user_service.read_user(db_session=session, user_id=created.user_id)

    testbase.assert_equal(fetched.login_name, "alice")
    testbase.assert_equal(fetched.primary_email, "alice@example.com")
    testbase.assert_equal(len(received), 1)
    testbase.assert_equal(received[0].topic, "entity.user.created")
    testbase.assert_equal(received[0].payload["login_name"], "alice")
    return


def test_create_user_duplicate_login_raises():
    """
    **Feature: 1-user-management**
    **Property: create_user with an existing login_name raises
    UserAlreadyExistsError with a structured multi-line message.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()

    user_service.create_user(
        db_session=session,
        login_name="bob",
        primary_email="bob@example.com",
        display_name="Bob",
        timezone="UTC",
        provisioning_source="local",
        external_id=None,
        actor_user_id=None,
    )

    raised = False
    try:
        user_service.create_user(
            db_session=session,
            login_name="bob",
            primary_email="bob2@example.com",
            display_name="Bob",
            timezone="UTC",
            provisioning_source="local",
            external_id=None,
            actor_user_id=None,
        )
    except UserAlreadyExistsError as xcpt:
        raised = True
        testbase.assert_equal("LOGIN_NAME: bob" in str(xcpt), True)

    testbase.assert_equal(raised, True)
    return


def test_create_user_duplicate_email_raises():
    """
    **Feature: 1-user-management**
    **Property: create_user with an existing email raises UserAlreadyExistsError.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()

    user_service.create_user(
        db_session=session,
        login_name="carol",
        primary_email="shared@example.com",
        display_name="Carol",
        timezone="UTC",
        provisioning_source="local",
        external_id=None,
        actor_user_id=None,
    )

    raised = False
    try:
        user_service.create_user(
            db_session=session,
            login_name="dave",
            primary_email="shared@example.com",
            display_name="Dave",
            timezone="UTC",
            provisioning_source="local",
            external_id=None,
            actor_user_id=None,
        )
    except UserAlreadyExistsError:
        raised = True

    testbase.assert_equal(raised, True)
    return


def test_create_user_empty_login_raises_semantic_error():
    """
    **Feature: 1-user-management**
    **Property: create_user with empty login_name raises SemanticError.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()

    raised = False
    try:
        user_service.create_user(
            db_session=session,
            login_name="   ",
            primary_email="eve@example.com",
            display_name="Eve",
            timezone="UTC",
            provisioning_source="local",
            external_id=None,
            actor_user_id=None,
        )
    except SemanticError:
        raised = True

    testbase.assert_equal(raised, True)
    return


def test_read_user_unknown_raises_not_found():
    """
    **Feature: 1-user-management**
    **Property: read_user with an unknown id raises UserNotFoundError.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()

    raised = False
    try:
        user_service.read_user(
            db_session=session,
            user_id="00000000-0000-0000-0000-000000000000",
        )
    except UserNotFoundError:
        raised = True

    testbase.assert_equal(raised, True)
    return


def test_rolled_back_transaction_does_not_publish():
    """
    **Feature: 0-message-bus (stub) + 1-user-management**
    **Property: Buffered events are dropped on rollback.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()

    received = []
    subscribe(
        topic="entity.user.created",
        subscriber=lambda evt: received.append(evt),
    )

    # Create a row but roll back the transaction directly instead of letting
    # create_user commit. We imitate the outbox flow by inserting an event
    # ourselves via enqueue_event and then calling rollback.
    from automojo.pychestrate.webservice.messaging.outbox import enqueue_event

    enqueue_event(
        db_session=session,
        event=EntityEvent(
            topic="entity.user.created",
            payload={"user_id": "x"},
            source_event_id="rollback-test",
        ),
    )
    session.rollback()

    testbase.assert_equal(len(received), 0)
    return
