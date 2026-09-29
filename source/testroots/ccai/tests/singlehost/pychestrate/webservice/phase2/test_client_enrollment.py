"""
.. module:: test_client_enrollment
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for 3-client-enrollment M1 service surface.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime, timedelta, timezone

from ccai import testbase

from ccai.pychestrate.core.defaults import new_uuid

from ccai.pychestrate.webservice.clients.enrollment.factories.identity_verifier import (
    EnrollmentPayload,
)
from ccai.pychestrate.webservice.clients.enrollment.service import (
    issue_enrollment_token,
    list_enrollment_tokens,
    redeem_enrollment_token,
    revoke_client,
    revoke_enrollment_token,
)
from ccai.pychestrate.webservice.clients.enums import (
    ClientStatus,
    RevocationReason,
    TokenStatus,
)
from ccai.pychestrate.webservice.clients.exceptions import (
    ClientNotFoundError,
    EnrollmentRejectedError,
    EnrollmentTokenInvalidError,
    EnrollmentTokenNotFoundError,
)
from ccai.pychestrate.webservice.clients.models import (
    Client,
    ClientRevocation,
    EnrollmentToken,
)
from ccai.pychestrate.webservice.clients.registry.service import (
    get_client,
)
from ccai.pychestrate.webservice.messaging.event_bus import subscribe
from ccai.pychestrate.webservice.secrets.secret_bytes import SecretBytes
from ccai.pychestrate.webservice.security.auth.pepper_loader import (
    reset_active_pepper_for_testing,
    set_active_pepper,
)

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
    reset_phase1_runtime,
)


def _install_pepper() -> None:
    reset_active_pepper_for_testing()
    set_active_pepper(pepper=SecretBytes(b"phase2-enrollment-test-pepper"))
    return


def test_issue_and_list_tokens():
    """
    **Feature: 3-client-enrollment (M1)**
    **Property: issue_enrollment_token persists a PENDING row,
    returns a one-time secret, and publishes entity.client.token_issued.**
    """
    reset_phase1_runtime()
    _install_pepper()
    _engine, session = build_in_memory_session()

    received = []
    subscribe(topic="entity.client.token_issued", subscriber=lambda e: received.append(e))

    project_id = new_uuid()
    issued = issue_enrollment_token(
        db_session=session, project_id=project_id, pod_name="enroll-pod",
        ttl_seconds=300, one_shot=True, issued_by=None,
    )
    testbase.assert_equal(isinstance(issued.secret, str), True)
    testbase.assert_equal(len(issued.secret) >= 32, True)

    tokens = list_enrollment_tokens(db_session=session, project_id=project_id)
    testbase.assert_equal(len(tokens), 1)
    testbase.assert_equal(tokens[0].status, TokenStatus.PENDING)
    testbase.assert_equal(tokens[0].pod_name, "enroll-pod")
    testbase.assert_equal(len(received), 1)
    return


def test_issue_token_ttl_capped():
    """
    **Feature: 3-client-enrollment (M1)**
    **Property: ttl_seconds above the 86400 cap is clamped.**
    """
    reset_phase1_runtime()
    _install_pepper()
    _engine, session = build_in_memory_session()

    project_id = new_uuid()
    issued = issue_enrollment_token(
        db_session=session, project_id=project_id, pod_name="cap-pod",
        ttl_seconds=999_999, one_shot=True, issued_by=None,
    )

    row = (
        session.query(EnrollmentToken)
        .filter(EnrollmentToken.token_id == issued.token_id)
        .first()
    )
    testbase.assert_equal(row is not None, True)
    delta = row.expires_at - row.issued_at
    testbase.assert_equal(delta.total_seconds() <= 86400 + 5, True)
    return


def test_redeem_happy_path():
    """
    **Feature: 3-client-enrollment + 3-client-registry (M1)**
    **Property: redeem_enrollment_token verifies the secret, runs the
    identity verifier, materializes the client, returns a bearer token,
    and publishes entity.client.enrolled.**
    """
    reset_phase1_runtime()
    _install_pepper()
    _engine, session = build_in_memory_session()

    received = []
    subscribe(topic="entity.client.enrolled", subscriber=lambda e: received.append(e))

    project_id = new_uuid()
    issued = issue_enrollment_token(
        db_session=session, project_id=project_id, pod_name="happy-pod",
        ttl_seconds=300, one_shot=True, issued_by=None,
    )

    payload = EnrollmentPayload(
        pod_name="happy-pod", agent_version="0.1.0",
        transport_name="http", extras={},
    )
    result = redeem_enrollment_token(
        db_session=session, secret=issued.secret, payload=payload,
    )

    testbase.assert_equal(len(result.bearer_token) > 0, True)
    testbase.assert_equal(result.project_id, project_id)
    testbase.assert_equal(result.pod_name, "happy-pod")

    client_view = get_client(db_session=session, client_id=result.client_id)
    testbase.assert_equal(client_view.status, ClientStatus.ACTIVE)

    token_view = list_enrollment_tokens(db_session=session, project_id=project_id)
    testbase.assert_equal(token_view[0].status, TokenStatus.REDEEMED)
    testbase.assert_equal(len(received), 1)
    return


def test_redeem_wrong_secret_raises():
    """
    **Feature: 3-client-enrollment (M1)**
    **Property: A random-looking secret that matches no token row raises
    EnrollmentTokenNotFoundError, distinguishing it from the
    EnrollmentTokenInvalidError raised when the secret matches a row in
    a non-redeemable state.**
    """
    reset_phase1_runtime()
    _install_pepper()
    _engine, session = build_in_memory_session()

    project_id = new_uuid()
    issue_enrollment_token(
        db_session=session, project_id=project_id, pod_name="bogus-pod",
        ttl_seconds=300, one_shot=True, issued_by=None,
    )

    raised = False
    try:
        redeem_enrollment_token(
            db_session=session, secret="this-is-not-the-real-secret-12345",
            payload=EnrollmentPayload(
                pod_name="bogus-pod", agent_version=None,
                transport_name=None, extras={},
            ),
        )
    except EnrollmentTokenNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_redeem_pod_name_mismatch_rejected():
    """
    **Feature: 3-client-enrollment (M1)**
    **Property: ScopeIdentityVerifier rejects when the inbound pod_name
    does not match the token scope; the service raises EnrollmentRejectedError
    and publishes entity.client.enroll_rejected.**
    """
    reset_phase1_runtime()
    _install_pepper()
    _engine, session = build_in_memory_session()

    rejected_events = []
    subscribe(topic="entity.client.enroll_rejected", subscriber=lambda e: rejected_events.append(e))

    project_id = new_uuid()
    issued = issue_enrollment_token(
        db_session=session, project_id=project_id, pod_name="expected-pod",
        ttl_seconds=300, one_shot=True, issued_by=None,
    )

    raised = False
    try:
        redeem_enrollment_token(
            db_session=session, secret=issued.secret,
            payload=EnrollmentPayload(
                pod_name="WRONG-pod", agent_version=None,
                transport_name=None, extras={},
            ),
        )
    except EnrollmentRejectedError:
        raised = True
    testbase.assert_equal(raised, True)
    testbase.assert_equal(len(rejected_events), 1)
    testbase.assert_equal(rejected_events[0].payload["reason"], "pod_name_mismatch")
    return


def test_a_wrong_pod_name_is_told_which_name_the_token_expects_and_the_token_still_works():
    """
    **Feature: 3-client-enrollment (E2E-30)**
    **Property: the rejection for a pod name other than the token's carries
    ``EXPECTED_POD_NAME`` and a hint to enroll again with exactly that name;
    the rejection does not spend the token, so redeeming it with the right
    name then succeeds.**
    """
    reset_phase1_runtime()
    _install_pepper()
    _engine, session = build_in_memory_session()

    project_id = new_uuid()
    issued = issue_enrollment_token(
        db_session=session, project_id=project_id, pod_name="expected-pod",
        ttl_seconds=300, one_shot=True, issued_by=None,
    )

    message = ""
    try:
        redeem_enrollment_token(
            db_session=session, secret=issued.secret,
            payload=EnrollmentPayload(pod_name="WRONG-pod", agent_version=None, transport_name=None, extras={}),
        )
    except EnrollmentRejectedError as rejection:
        message = str(rejection)
    result = redeem_enrollment_token(
        db_session=session, secret=issued.secret,
        payload=EnrollmentPayload(pod_name="expected-pod", agent_version=None, transport_name=None, extras={}),
    )

    testbase.assert_equal(
        ("REASON: pod_name_mismatch" in message, "EXPECTED_POD_NAME: expected-pod" in message,
         "enroll again with exactly that name" in message, "WRONG-pod" in message, result.pod_name),
        (True, True, True, False, "expected-pod"),
    )
    return


def test_redeem_expired_token_rejected():
    """
    **Feature: 3-client-enrollment (M1)**
    **Property: A token whose expires_at has passed is swept to EXPIRED
    and subsequent redemption raises EnrollmentTokenInvalidError (the
    secret still matches a row, just not a PENDING one).**
    """
    reset_phase1_runtime()
    _install_pepper()
    _engine, session = build_in_memory_session()

    project_id = new_uuid()
    issued = issue_enrollment_token(
        db_session=session, project_id=project_id, pod_name="exp-pod",
        ttl_seconds=1, one_shot=True, issued_by=None,
    )

    # Age the row by rewriting expires_at; avoids sleep in tests.
    row = (
        session.query(EnrollmentToken)
        .filter(EnrollmentToken.token_id == issued.token_id)
        .first()
    )
    row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=60)
    session.commit()

    raised = False
    try:
        redeem_enrollment_token(
            db_session=session, secret=issued.secret,
            payload=EnrollmentPayload(
                pod_name="exp-pod", agent_version=None,
                transport_name=None, extras={},
            ),
        )
    except EnrollmentTokenInvalidError:
        raised = True
    testbase.assert_equal(raised, True)

    tokens = list_enrollment_tokens(db_session=session, project_id=project_id)
    testbase.assert_equal(tokens[0].status, TokenStatus.EXPIRED)
    return


def test_one_shot_cannot_be_replayed():
    """
    **Feature: 3-client-enrollment (M1)**
    **Property: A one-shot token marks REDEEMED after first use; a
    replay raises EnrollmentTokenInvalidError.**
    """
    reset_phase1_runtime()
    _install_pepper()
    _engine, session = build_in_memory_session()

    project_id = new_uuid()
    issued = issue_enrollment_token(
        db_session=session, project_id=project_id, pod_name="once-pod",
        ttl_seconds=300, one_shot=True, issued_by=None,
    )
    payload = EnrollmentPayload(
        pod_name="once-pod", agent_version=None,
        transport_name=None, extras={},
    )
    redeem_enrollment_token(db_session=session, secret=issued.secret, payload=payload)

    raised = False
    try:
        redeem_enrollment_token(db_session=session, secret=issued.secret, payload=payload)
    except EnrollmentTokenInvalidError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_revoke_token_blocks_redemption():
    """
    **Feature: 3-client-enrollment (M1)**
    **Property: revoke_enrollment_token flips the row to REVOKED so
    redemption raises EnrollmentTokenInvalidError.**
    """
    reset_phase1_runtime()
    _install_pepper()
    _engine, session = build_in_memory_session()

    project_id = new_uuid()
    issued = issue_enrollment_token(
        db_session=session, project_id=project_id, pod_name="rev-pod",
        ttl_seconds=300, one_shot=True, issued_by=None,
    )
    revoke_enrollment_token(
        db_session=session, token_id=issued.token_id, actor_user_id=None,
    )

    raised = False
    try:
        redeem_enrollment_token(
            db_session=session, secret=issued.secret,
            payload=EnrollmentPayload(
                pod_name="rev-pod", agent_version=None,
                transport_name=None, extras={},
            ),
        )
    except EnrollmentTokenInvalidError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_revoke_client_records_revocation_and_flips_status():
    """
    **Feature: 3-client-enrollment (M1)**
    **Property: revoke_client creates a clients_client_revocations row,
    flips client status to REVOKED, and publishes entity.client.revoked.**
    """
    reset_phase1_runtime()
    _install_pepper()
    _engine, session = build_in_memory_session()

    received = []
    subscribe(topic="entity.client.revoked", subscriber=lambda e: received.append(e))

    project_id = new_uuid()
    issued = issue_enrollment_token(
        db_session=session, project_id=project_id, pod_name="revokee",
        ttl_seconds=300, one_shot=True, issued_by=None,
    )
    result = redeem_enrollment_token(
        db_session=session, secret=issued.secret,
        payload=EnrollmentPayload(
            pod_name="revokee", agent_version=None,
            transport_name=None, extras={},
        ),
    )

    revoke_client(
        db_session=session, client_id=result.client_id,
        reason=RevocationReason.COMPROMISED,
        revoked_by=None, note="unit-test revoke",
    )

    view = get_client(db_session=session, client_id=result.client_id)
    testbase.assert_equal(view.status, ClientStatus.REVOKED)

    rev_rows = (
        session.query(ClientRevocation)
        .filter(ClientRevocation.client_id == result.client_id)
        .all()
    )
    testbase.assert_equal(len(rev_rows), 1)
    testbase.assert_equal(rev_rows[0].reason, RevocationReason.COMPROMISED)
    testbase.assert_equal(rev_rows[0].note, "unit-test revoke")

    testbase.assert_equal(len(received), 1)
    testbase.assert_equal(received[0].payload["reason"], "COMPROMISED")
    return


def test_revoke_unknown_client_raises():
    """
    **Feature: 3-client-enrollment (M1)**
    **Property: revoke_client with an unknown client_id raises
    ClientNotFoundError.**
    """
    reset_phase1_runtime()
    _install_pepper()
    _engine, session = build_in_memory_session()

    raised = False
    try:
        revoke_client(
            db_session=session, client_id=new_uuid(),
            reason=RevocationReason.ADMIN_REQUEST,
            revoked_by=None, note="",
        )
    except ClientNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_revoke_unknown_token_raises():
    """
    **Feature: 3-client-enrollment (M1)**
    **Property: revoke_enrollment_token with unknown token_id raises
    EnrollmentTokenNotFoundError.**
    """
    reset_phase1_runtime()
    _install_pepper()
    _engine, session = build_in_memory_session()

    raised = False
    try:
        revoke_enrollment_token(
            db_session=session, token_id=new_uuid(), actor_user_id=None,
        )
    except EnrollmentTokenNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return
