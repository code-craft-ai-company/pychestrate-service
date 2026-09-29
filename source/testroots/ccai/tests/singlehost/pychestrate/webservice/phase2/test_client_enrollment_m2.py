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
* The issued certificate carries the client id as its identity (CN
  and ``urn:uuid:`` SAN) and is a TLS client certificate (E2E-04).
* A redemption that fails while signing writes nothing, so the pod
  name stays free and the same token can be redeemed again.
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
    EnrollmentRejectedError,
)
from ccai.pychestrate.webservice.clients.models import (
    Client,
    ClientCert,
    ClientRevocation,
)
from ccai.pychestrate.webservice.secrets.secret_bytes import SecretBytes
from ccai.pychestrate.webservice.security.auth.pepper_loader import (
    set_active_pepper,
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
    # The certificate identity is the client id, not the pod name the
    # CSR carried (E2E-04).
    testbase.assert_equal(cert_rows[0].subject_cn, result.client_id)

    ca_adapter.reset_active_ca_for_testing()
    return


def _install_token_pepper() -> None:
    """
        Install the password pepper the token issuer hashes secrets
        with, so these tests do not depend on an earlier module having
        installed one.
    """
    set_active_pepper(pepper=SecretBytes(b"phase2-enrollment-m2-test-pepper"))
    return


def _redeem_with_csr(*, pod_name: str, project_id: str):
    """
        Install a dev CA, issue a token for ``pod_name`` and redeem it
        with a matching CSR.

        :param pod_name: Pod the token is scoped to.
        :param project_id: Project the token is scoped to.

        :returns: Tuple ``(session, RedemptionResult, parsed issued
                  certificate)``.
    """
    reset_phase2_runtime()
    _install_token_pepper()
    ca_adapter.reset_active_ca_for_testing()
    _install_dev_ca()
    _engine, session = build_in_memory_session()

    issued = issue_enrollment_token(
        db_session=session,
        project_id=project_id,
        pod_name=pod_name,
        ttl_seconds=600,
        one_shot=True,
        issued_by=None,
    )
    result = redeem_enrollment_token(
        db_session=session,
        secret=issued.secret,
        payload=EnrollmentPayload(
            pod_name=pod_name,
            agent_version="0.1.0",
            transport_name="http",
            extras={},
            csr_pem=_generate_client_csr(common_name=pod_name),
        ),
    )
    certificate = x509.load_pem_x509_certificate(result.cert_pem)
    rtnval = (session, result, certificate)
    return rtnval


def test_issued_certificate_common_name_is_the_client_id():
    """
    **Feature: 3-client-enrollment (M2) -- one client identity (E2E-04)**
    **Property: the certificate issued at redemption has Subject CN equal
    to the assigned client id, which is what the pod routes compare with
    the client_id in their path -- not the pod name the CSR carried.**
    """
    _session, result, certificate = _redeem_with_csr(
        pod_name="cn-pod", project_id="00000000-0000-0000-0000-000000000011",
    )
    try:
        cn_values = [attr.value for attr in certificate.subject.get_attributes_for_oid(NameOID.COMMON_NAME)]
        testbase.assert_equal(cn_values, [result.client_id])
    finally:
        ca_adapter.reset_active_ca_for_testing()
    return


def test_issued_certificate_names_the_client_id_as_uuid_urn_san():
    """
    **Feature: 3-client-enrollment (M2) -- one client identity (E2E-04)**
    **Property: the issued certificate carries the client id as a
    ``urn:uuid:<client_id>`` URI subject alternative name.**
    """
    _session, result, certificate = _redeem_with_csr(
        pod_name="san-pod", project_id="00000000-0000-0000-0000-000000000012",
    )
    try:
        san = certificate.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        uris = san.get_values_for_type(x509.UniformResourceIdentifier)
        testbase.assert_equal(uris, ["urn:uuid:{}".format(result.client_id)])
    finally:
        ca_adapter.reset_active_ca_for_testing()
    return


def test_issued_certificate_is_a_tls_client_certificate():
    """
    **Feature: 3-client-enrollment (M2) -- one client identity (E2E-04)**
    **Property: the issued certificate is usable only as a TLS client
    certificate: extendedKeyUsage is clientAuth and basicConstraints
    forbids acting as a CA.**
    """
    _session, _result, certificate = _redeem_with_csr(
        pod_name="eku-pod", project_id="00000000-0000-0000-0000-000000000013",
    )
    try:
        eku = certificate.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
        constraints = certificate.extensions.get_extension_for_class(x509.BasicConstraints).value
        testbase.assert_equal(
            (list(eku), constraints.ca),
            ([x509.oid.ExtendedKeyUsageOID.CLIENT_AUTH], False),
        )
    finally:
        ca_adapter.reset_active_ca_for_testing()
    return


def test_issued_certificate_verifies_against_the_returned_chain():
    """
    **Feature: 3-client-enrollment (M2) -- one client identity (E2E-04)**
    **Property: the issued certificate is signed by the CA certificate the
    redemption returns as its chain, so a TLS terminator that trusts that
    CA accepts it.**
    """
    _session, result, certificate = _redeem_with_csr(
        pod_name="chain-pod", project_id="00000000-0000-0000-0000-000000000014",
    )
    try:
        ca_certificate = x509.load_pem_x509_certificate(result.cert_chain_pem)
        certificate.verify_directly_issued_by(ca_certificate)
        testbase.assert_equal(certificate.issuer, ca_certificate.subject)
    finally:
        ca_adapter.reset_active_ca_for_testing()
    return


def test_redeem_that_fails_to_sign_writes_no_client_row():
    """
    **Feature: 3-client-enrollment (M2) -- transactional redeem (LD-02)**
    **Property: when signing fails (no CA installed) the redemption
    writes no client row, so no phantom client is left behind.**
    """
    reset_phase2_runtime()
    _install_token_pepper()
    ca_adapter.reset_active_ca_for_testing()
    _engine, session = build_in_memory_session()

    pod_name = "phantom-pod"
    issued = issue_enrollment_token(
        db_session=session,
        project_id="00000000-0000-0000-0000-000000000015",
        pod_name=pod_name,
        ttl_seconds=600,
        one_shot=True,
        issued_by=None,
    )
    try:
        redeem_enrollment_token(
            db_session=session,
            secret=issued.secret,
            payload=EnrollmentPayload(
                pod_name=pod_name, agent_version="0.1.0", transport_name="http",
                extras={}, csr_pem=_generate_client_csr(common_name=pod_name),
            ),
        )
    except CertificateAuthorityUnavailableError:
        pass

    testbase.assert_equal(session.query(Client).count(), 0)
    return


def test_redeem_can_be_retried_after_a_signing_failure():
    """
    **Feature: 3-client-enrollment (M2) -- transactional redeem (LD-02)**
    **Property: after a redemption fails because no CA was installed,
    the same token redeems successfully once a CA is installed -- the
    failed attempt neither consumed the token nor reserved the pod name
    (it used to answer 409 "already registered").**
    """
    reset_phase2_runtime()
    _install_token_pepper()
    ca_adapter.reset_active_ca_for_testing()
    _engine, session = build_in_memory_session()

    pod_name = "retry-pod"
    issued = issue_enrollment_token(
        db_session=session,
        project_id="00000000-0000-0000-0000-000000000016",
        pod_name=pod_name,
        ttl_seconds=600,
        one_shot=True,
        issued_by=None,
    )

    def _redeem():
        rtnval = redeem_enrollment_token(
            db_session=session,
            secret=issued.secret,
            payload=EnrollmentPayload(
                pod_name=pod_name, agent_version="0.1.0", transport_name="http",
                extras={}, csr_pem=_generate_client_csr(common_name=pod_name),
            ),
        )
        return rtnval

    try:
        _redeem()
    except CertificateAuthorityUnavailableError:
        pass

    _install_dev_ca()
    try:
        result = _redeem()
        testbase.assert_equal(result.cert_pem is not None, True)
    finally:
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


def test_a_csr_named_for_another_pod_is_rejected_saying_which_name_the_token_expects():
    """
    **Feature: 3-client-enrollment (E2E-30)**
    **Property: the rejection of a CSR whose Subject CN is not the token's
    pod name names the pod name the token expects, whichever layer notices
    the mismatch, and does not spend the token.**
    """
    reset_phase2_runtime()
    ca_adapter.reset_active_ca_for_testing()
    _install_dev_ca()
    _engine, session = build_in_memory_session()

    issued = issue_enrollment_token(
        db_session=session, project_id="00000000-0000-0000-0000-000000000004", pod_name="intended-pod",
        ttl_seconds=600, one_shot=True, issued_by=None,
    )
    message = ""
    try:
        redeem_enrollment_token(
            db_session=session, secret=issued.secret,
            payload=EnrollmentPayload(
                pod_name="intended-pod", agent_version="0.1.0", transport_name="http", extras={},
                csr_pem=_generate_client_csr(common_name="other-pod"),
            ),
        )
    except (EnrollmentRejectedError, CsrScopeMismatchError) as rejection:
        message = str(rejection)
    result = redeem_enrollment_token(
        db_session=session, secret=issued.secret,
        payload=EnrollmentPayload(
            pod_name="intended-pod", agent_version="0.1.0", transport_name="http", extras={},
            csr_pem=_generate_client_csr(common_name="intended-pod"),
        ),
    )
    ca_adapter.reset_active_ca_for_testing()

    testbase.assert_equal(
        ("intended-pod" in message, len(message) > 0, result.pod_name),
        (True, True, "intended-pod"),
    )
    return
