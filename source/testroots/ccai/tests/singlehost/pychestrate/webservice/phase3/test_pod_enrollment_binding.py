"""
.. module:: test_pod_enrollment_binding
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests that an enrolled client is registered on its pod and
               so becomes eligible for dispatch (ORG-F01).

.. moduleauthor:: Code Craft AI LLC

Before this change nothing in the product created a
:class:`PodRegistration`: ``register_static_pod`` had no production
caller, so a healthy, heartbeating client never became a dispatch
candidate and every trigger answered "no eligible pod". Redeeming an
enrollment token now registers the client on the pod the token names.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Tuple

from ccai import testbase

from ccai.pychestrate.core.defaults import new_uuid

from ccai.pychestrate.webservice.clients.enrollment.factories.identity_verifier import (
    EnrollmentPayload,
)
from ccai.pychestrate.webservice.clients.enrollment.service import (
    issue_enrollment_token,
    redeem_enrollment_token,
    revoke_client,
)
from ccai.pychestrate.webservice.clients.enums import RevocationReason
from ccai.pychestrate.webservice.clients.exceptions import ClientAlreadyExistsError
from ccai.pychestrate.webservice.clients.registry.service import get_client_by_scope
from ccai.pychestrate.webservice.orchestration.rpa.candidates import (
    resolve_dispatch_candidates,
)
from ccai.pychestrate.webservice.pods import definitions_service
from ccai.pychestrate.webservice.pods import static_service
from ccai.pychestrate.webservice.pods.models import (
    PodDefinition,
    PodRegistration,
    RegistrationState,
)
from ccai.pychestrate.webservice.secrets.secret_bytes import SecretBytes
from ccai.pychestrate.webservice.security.auth.pepper_loader import (
    set_active_pepper,
)

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
)
from ccai.tests.singlehost.pychestrate.webservice.phase3.fixtures import (
    reset_phase3_runtime,
)


def _enroll(*, session, project_id: str, pod_name: str) -> str:
    """
        Issue a token for ``(project_id, pod_name)`` and redeem it
        bearer-only (no CSR, so no CA is needed).

        :returns: The enrolled client id.
    """
    issued = _mint(session=session, project_id=project_id, pod_name=pod_name)
    rtnval = _redeem(session=session, secret=issued.secret, pod_name=pod_name)
    return rtnval


def _mint(*, session, project_id: str, pod_name: str):
    """
        Issue a one-shot token for ``(project_id, pod_name)``.

        :returns: The :class:`IssuedEnrollmentToken`.
    """
    rtnval = issue_enrollment_token(
        db_session=session,
        project_id=project_id,
        pod_name=pod_name,
        ttl_seconds=600,
        one_shot=True,
        issued_by=None,
    )
    return rtnval


def _redeem(*, session, secret: str, pod_name: str) -> str:
    """
        Redeem ``secret`` bearer-only (no CSR, so no CA is needed).

        :returns: The enrolled client id.
    """
    result = redeem_enrollment_token(
        db_session=session,
        secret=secret,
        payload=EnrollmentPayload(
            pod_name=pod_name, agent_version="0.1.0", transport_name="http-long-poll",
            extras={}, csr_pem=None,
        ),
    )
    rtnval = str(result.client_id)
    return rtnval


def _fresh_session() -> Tuple[object, object]:
    """
        Reset the Phase-3 runtime, install the pepper the token issuer
        hashes secrets with, and open an in-memory database.

        :returns: Tuple ``(engine, session)``.
    """
    reset_phase3_runtime()
    set_active_pepper(pepper=SecretBytes(b"phase3-pod-binding-test-pepper"))
    rtnval = build_in_memory_session()
    return rtnval


def _registered_rows(*, session, client_id: str):
    rtnval = (
        session.query(PodRegistration)
        .filter(PodRegistration.client_id == client_id)
        .filter(PodRegistration.state == RegistrationState.REGISTERED)
        .all()
    )
    return rtnval


def test_redeem_registers_the_client_on_the_pod_the_token_names():
    """
    **Feature: client enrollment binds the pod (ORG-F01)**
    **Property: after redemption the client holds exactly one REGISTERED
    registration, on the pod definition named by the token.**
    """
    _engine, session = _fresh_session()
    project_id = new_uuid()
    client_id = _enroll(session=session, project_id=project_id, pod_name="lab-pod-a")

    rows = _registered_rows(session=session, client_id=client_id)
    definition = session.query(PodDefinition).filter(PodDefinition.pod_id == rows[0].pod_id).first()
    testbase.assert_equal(
        (len(rows), definition.pod_name, str(definition.project_id)),
        (1, "lab-pod-a", project_id),
    )
    return


def test_redeem_creates_an_empty_static_pod_for_an_undefined_pod_name():
    """
    **Feature: client enrollment binds the pod (ORG-F01)**
    **Property: when no pod definition carries the token's pod name, the
    redemption creates a static pod definition with no members.**
    """
    _engine, session = _fresh_session()
    project_id = new_uuid()
    _enroll(session=session, project_id=project_id, pod_name="new-pod")

    definitions = definitions_service.list_pod_definitions(db_session=session, project_id=project_id)
    version = definitions_service.read_pod_definition_version(
        db_session=session, pod_id=str(definitions[0].pod_id), version=1,
    )
    testbase.assert_equal(
        ([d.pod_name for d in definitions], version.spec_json),
        (["new-pod"], {"members": []}),
    )
    return


def test_redeem_reuses_an_existing_pod_definition():
    """
    **Feature: client enrollment binds the pod (ORG-F01)**
    **Property: when the operator already defined the pod, the client is
    registered on that definition and its declared members are recorded
    as the registration report.**
    """
    _engine, session = _fresh_session()
    project_id = new_uuid()
    members = [{"name": "host-a", "kind": "linux_host", "hostname": "a.example.com"}]
    definition = definitions_service.create_pod_definition(
        db_session=session, project_id=project_id, pod_name="defined-pod",
        spec={"members": members}, actor_user_id=None,
    )
    client_id = _enroll(session=session, project_id=project_id, pod_name="defined-pod")

    rows = _registered_rows(session=session, client_id=client_id)
    testbase.assert_equal(
        (str(rows[0].pod_id), rows[0].report_json.get("members")),
        (str(definition.pod_id), members),
    )
    return


def test_enrolled_client_is_a_dispatch_candidate_for_its_project():
    """
    **Feature: client enrollment binds the pod (ORG-F01)**
    **Property: RPA candidate resolution for the token's project returns
    the enrolled client on its pod (it returned nothing before).**
    """
    _engine, session = _fresh_session()
    project_id = new_uuid()
    client_id = _enroll(session=session, project_id=project_id, pod_name="candidate-pod")

    candidates = resolve_dispatch_candidates(db_session=session, project_id=project_id)
    rows = _registered_rows(session=session, client_id=client_id)
    testbase.assert_equal(
        [(c.client_id, c.pod_id) for c in candidates],
        [(client_id, str(rows[0].pod_id))],
    )
    return


def test_enrolled_client_is_a_dispatch_candidate_for_a_ui_project_spec():
    """
    **Feature: client enrollment binds the pod (ORG-F01)**
    **Property: a specification in a consumer-UI project (integer id)
    also finds the enrolled client -- the deployment-wide candidate tier
    sees the new registration.**
    """
    _engine, session = _fresh_session()
    client_id = _enroll(session=session, project_id=new_uuid(), pod_name="ui-project-pod")

    candidates = resolve_dispatch_candidates(db_session=session, project_id="1")
    testbase.assert_equal([c.client_id for c in candidates], [client_id])
    return


def test_binding_a_new_client_deregisters_the_previous_client():
    """
    **Feature: client enrollment binds the pod (ORG-F01)**
    **Property: a pod has one client -- binding a second client to the
    same pod deregisters the first client's registration.**
    """
    _engine, session = _fresh_session()
    project_id = new_uuid()
    first = static_service.bind_enrolled_client(
        db_session=session, project_id=project_id, pod_name="shared-pod", client_id=new_uuid(),
    )
    session.commit()
    static_service.bind_enrolled_client(
        db_session=session, project_id=project_id, pod_name="shared-pod", client_id=new_uuid(),
    )
    session.commit()

    session.refresh(first)
    testbase.assert_equal(first.state, RegistrationState.DEREGISTERED)
    return


def test_binding_the_same_client_twice_keeps_one_registration():
    """
    **Feature: client enrollment binds the pod (ORG-F01)**
    **Property: binding a client that already holds the pod returns its
    existing registration instead of adding a second one.**
    """
    _engine, session = _fresh_session()
    project_id = new_uuid()
    client_id = new_uuid()
    first = static_service.bind_enrolled_client(
        db_session=session, project_id=project_id, pod_name="same-pod", client_id=client_id,
    )
    second = static_service.bind_enrolled_client(
        db_session=session, project_id=project_id, pod_name="same-pod", client_id=client_id,
    )
    session.commit()

    testbase.assert_equal(
        (str(second.registration_id), len(_registered_rows(session=session, client_id=client_id))),
        (str(first.registration_id), 1),
    )
    return


def test_a_revoked_client_gives_up_its_pod_name_to_a_replacement():
    """
    **Feature: re-enrolling a replaced pod (E2E-25)**
    **Property: while a client holds a pod name, a token minted for it
    carries a warning and redeeming it is refused without consuming the
    token; revoking the client removes it from dispatch, and that token
    then enrolls a replacement that takes over the pod.**
    """
    _engine, session = _fresh_session()
    project_id = new_uuid()
    original = _enroll(session=session, project_id=project_id, pod_name="lab-pod-r")

    issued = _mint(session=session, project_id=project_id, pod_name="lab-pod-r")
    testbase.assert_equal(len(issued.warnings), 1)
    testbase.assert_equal(original in issued.warnings[0], True)

    refused = False
    try:
        _redeem(session=session, secret=issued.secret, pod_name="lab-pod-r")
    except ClientAlreadyExistsError as xcpt:
        refused = True
        testbase.assert_equal(original in str(xcpt), True)
    testbase.assert_equal(refused, True)

    revoke_client(
        db_session=session, client_id=original,
        reason=RevocationReason.DECOMMISSIONED, revoked_by=None,
    )
    # Revocation deregisters the client, so it is no longer a dispatch
    # candidate while the pod waits for its replacement.
    testbase.assert_equal(
        (len(_registered_rows(session=session, client_id=original)),
         resolve_dispatch_candidates(db_session=session, project_id=project_id)),
        (0, []),
    )
    after_revoke = _mint(session=session, project_id=project_id, pod_name="lab-pod-r")
    testbase.assert_equal(after_revoke.warnings, ())

    replacement = _redeem(session=session, secret=issued.secret, pod_name="lab-pod-r")
    holder = get_client_by_scope(db_session=session, project_id=project_id, pod_name="lab-pod-r")
    testbase.assert_equal(
        (replacement != original, str(holder.client_id),
         len(_registered_rows(session=session, client_id=replacement)),
         len(_registered_rows(session=session, client_id=original))),
        (True, replacement, 1, 0),
    )
    return
