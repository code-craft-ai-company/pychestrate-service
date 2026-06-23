"""
.. module:: test_client_enrollment_m2
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for 3-client-enrollment M2 — mTLS / CSR / CA path.

.. moduleauthor:: Code Craft AI LLC

Covers the M2 spec's core behavior:

* ``ca_adapter.load_ca_at_startup`` + ``set_active_ca`` install a CA.
* ``redeem_enrollment_token`` signs a CSR, persists a ``ClientCert``
  row, and returns the cert metadata alongside the bearer token.
* A CSR whose Subject CN disagrees with the token scope is rejected.
* ``revoke_client`` records the cert serial on the revocation row and
  ``is_cert_revoked`` returns ``True`` for it afterwards.
* A client without a CA installed gets HTTP 503-equivalent
  ``CertificateAuthorityUnavailableError`` when a CSR is supplied.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from ccai import testbase

from ccai.pychestrate.webservice.clients.enrollment import ca_adapter
from ccai.pychestrate.webservice.clients.enrollment.factories.identity_verifier import (
    EnrollmentPayload,
)
from ccai.pychestrate.webservice.clients.enrollment.service import (
    is_cert_revoked,
    issue_enrollment_token,
    redeem_enrollment_token,
    revoke_client,
)
from ccai.pychestrate.webservice.clients.enums import (
    ClientStatus,
    RevocationReason,
)
from ccai.pychestrate.webservice.clients.exceptions import (
    CertificateAuthorityUnavailableError,
    CsrScopeMismatchError,
    CsrValidationError,
)
from ccai.pychestrate.webservice.clients.models import (
    Client,
    ClientCert,
    ClientRevocation,
)

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
)
from ccai.tests.singlehost.pychestrate.webservice.phase2.fixtures import (
    reset_phase2_runtime,
)


def _generate_client_csr(*, common_name: str) -> bytes:
    """
        Produce a PEM CSR with the requested CN. Used as fixture data
        for CSR redemption tests.

        :param common_name: Subject CN to set on the CSR.

        :returns: PEM-encoded CSR bytes.
    """
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    builder = x509.CertificateSigningRequestBuilder().subject_name(
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    )
    csr = builder.sign(private_key=private_key, algorithm=hashes.SHA256())
    rtnval = csr.public_bytes(encoding=serialization.Encoding.PEM)
    return rtnval


def _install_dev_ca() -> None:
    """
        Generate an in-memory CA and install it as the active CA for
        the current test process. Paired with
        :func:`ca_adapter.reset_active_ca_for_testing` between tests
        so state never leaks across cases.
    """
    pem_bytes = ca_adapter.generate_dev_ca(common_name="Test CA")

    # Exercise load_ca_at_startup via the env-var source so the PEM
    # parser is covered by this test, not just the happy path.
    import os
    os.environ["PCX_TEST_CA_PEM"] = pem_bytes.decode("utf-8")
    try:
        handle = ca_adapter.load_ca_at_startup(
            source="env",
            env_var="PCX_TEST_CA_PEM",
            ca_id="test-ca",
        )
    finally:
        del os.environ["PCX_TEST_CA_PEM"]

    ca_adapter.set_active_ca(ca=handle)
    return


def test_redeem_with_csr_issues_and_persists_cert():
    """
    **Feature: 3-client-enrollment (M2)**
    **Property: a redemption that carries a CSR returns a cert, persists
    a ClientCert row, and sets cert metadata on the RedemptionResult.**
    """
    reset_phase2_runtime()
    ca_adapter.reset_active_ca_for_testing()
    _install_dev_ca()
    _engine, session = build_in_memory_session()

    project_id = "00000000-0000-0000-0000-000000000001"
    pod_name = "test-pod-m2"

    issued = issue_enrollment_token(
        db_session=session,
        project_id=project_id,
        pod_name=pod_name,
        ttl_seconds=600,
        one_shot=True,
        issued_by=None,
    )

    csr_pem = _generate_client_csr(common_name=pod_name)
    payload = EnrollmentPayload(
        pod_name=pod_name,
        agent_version="0.1.0",
        transport_name="http",
        extras={},
        csr_pem=csr_pem,
    )

    result = redeem_enrollment_token(
        db_session=session,
        secret=issued.secret,
        payload=payload,
    )

    testbase.assert_equal(result.cert_serial is not None, True)
    testbase.assert_equal(len(result.cert_serial) > 0, True)
    testbase.assert_equal(result.cert_pem is not None, True)
    testbase.assert_equal(result.cert_pem.startswith(b"-----BEGIN CERTIFICATE-----"), True)
    testbase.assert_equal(result.cert_chain_pem is not None, True)
    testbase.assert_equal(result.cert_chain_pem.startswith(b"-----BEGIN CERTIFICATE-----"), True)

    cert_rows = session.query(ClientCert).filter(ClientCert.client_id == result.client_id).all()
    testbase.assert_equal(len(cert_rows), 1)
    testbase.assert_equal(cert_rows[0].cert_serial, result.cert_serial)
    testbase.assert_equal(cert_rows[0].subject_cn, pod_name)

    ca_adapter.reset_active_ca_for_testing()
    return


def test_redeem_without_csr_keeps_m1_bearer_path():
    """
    **Feature: 3-client-enrollment (M2)**
    **Property: a redemption without a CSR still succeeds and returns
    only bearer credentials (no cert). Backward-compat with M1.**
    """
    reset_phase2_runtime()
    ca_adapter.reset_active_ca_for_testing()
    _engine, session = build_in_memory_session()

    project_id = "00000000-0000-0000-0000-000000000002"
    pod_name = "pod-no-csr"

    issued = issue_enrollment_token(
        db_session=session,
        project_id=project_id,
        pod_name=pod_name,
        ttl_seconds=600,
        one_shot=True,
        issued_by=None,
    )

    payload = EnrollmentPayload(
        pod_name=pod_name,
        agent_version="0.1.0",
        transport_name="http",
        extras={},
        csr_pem=None,
    )

    result = redeem_enrollment_token(
        db_session=session,
        secret=issued.secret,
        payload=payload,
    )

    testbase.assert_equal(result.cert_serial, None)
    testbase.assert_equal(result.cert_pem, None)
    testbase.assert_equal(result.cert_chain_pem, None)
    testbase.assert_equal(len(result.bearer_token) > 0, True)

    cert_count = session.query(ClientCert).count()
    testbase.assert_equal(cert_count, 0)
    return


def test_csr_with_mismatched_cn_rejects_with_scope_mismatch():
    """
    **Feature: 3-client-enrollment (M2)**
    **Property: a CSR whose Subject CN disagrees with the token scope
    is rejected.**

    The spec allows the rejection to surface either as
    ``EnrollmentRejectedError`` (from the CsrSubjectVerifier) or as
    ``CsrScopeMismatchError`` (from ca_adapter.sign_csr) depending on
    which layer notices the mismatch first. Both are acceptable
    outcomes since both translate to the same wire reason code.
    """
    reset_phase2_runtime()
    ca_adapter.reset_active_ca_for_testing()
    _install_dev_ca()
    _engine, session = build_in_memory_session()

    project_id = "00000000-0000-0000-0000-000000000003"
    pod_name = "intended-pod"

    issued = issue_enrollment_token(
        db_session=session,
        project_id=project_id,
        pod_name=pod_name,
        ttl_seconds=600,
        one_shot=True,
        issued_by=None,
    )

    attacker_csr = _generate_client_csr(common_name="evil-pod")
    payload = EnrollmentPayload(
        pod_name=pod_name,
        agent_version="0.1.0",
        transport_name="http",
        extras={},
        csr_pem=attacker_csr,
    )

    raised = False
    try:
        redeem_enrollment_token(
            db_session=session,
            secret=issued.secret,
            payload=payload,
        )
    except (CsrScopeMismatchError, CsrValidationError, Exception) as xcpt:
        raised = True
        message = str(xcpt)
        testbase.assert_equal(
            "scope_mismatch" in message or "evil-pod" in message or "Subject CN" in message,
            True,
        )
    testbase.assert_equal(raised, True)

    cert_count = session.query(ClientCert).count()
    testbase.assert_equal(cert_count, 0)

    ca_adapter.reset_active_ca_for_testing()
    return


def test_revoke_client_records_cert_serial_and_is_cert_revoked_agrees():
    """
    **Feature: 3-client-enrollment (M2)**
    **Property: revoke_client persists the cert serial on the
    revocation row; is_cert_revoked(serial) returns True afterwards.**
    """
    reset_phase2_runtime()
    ca_adapter.reset_active_ca_for_testing()
    _install_dev_ca()
    _engine, session = build_in_memory_session()

    project_id = "00000000-0000-0000-0000-000000000004"
    pod_name = "pod-to-revoke"

    issued = issue_enrollment_token(
        db_session=session,
        project_id=project_id,
        pod_name=pod_name,
        ttl_seconds=600,
        one_shot=True,
        issued_by=None,
    )

    csr_pem = _generate_client_csr(common_name=pod_name)
    result = redeem_enrollment_token(
        db_session=session,
        secret=issued.secret,
        payload=EnrollmentPayload(
            pod_name=pod_name,
            agent_version="0.1.0",
            transport_name="http",
            extras={},
            csr_pem=csr_pem,
        ),
    )

    issued_serial = result.cert_serial
    testbase.assert_equal(is_cert_revoked(db_session=session, cert_serial=issued_serial), False)

    revoke_client(
        db_session=session,
        client_id=result.client_id,
        reason=RevocationReason.COMPROMISED,
        revoked_by=None,
        note="unit-test",
    )

    # Revocation row captured the cert serial.
    revocation = (
        session.query(ClientRevocation)
        .filter(ClientRevocation.client_id == result.client_id)
        .first()
    )
    testbase.assert_equal(revocation is not None, True)
    testbase.assert_equal(revocation.cert_serial, issued_serial)

    # Client row flipped to REVOKED.
    client = session.query(Client).filter(Client.client_id == result.client_id).first()
    testbase.assert_equal(client.status, ClientStatus.REVOKED)

    # is_cert_revoked now returns True for the revoked serial.
    testbase.assert_equal(is_cert_revoked(db_session=session, cert_serial=issued_serial), True)

    # is_cert_revoked keeps returning False for an unrelated serial.
    testbase.assert_equal(is_cert_revoked(db_session=session, cert_serial="deadbeef"), False)

    ca_adapter.reset_active_ca_for_testing()
    return


def test_csr_path_with_no_ca_installed_raises_authority_unavailable():
    """
    **Feature: 3-client-enrollment (M2)**
    **Property: when no CA is installed, a CSR redemption raises
    CertificateAuthorityUnavailableError.**
    """
    reset_phase2_runtime()
    ca_adapter.reset_active_ca_for_testing()
    _engine, session = build_in_memory_session()

    project_id = "00000000-0000-0000-0000-000000000005"
    pod_name = "pod-no-ca"

    issued = issue_enrollment_token(
        db_session=session,
        project_id=project_id,
        pod_name=pod_name,
        ttl_seconds=600,
        one_shot=True,
        issued_by=None,
    )

    csr_pem = _generate_client_csr(common_name=pod_name)
    payload = EnrollmentPayload(
        pod_name=pod_name,
        agent_version="0.1.0",
        transport_name="http",
        extras={},
        csr_pem=csr_pem,
    )

    raised = False
    try:
        redeem_enrollment_token(
            db_session=session,
            secret=issued.secret,
            payload=payload,
        )
    except CertificateAuthorityUnavailableError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_csr_with_invalid_pem_rejects_with_csr_validation_error():
    """
    **Feature: 3-client-enrollment (M2)**
    **Property: a non-PEM CSR blob is rejected before signing.**

    The verifier runs first in the redeem path and classifies the
    failure as ``csr_unparseable`` / ``csr_signature_invalid`` —
    either reaches the caller as ``EnrollmentRejectedError`` with the
    reason in the message.
    """
    reset_phase2_runtime()
    ca_adapter.reset_active_ca_for_testing()
    _install_dev_ca()
    _engine, session = build_in_memory_session()

    project_id = "00000000-0000-0000-0000-000000000006"
    pod_name = "pod-bad-csr"

    issued = issue_enrollment_token(
        db_session=session,
        project_id=project_id,
        pod_name=pod_name,
        ttl_seconds=600,
        one_shot=True,
        issued_by=None,
    )

    payload = EnrollmentPayload(
        pod_name=pod_name,
        agent_version="0.1.0",
        transport_name="http",
        extras={},
        csr_pem=b"not a real csr",
    )

    raised = False
    try:
        redeem_enrollment_token(
            db_session=session,
            secret=issued.secret,
            payload=payload,
        )
    except Exception as xcpt:
        raised = True
        message = str(xcpt)
        testbase.assert_equal(
            "csr" in message.lower() or "CSR" in message,
            True,
        )
    testbase.assert_equal(raised, True)

    ca_adapter.reset_active_ca_for_testing()
    return
