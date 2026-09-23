"""
.. module:: clients.enrollment.ca_adapter
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Client-enrollment CA signing adapter.

.. moduleauthor:: Code Craft AI LLC

The CA adapter owns two responsibilities:

1. **Bootstrap-time loading.** Operators install the signing material
   once at service startup via :func:`load_ca_at_startup` and
   :func:`set_active_ca`. Supported sources in M2 are ``file`` (a path
   to a PEM concatenation of the private key and the CA certificate)
   and ``env`` (the same PEM content inlined into an environment
   variable). The long-running ``secrets-vault`` source lands when
   the deployer wires ``bootstrap_phase1_runtime`` through the full
   vault flow — it can then stage the material into this module via
   :func:`set_active_ca` without changing callers.
2. **Per-request CSR signing.** :func:`sign_csr` accepts a PEM-encoded
   CSR, validates that the supplied Subject CN matches the pod name
   the enrollment token is scoped to, and returns a freshly signed
   X.509 certificate plus the metadata the service persists on the
   :class:`ClientCert` row.

Certificate identity
--------------------

The CSR's Subject CN only proves which pod the requester claims
(it must equal the pod name the token names). The certificate the
CA issues is NOT a copy of the CSR subject: its Subject CN, and a
``urn:uuid:`` URI subject alternative name, carry the client id the
enrollment service assigns. That client id is the identity every
pod-facing route checks (the TLS terminator forwards the verified
certificate CN, and the routes compare it with the ``client_id`` in
the path), so a pod has exactly one identity end to end: registry
row, certificate, and URL. The certificate is also marked as a TLS
client certificate (``extendedKeyUsage=clientAuth``) that cannot
act as a CA.

The module intentionally does not hold a long-lived reference to the
plaintext private key. :class:`CaHandle` wraps the key in
:class:`SecretBytes`; signing loads a ``cryptography`` key object
inside :func:`sign_csr`, produces the certificate, and drops the
reference before returning so it is available for garbage collection
in a single frame.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import secrets
import uuid

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from ccai.errors.exceptions import ConfigurationError

from ccai.pychestrate.webservice.clients.exceptions import (
    CertificateAuthorityUnavailableError,
    CsrScopeMismatchError,
    CsrValidationError,
)
from ccai.pychestrate.webservice.secrets.secret_bytes import SecretBytes


# RFC 5280 caps cert serials at 159 significant bits (the ASN.1 INTEGER
# encoding is signed, so the top bit must be zero). 19 bytes = 152 bits,
# comfortably under the cap and well above the collision-resistance
# floor a signed certificate serial actually needs.
SERIAL_ENTROPY_BYTES: int = 19
DEFAULT_CERT_TTL_DAYS: int = 365


@dataclass(frozen=True)
class CaHandle:
    """
        A loaded CA identity the adapter can sign against.

        :param ca_id: Operator-assigned identifier for the loaded CA.
        :param key_material: PEM-encoded private key wrapped in
                             :class:`SecretBytes`. Zeroized on handle
                             close.
        :param cert_pem: PEM-encoded CA certificate used as the issuer.
        :param issuer_subject: Human-readable subject DN of the CA
                               certificate, cached for quick insertion
                               into the ``ClientCert`` row.
        :param source: Short string describing where the CA was loaded
                       from.
    """
    ca_id: str
    key_material: SecretBytes
    cert_pem: bytes
    issuer_subject: str
    source: str


@dataclass(frozen=True)
class SignedCertificate:
    """
        Result returned by :func:`sign_csr`.

        :param cert_serial: Decimal serial string that is the stable
                            identity of the issued certificate.
        :param pem_public: PEM-encoded signed certificate.
        :param chain_pem: PEM-encoded issuer chain (currently a single
                          CA cert).
        :param subject_cn: The Subject CN of the issued certificate --
                           the ``issued_subject_cn`` the caller asked
                           for (the enrolled client id), not the CSR's
                           CN.
        :param not_before: Validity window start (UTC).
        :param not_after: Validity window end (UTC).
        :param issuer_subject: Subject DN of the issuing CA.
    """
    cert_serial: str
    pem_public: bytes
    chain_pem: bytes
    subject_cn: str
    not_before: datetime
    not_after: datetime
    issuer_subject: str


_ACTIVE_CA: Optional[CaHandle] = None


def set_active_ca(*, ca: CaHandle) -> None:
    """
        Register the active CA handle for the process. :func:`sign_csr`
        reads the active CA via :func:`get_active_ca`.

        :param ca: The :class:`CaHandle` returned by
                   :func:`load_ca_at_startup` or constructed directly
                   by a vault-backed deployer.

        :returns: None.
    """
    global _ACTIVE_CA
    _ACTIVE_CA = ca
    return


def get_active_ca() -> CaHandle:
    """
        Return the currently-installed :class:`CaHandle` or raise.

        :returns: The active CA handle.
        :raises: CertificateAuthorityUnavailableError when none is
                 installed.
    """
    handle = _ACTIVE_CA
    if handle is None:
        err_msg_lines = ["No client-enrollment CA is installed."]
        err_msg_lines.append("HINT: call load_ca_at_startup() + set_active_ca() from the service bootstrap.")
        err_msg = os.linesep.join(err_msg_lines)
        raise CertificateAuthorityUnavailableError(err_msg) from None
    return handle


def reset_active_ca_for_testing() -> None:
    """
        Clear the active CA handle. Intended for the test suite only.

        :returns: None.
    """
    global _ACTIVE_CA
    _ACTIVE_CA = None
    return


def load_ca_at_startup(
        *,
        source: str,
        file_path: Optional[str] = None,
        env_var: Optional[str] = None,
        ca_id: str
    ) -> CaHandle:
    """
        Load the CA PEM material from an operator-supplied source.

        Mirrors the :func:`secrets.kek_loader.load_kek_at_startup`
        signature so deploy wiring treats the two identically.

        :param source: ``"file"`` or ``"env"``.
        :param file_path: Path to a PEM file containing the CA cert +
                          private key (concatenated) when
                          ``source="file"``.
        :param env_var: Environment variable holding the same PEM
                        content when ``source="env"``.
        :param ca_id: Operator-assigned identifier for the active CA.

        :returns: A populated :class:`CaHandle`.
        :raises: ConfigurationError when the source cannot be read or
                 the PEM payload cannot be parsed.
    """
    if source == "file":
        if file_path is None or len(file_path) == 0:
            err_msg_lines = ["CA source 'file' requires file_path."]
            err_msg = os.linesep.join(err_msg_lines)
            raise ConfigurationError(err_msg) from None
        try:
            with open(file_path, "rb") as handle:
                pem_bytes = handle.read()
        except OSError as xcpt:
            err_msg_lines = ["Cannot load CA material — file read failed."]
            err_msg_lines.append("PATH: {}".format(file_path))
            err_msg_lines.append("REASON: {}".format(str(xcpt)))
            err_msg = os.linesep.join(err_msg_lines)
            raise ConfigurationError(err_msg) from xcpt
    elif source == "env":
        if env_var is None or len(env_var) == 0:
            err_msg_lines = ["CA source 'env' requires env_var."]
            err_msg = os.linesep.join(err_msg_lines)
            raise ConfigurationError(err_msg) from None
        value = os.environ.get(env_var, None)
        if value is None or len(value) == 0:
            err_msg_lines = ["Cannot load CA material — env var is empty."]
            err_msg_lines.append("ENV_VAR: {}".format(env_var))
            err_msg = os.linesep.join(err_msg_lines)
            raise ConfigurationError(err_msg) from None
        pem_bytes = value.encode("utf-8")
    else:
        err_msg_lines = ["Unsupported CA source."]
        err_msg_lines.append("SOURCE: {}".format(source))
        err_msg_lines.append("SUPPORTED: (file, env)")
        err_msg = os.linesep.join(err_msg_lines)
        raise ConfigurationError(err_msg) from None

    key_pem, cert_pem = _split_ca_pem(pem_bytes=pem_bytes)
    issuer_subject = _read_issuer_subject(cert_pem=cert_pem)

    rtnval = CaHandle(
        ca_id=ca_id,
        key_material=SecretBytes(key_pem),
        cert_pem=cert_pem,
        issuer_subject=issuer_subject,
        source=source,
    )
    return rtnval


def validate_csr(
        *,
        csr_pem: bytes,
        expected_subject_cn: str
    ) -> x509.CertificateSigningRequest:
    """
        Parse a PEM-encoded CSR and check it may be signed for an
        enrollment scoped to ``expected_subject_cn``: it must parse,
        its self-signature must verify, and its Subject CN must equal
        the pod name the token names. Nothing is signed or stored, so
        callers can run this before they write anything.

        :param csr_pem: PEM-encoded certificate signing request.
        :param expected_subject_cn: Pod name the enrollment token is
                                    scoped to.

        :returns: The parsed CSR.
        :raises: CsrValidationError when the CSR is empty, cannot be
                 parsed or its signature does not verify;
                 CsrScopeMismatchError when the Subject CN does not
                 match.
    """
    if csr_pem is None or len(csr_pem) == 0:
        err_msg_lines = ["Cannot sign empty CSR."]
        err_msg = os.linesep.join(err_msg_lines)
        raise CsrValidationError(err_msg) from None

    try:
        csr = x509.load_pem_x509_csr(csr_pem)
    except ValueError as xcpt:
        err_msg_lines = ["CSR did not parse as PEM X.509 CSR."]
        err_msg_lines.append("REASON: {}".format(str(xcpt)))
        err_msg = os.linesep.join(err_msg_lines)
        raise CsrValidationError(err_msg) from xcpt

    if csr.is_signature_valid is False:
        err_msg_lines = ["CSR signature did not verify against its public key."]
        err_msg = os.linesep.join(err_msg_lines)
        raise CsrValidationError(err_msg) from None

    subject_cn = _extract_subject_cn(csr=csr)
    if subject_cn != expected_subject_cn:
        err_msg_lines = ["CSR Subject CN does not match enrollment token scope."]
        err_msg_lines.append("CSR_CN: {}".format(subject_cn))
        err_msg_lines.append("EXPECTED_CN: {}".format(expected_subject_cn))
        err_msg = os.linesep.join(err_msg_lines)
        raise CsrScopeMismatchError(err_msg) from None

    rtnval = csr
    return rtnval


def sign_csr(
        *,
        csr_pem: bytes,
        expected_subject_cn: str,
        issued_subject_cn: str,
        ttl_days: int = DEFAULT_CERT_TTL_DAYS
    ) -> SignedCertificate:
    """
        Sign a PEM-encoded CSR against the active CA and return the
        issued certificate metadata. The CSR Subject CN must match
        ``expected_subject_cn``; any mismatch raises
        :class:`CsrScopeMismatchError` so the caller can translate it
        to a ``scope_mismatch`` rejection.

        The issued certificate's subject is ``CN=<issued_subject_cn>``
        rather than a copy of the CSR subject; see "Certificate
        identity" in the module docstring.

        :param csr_pem: PEM-encoded certificate signing request.
        :param expected_subject_cn: Pod name the enrollment token is
                                    scoped to — must equal the CSR
                                    Subject CN.
        :param issued_subject_cn: Identity to issue the certificate
                                  under: the client id the enrollment
                                  service assigned. Also published as a
                                  ``urn:uuid:`` URI subject alternative
                                  name when it is a UUID.
        :param ttl_days: Desired certificate validity window in days.

        :returns: A :class:`SignedCertificate` describing the issued
                  cert.
        :raises: CsrValidationError when the CSR cannot be parsed or
                 its signature does not verify, or when
                 ``issued_subject_cn`` is empty;
                 CsrScopeMismatchError when the Subject CN does not
                 match; CertificateAuthorityUnavailableError when no CA
                 is installed.
    """
    if ttl_days <= 0:
        err_msg_lines = ["ttl_days must be > 0."]
        err_msg_lines.append("RECEIVED: {}".format(ttl_days))
        err_msg = os.linesep.join(err_msg_lines)
        raise CsrValidationError(err_msg) from None

    if issued_subject_cn is None or len(issued_subject_cn) == 0:
        err_msg_lines = ["Cannot issue a client certificate without an identity (issued_subject_cn is empty)."]
        err_msg = os.linesep.join(err_msg_lines)
        raise CsrValidationError(err_msg) from None

    csr = validate_csr(csr_pem=csr_pem, expected_subject_cn=expected_subject_cn)

    ca_handle = get_active_ca()

    ca_cert = x509.load_pem_x509_certificate(ca_handle.cert_pem)
    ca_private_key = serialization.load_pem_private_key(
        data=ca_handle.key_material.reveal(),
        password=None,
    )

    not_before = datetime.now(timezone.utc)
    not_after = not_before + timedelta(days=ttl_days)
    serial_int = int.from_bytes(
        secrets.token_bytes(SERIAL_ENTROPY_BYTES),
        byteorder="big",
        signed=False,
    )
    serial_int = serial_int | 0x01

    subject_public_key = csr.public_key()
    is_rsa_key = isinstance(subject_public_key, rsa.RSAPublicKey)

    builder = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, issued_subject_cn)]))
        .issuer_name(ca_cert.subject)
        .public_key(subject_public_key)
        .serial_number(serial_int)
        .not_valid_before(not_before)
        .not_valid_after(not_after)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=is_rsa_key,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]), critical=False)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(subject_public_key), critical=False)
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_cert.public_key()),
            critical=False,
        )
    )

    client_uuid_urn = _client_uuid_urn(identity=issued_subject_cn)
    if client_uuid_urn is not None:
        builder = builder.add_extension(
            x509.SubjectAlternativeName([x509.UniformResourceIdentifier(client_uuid_urn)]),
            critical=False,
        )

    signed_cert = builder.sign(
        private_key=ca_private_key,
        algorithm=hashes.SHA256(),
    )
    cert_pem = signed_cert.public_bytes(encoding=serialization.Encoding.PEM)
    serial_str = "{:x}".format(serial_int)

    rtnval = SignedCertificate(
        cert_serial=serial_str,
        pem_public=cert_pem,
        chain_pem=ca_handle.cert_pem,
        subject_cn=issued_subject_cn,
        not_before=not_before,
        not_after=not_after,
        issuer_subject=ca_handle.issuer_subject,
    )
    return rtnval


def _client_uuid_urn(*, identity: str) -> Optional[str]:
    """
        Render a client id as an RFC 4122 ``urn:uuid:`` URI for the
        certificate's subject alternative name.

        :param identity: The issued identity (normally a client UUID).

        :returns: ``urn:uuid:<uuid>`` when ``identity`` is a UUID,
                  otherwise ``None``.
    """
    try:
        parsed = uuid.UUID(str(identity))
    except (ValueError, TypeError, AttributeError):
        return None
    rtnval = "urn:uuid:{}".format(parsed)
    return rtnval


def generate_dev_ca(*, common_name: str = "Pychestrate Dev CA") -> bytes:
    """
        Produce a self-signed CA PEM (private key concatenated with
        the CA certificate) suitable for loading via
        :func:`load_ca_at_startup` with ``source="env"``. Intended for
        tests and local development — real deployments supply material
        through ``1-secrets-vault``.

        :param common_name: Subject CN to set on the generated CA cert.

        :returns: PEM bytes: private key block followed by the CA cert
                  block, safe to feed back into
                  :func:`load_ca_at_startup`.
    """
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    subject = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Code Craft AI"),
    ])
    issuer = subject

    not_before = datetime.now(timezone.utc) - timedelta(seconds=5)
    not_after = not_before + timedelta(days=365 * 5)
    serial_int = int.from_bytes(
        secrets.token_bytes(SERIAL_ENTROPY_BYTES),
        byteorder="big",
        signed=False,
    ) | 0x01

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(serial_int)
        .not_valid_before(not_before)
        .not_valid_after(not_after)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(private_key=private_key, algorithm=hashes.SHA256())
    )

    key_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    cert_pem = cert.public_bytes(encoding=serialization.Encoding.PEM)
    rtnval = key_pem + cert_pem
    return rtnval


def _split_ca_pem(*, pem_bytes: bytes) -> Tuple[bytes, bytes]:
    """
        Split a combined PEM blob into a (key, cert) PEM pair. The
        loader accepts either ordering and rejects inputs that are
        missing either block.

        :param pem_bytes: Combined PEM content.

        :returns: Tuple ``(key_pem, cert_pem)``.
        :raises: ConfigurationError when either block is missing.
    """
    key_marker = b"-----BEGIN"
    key_private_markers = (b"-----BEGIN PRIVATE KEY-----", b"-----BEGIN RSA PRIVATE KEY-----", b"-----BEGIN EC PRIVATE KEY-----")
    cert_begin = b"-----BEGIN CERTIFICATE-----"
    cert_end = b"-----END CERTIFICATE-----"

    cert_start_idx = pem_bytes.find(cert_begin)
    cert_end_idx = pem_bytes.find(cert_end)
    if cert_start_idx < 0 or cert_end_idx < 0:
        err_msg_lines = ["CA PEM input does not contain a CERTIFICATE block."]
        err_msg = os.linesep.join(err_msg_lines)
        raise ConfigurationError(err_msg) from None
    cert_pem = pem_bytes[cert_start_idx:cert_end_idx + len(cert_end)]

    key_start_idx = -1
    for marker in key_private_markers:
        idx = pem_bytes.find(marker)
        if idx >= 0:
            key_start_idx = idx
            key_begin = marker
            break
    if key_start_idx < 0:
        err_msg_lines = ["CA PEM input does not contain a PRIVATE KEY block."]
        err_msg_lines.append("LOOKED_FOR: {}".format([m.decode('ascii') for m in key_private_markers]))
        err_msg = os.linesep.join(err_msg_lines)
        raise ConfigurationError(err_msg) from None

    key_end_marker = key_begin.replace(b"BEGIN", b"END")
    key_end_idx = pem_bytes.find(key_end_marker)
    if key_end_idx < 0:
        err_msg_lines = ["CA PEM input key block is missing its END marker."]
        err_msg_lines.append("LOOKED_FOR: {}".format(key_end_marker.decode('ascii')))
        err_msg = os.linesep.join(err_msg_lines)
        raise ConfigurationError(err_msg) from None
    key_pem = pem_bytes[key_start_idx:key_end_idx + len(key_end_marker)]

    rtnval = (key_pem, cert_pem)
    return rtnval


def _read_issuer_subject(*, cert_pem: bytes) -> str:
    """
        Render the CA cert's subject DN as a readable string suitable
        for storage in the ``ClientCert.issuer_subject`` column.

        :param cert_pem: PEM-encoded CA certificate.

        :returns: RFC 4514 DN string.
        :raises: ConfigurationError when the cert cannot be parsed.
    """
    try:
        cert = x509.load_pem_x509_certificate(cert_pem)
    except ValueError as xcpt:
        err_msg_lines = ["CA certificate did not parse as PEM."]
        err_msg_lines.append("REASON: {}".format(str(xcpt)))
        err_msg = os.linesep.join(err_msg_lines)
        raise ConfigurationError(err_msg) from xcpt
    rtnval = cert.subject.rfc4514_string()
    return rtnval


def _extract_subject_cn(*, csr: x509.CertificateSigningRequest) -> str:
    """
        Pull the Subject CN attribute out of a parsed CSR. CSRs without
        a CN attribute are treated as empty-CN so the caller's scope
        check rejects them explicitly.

        :param csr: Parsed :class:`cryptography.x509.CertificateSigningRequest`.

        :returns: CN string, or an empty string when the CSR has no CN.
    """
    attrs = csr.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    if len(attrs) == 0:
        return ""
    rtnval = attrs[0].value
    if isinstance(rtnval, bytes):
        rtnval = rtnval.decode("utf-8")
    return rtnval


def _key_algorithm_is_accepted(*, csr: x509.CertificateSigningRequest) -> bool:
    """
        Return whether the CSR's public key algorithm is on the accept
        list for this service. Exposed as an internal helper so future
        hardening (e.g. PQ-readiness gating) can be swapped in without
        touching :func:`sign_csr`.

        :param csr: Parsed :class:`cryptography.x509.CertificateSigningRequest`.

        :returns: True when the key type is RSA or EC.
    """
    public_key = csr.public_key()
    if isinstance(public_key, rsa.RSAPublicKey):
        return True
    if isinstance(public_key, ec.EllipticCurvePublicKey):
        return True
    return False
