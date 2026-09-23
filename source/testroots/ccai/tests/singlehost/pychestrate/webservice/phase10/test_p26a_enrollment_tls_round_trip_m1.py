"""
.. module:: test_p26a_enrollment_tls_round_trip_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Enroll-then-connect round trip: the files a pod writes
               from the redeem response load in TLS and authenticate
               the pod to a TLS server that trusts the enrollment CA.

.. moduleauthor:: Code Craft AI LLC

The redeem handler used to return ``client_certificate_pem`` and
``ca_chain_pem`` as base64 of the PEM. A pod client writes those
values to disk verbatim and hands the files to ``ssl``, which refused
them (``PEM lib`` / ``NO_CERTIFICATE_OR_CRL_FOUND``), so no enrolled
pod could open a TLS connection (E2E-05).

This module runs the real redemption (dev CA, real CSR, real handler,
in-memory database), writes the two response fields and the pod's
private key to files exactly as ``pychestrate-client`` does, and
opens a mutual-TLS connection to an in-process TLS server that
requires a client certificate issued by the returned CA. The server
reports the peer certificate's CN, which must be the client id the
redemption assigned (E2E-04).
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import os
import socket
import ssl
import tempfile
import threading

from datetime import datetime, timedelta, timezone
from ipaddress import IPv4Address
from typing import Any, Dict, Optional

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from ccai import testbase

from ccai.pychestrate.webservice.clients.enrollment import ca_adapter
from ccai.pychestrate.webservice.clients.enrollment.service import (
    issue_enrollment_token,
)
from ccai.pychestrate.webservice.clients.restapi.v1 import enrollment_routes
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


_POD_NAME = "round-trip-pod"
_PROJECT_ID = "00000000-0000-0000-0000-00000000a26a"

_ROUND_TRIP_CACHE: Dict[str, Any] = {}


class _RedeemRequest:
    """
        Minimal webworks request stand-in for the redeem handler: a
        JSON body and the request-scoped db session.
    """

    def __init__(self, *, body: Dict[str, Any], db_session: Any) -> None:
        self.path: str = "/api/v1/enrollment-tokens/redeem"
        self.path_params: Dict[str, Any] = {}
        self._body: Dict[str, Any] = body
        self.db_session: Any = db_session
        return

    def json(self) -> Any:
        return self._body


def _write(*, directory: str, name: str, content: bytes) -> str:
    path = os.path.join(directory, name)
    with open(path, "wb") as handle:
        handle.write(content)
    rtnval = path
    return rtnval


def _self_signed_server_certificate(*, directory: str) -> Dict[str, str]:
    """
        Create a throwaway self-signed TLS server certificate for
        127.0.0.1 (the in-process server's identity; unrelated to the
        enrollment CA).

        :returns: Dict with ``cert`` and ``key`` file paths.
    """
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "127.0.0.1")])
    now = datetime.now(timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.IPAddress(IPv4Address("127.0.0.1"))]), critical=False)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(private_key=key, algorithm=hashes.SHA256())
    )
    rtnval = {
        "cert": _write(directory=directory, name="server.crt",
                       content=certificate.public_bytes(serialization.Encoding.PEM)),
        "key": _write(directory=directory, name="server.key", content=key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )),
    }
    return rtnval


def _enroll_and_write_files(*, directory: str) -> Dict[str, Any]:
    """
        Redeem a real enrollment token through the REST handler and
        write the response's PEM fields plus the pod key to files the
        way ``pychestrate-client`` does.

        :returns: Dict with ``client_id`` and the three file paths.
    """
    reset_phase2_runtime()
    set_active_pepper(pepper=SecretBytes(b"p26a-round-trip-test-pepper"))
    ca_adapter.reset_active_ca_for_testing()
    ca_adapter.set_active_ca(ca=ca_adapter.load_ca_at_startup(
        source="file",
        file_path=_write(directory=directory, name="enrollment-ca.pem",
                         content=ca_adapter.generate_dev_ca(common_name="Round Trip Enrollment CA")),
        ca_id="round-trip-ca",
    ))
    _engine, session = build_in_memory_session()

    issued = issue_enrollment_token(
        db_session=session, project_id=_PROJECT_ID, pod_name=_POD_NAME,
        ttl_seconds=600, one_shot=True, issued_by=None,
    )
    pod_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, _POD_NAME)]))
        .sign(private_key=pod_key, algorithm=hashes.SHA256())
    )
    response = enrollment_routes.handle_redeem_enrollment_token(_RedeemRequest(
        body={
            "bootstrap_secret": issued.secret,
            "csr_pem": csr.public_bytes(serialization.Encoding.PEM).decode("ascii"),
            "display_name": _POD_NAME,
        },
        db_session=session,
    ))
    body = json.loads(response.body.decode("utf-8"))

    rtnval = {
        "status_code": response.status_code,
        "client_id": body.get("client_id"),
        "client_cert_path": _write(directory=directory, name="client.crt",
                                   content=body.get("client_certificate_pem", "").encode("utf-8")),
        "ca_chain_path": _write(directory=directory, name="service-ca.crt",
                                content=body.get("ca_chain_pem", "").encode("utf-8")),
        "client_key_path": _write(directory=directory, name="client.key", content=pod_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )),
    }
    return rtnval


def _mutual_tls_peer_cn(*, files: Dict[str, Any], server_files: Dict[str, str]) -> Optional[str]:
    """
        Accept one connection on an in-process TLS server that requires
        a client certificate issued by the enrollment CA, connect to it
        with the pod's files, and return the client-certificate CN the
        server saw.

        :returns: The peer CN the server observed.
    """
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(certfile=server_files["cert"], keyfile=server_files["key"])
    server_context.verify_mode = ssl.CERT_REQUIRED
    server_context.load_verify_locations(cafile=files["ca_chain_path"])

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    listener.settimeout(10)
    port = listener.getsockname()[1]
    observed: Dict[str, Any] = {}

    def _serve() -> None:
        try:
            raw, _addr = listener.accept()
            with server_context.wrap_socket(raw, server_side=True) as tls:
                subject = dict(item[0] for item in tls.getpeercert()["subject"])
                observed["cn"] = subject.get("commonName")
                tls.sendall(b"ok")
        except Exception as xcpt:  # noqa: BLE001 -- surfaced through the assertion
            observed["error"] = repr(xcpt)
        return

    server_thread = threading.Thread(target=_serve, daemon=True)
    server_thread.start()
    try:
        client_context = ssl.create_default_context(cafile=server_files["cert"])
        client_context.load_cert_chain(certfile=files["client_cert_path"], keyfile=files["client_key_path"])
        with socket.create_connection(("127.0.0.1", port), timeout=10) as raw_client:
            with client_context.wrap_socket(raw_client, server_hostname="127.0.0.1") as tls_client:
                tls_client.recv(2)
    finally:
        server_thread.join(timeout=10)
        listener.close()

    rtnval = observed.get("cn")
    return rtnval


def _active_pepper_or_none() -> Any:
    """
        The active password pepper, or None when none is loaded.
    """
    from ccai.pychestrate.webservice.security.auth.pepper_loader import (  # noqa: E402
        get_active_pepper,
    )
    # ConfigurationError (no pepper loaded) derives from BaseException.
    try:
        rtnval = get_active_pepper()
    except BaseException:
        rtnval = None
    return rtnval


def _restore_pepper(*, pepper: Any) -> None:
    """
        Reinstate ``pepper`` (or clear the pepper when it is None).
    """
    from ccai.pychestrate.webservice.security.auth.pepper_loader import (  # noqa: E402
        reset_active_pepper_for_testing,
    )
    if pepper is None:
        reset_active_pepper_for_testing()
    else:
        set_active_pepper(pepper=pepper)
    return


def _round_trip() -> Dict[str, Any]:
    """
        Run the enrollment + file writing once per test run and cache
        it; each test asserts one property of the shared outcome.
    """
    if len(_ROUND_TRIP_CACHE) == 0:
        directory = tempfile.mkdtemp(prefix="pyc-p26a-")
        # The enrollment installs its own password pepper; put back the
        # one that was active so later tests in the same process (the
        # phase-10 e2e harness signs in with passwords hashed under it)
        # are unaffected.
        previous_pepper = _active_pepper_or_none()
        try:
            files = _enroll_and_write_files(directory=directory)
        finally:
            ca_adapter.reset_active_ca_for_testing()
            _restore_pepper(pepper=previous_pepper)
        _ROUND_TRIP_CACHE.update(files)
        _ROUND_TRIP_CACHE["directory"] = directory
    rtnval = _ROUND_TRIP_CACHE
    return rtnval


def test_redeem_round_trip_succeeds():
    """
    **Feature: 3-client-enrollment -- enroll-then-connect (E2E-05)**
    **Property: the real redemption through the REST handler answers
    200.**
    """
    files = _round_trip()
    testbase.assert_equal(files["status_code"], 200)
    return


def test_client_certificate_file_loads_into_tls():
    """
    **Feature: 3-client-enrollment -- enroll-then-connect (E2E-05)**
    **Property: the certificate file written verbatim from
    ``client_certificate_pem`` loads into an ``ssl`` context together
    with the pod's private key.**
    """
    files = _round_trip()
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    load_error = None
    try:
        context.load_cert_chain(certfile=files["client_cert_path"], keyfile=files["client_key_path"])
    except ssl.SSLError as xcpt:
        load_error = str(xcpt)
    testbase.assert_equal(load_error, None)
    return


def test_ca_chain_file_loads_as_tls_trust_anchor():
    """
    **Feature: 3-client-enrollment -- enroll-then-connect (E2E-05)**
    **Property: the file written verbatim from ``ca_chain_pem`` loads as
    a trust anchor (exactly one CA certificate).**
    """
    files = _round_trip()
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    load_error = None
    try:
        context.load_verify_locations(cafile=files["ca_chain_path"])
    except ssl.SSLError as xcpt:
        load_error = str(xcpt)
    testbase.assert_equal((load_error, context.cert_store_stats()["x509_ca"]), (None, 1))
    return


def test_tls_server_trusting_the_enrollment_ca_sees_the_client_id():
    """
    **Feature: 3-client-enrollment -- enroll-then-connect (E2E-04/E2E-05)**
    **Property: a TLS server that requires client certificates issued by
    the returned CA accepts the pod's files, and the certificate CN it
    sees is the client id the redemption assigned.**
    """
    files = _round_trip()
    server_files = _self_signed_server_certificate(directory=files["directory"])
    peer_cn = _mutual_tls_peer_cn(files=files, server_files=server_files)
    testbase.assert_equal(peer_cn, files["client_id"])
    return
