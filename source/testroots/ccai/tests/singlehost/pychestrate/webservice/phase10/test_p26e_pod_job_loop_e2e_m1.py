"""
.. module:: test_p26e_pod_job_loop_e2e_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Unmocked end-to-end test of the service side of the pod
               job loop through the production WSGI application.

.. moduleauthor:: Code Craft AI LLC

Boots ``build_wsgi_application_for_production()`` in a subprocess (the
webworks persona is process-global) with a fresh SQLite database, an
enrollment CA, an envelope signing key and a presign secret -- the
environment the launchers now provision -- and drives it with raw
PEP-3333 environs the way nginx + gunicorn would:

1. an operator mints an enrollment token for a pod;
2. the pod redeems it with a real CSR (``POST .../redeem``);
3. the pod's calls carry its certificate CN in ``X-Client-Cert-CN`` /
   ``X-Client-Cert-Verify`` from the loopback proxy;
4. it heartbeats and advertises capabilities;
5. an RPA job is triggered through the RPA service with the
   candidates the product resolves for the project;
6. the pod's long-poll receives the signed envelope for that job.

Nothing is mocked. Each test asserts one property of the recorded
observations. The loop beyond delivery (dispatch-ack, progress,
results) is outside this module.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap

from typing import Any, Dict, Generator, Optional

from ccai import testbase
from ccai.testbase.resourcelifespan import ResourceLifespan

from ccai.pychestrate.webservice.clients.enrollment import ca_adapter


def _repo_root() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    rtnval = os.path.normpath(os.path.join(here, "..", "..", "..", "..", "..", "..", "..", ".."))
    return rtnval


_DRIVER_SCRIPT = textwrap.dedent('''\
    import io
    import json
    import os
    import sys
    import traceback

    REPO_ROOT = {repo_root!r}
    for component in ("source/site", "source/packages"):
        full = os.path.join(REPO_ROOT, component)
        if full not in sys.path:
            sys.path.insert(0, full)

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    from app_pychestrate_main import build_wsgi_application_for_production

    PROJECT_ID = "3a1c2b7e-5d44-4f0a-9d2e-6b8c1f0e2a26"
    POD_NAME = "e2e-pod"
    results = {{}}

    def drive(method, path, *, body=None, headers=None, remote_addr="127.0.0.1", query=""):
        environ = {{
            "REQUEST_METHOD": method, "PATH_INFO": path, "QUERY_STRING": query,
            "SERVER_NAME": "pyc.invalid", "SERVER_PORT": "8888", "SERVER_PROTOCOL": "HTTP/1.1",
            "SCRIPT_NAME": "", "REMOTE_ADDR": remote_addr,
            "wsgi.input": io.BytesIO(body or b""), "wsgi.errors": sys.stderr,
            "wsgi.url_scheme": "http", "wsgi.multithread": True, "wsgi.multiprocess": False,
            "wsgi.run_once": False, "wsgi.version": (1, 0),
            "CONTENT_LENGTH": str(len(body)) if body else "",
        }}
        if body:
            environ["CONTENT_TYPE"] = "application/json"
        for name, value in (headers or {{}}).items():
            environ["HTTP_" + name.upper().replace("-", "_")] = value
        captured = {{}}
        def start_response(status, response_headers, exc_info=None):
            captured["status"] = int(status.split(" ")[0])
            return lambda chunk: None
        response = wsgi_app(environ, start_response)
        payload = b"".join(chunk for chunk in response if chunk)
        close = getattr(response, "close", None)
        if callable(close):
            close()
        return captured.get("status", -1), payload

    try:
        wsgi_app = build_wsgi_application_for_production()

        from ccai.pychestrate.webservice.metadata import SITE_SHARED_GLOBALS
        from ccai.pychestrate.webservice.clients.enrollment.service import issue_enrollment_token
        session = SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY()
        try:
            issued = issue_enrollment_token(
                db_session=session, project_id=PROJECT_ID, pod_name=POD_NAME,
                ttl_seconds=600, one_shot=True, issued_by=None,
            )
        finally:
            session.close()

        pod_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        csr = (x509.CertificateSigningRequestBuilder()
               .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, POD_NAME)]))
               .sign(private_key=pod_key, algorithm=hashes.SHA256()))
        status, payload = drive("POST", "/api/v1/enrollment-tokens/redeem", body=json.dumps({{
            "bootstrap_secret": issued.secret,
            "csr_pem": csr.public_bytes(serialization.Encoding.PEM).decode("ascii"),
            "display_name": POD_NAME,
        }}).encode("utf-8"))
        results["redeem_status"] = status
        redeem = json.loads(payload.decode("utf-8"))
        client_id = redeem["client_id"]
        certificate = x509.load_pem_x509_certificate(redeem["client_certificate_pem"].encode("ascii"))
        cert_cn = certificate.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value
        results["cert_cn_equals_client_id"] = cert_cn == client_id
        proxy_identity = {{"X-Client-Cert-CN": cert_cn, "X-Client-Cert-Verify": "SUCCESS"}}
        heartbeat_path = "/api/v1/clients/{{}}/heartbeat".format(client_id)

        results["heartbeat_status"] = drive("GET", heartbeat_path, headers=proxy_identity)[0]
        results["heartbeat_untrusted_peer_status"] = drive(
            "GET", heartbeat_path, headers=proxy_identity, remote_addr="192.0.2.10")[0]
        results["heartbeat_underscore_header_status"] = drive(
            "GET", heartbeat_path, headers={{"SSL_CLIENT_S_DN_CN": cert_cn, "SSL_CLIENT_VERIFY": "SUCCESS"}})[0]

        results["capabilities_status"] = drive(
            "PUT", "/api/v1/clients/{{}}/capabilities".format(client_id), headers=proxy_identity,
            body=json.dumps({{"advertisements": [{{"kind": "rpa", "value": {{
                "job_types": ["e2e-echo"], "taskplus": None, "tags": []}}}}]}}).encode("utf-8"),
        )[0]

        from ccai.pychestrate.webservice.pods.models import PodRegistration, RegistrationState
        from ccai.pychestrate.webservice.orchestration.rpa import service as rpa_service
        from ccai.pychestrate.webservice.orchestration.rpa.candidates import resolve_dispatch_candidates
        session = SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY()
        try:
            registrations = (session.query(PodRegistration)
                             .filter(PodRegistration.client_id == client_id)
                             .filter(PodRegistration.state == RegistrationState.REGISTERED).all())
            results["registered_pods"] = len(registrations)

            rpa_service.register_job_type(db_session=session, inputs=rpa_service.RpaJobTypeInputs(
                type_id="e2e-echo", display_name="E2E echo", execution_mode="process"))
            rpa_service.publish_version(db_session=session, type_id="e2e-echo", inputs=rpa_service.RpaVersionInputs(
                version="1.0.0", source_kind="local", source_ref="/tmp",
                entrypoint={{"command": ["python3", "-c", "print('hello')"]}}))
            spec = rpa_service.create_spec(db_session=session, project_id=PROJECT_ID, inputs=rpa_service.RpaSpecInputs(
                name="e2e spec", type_id="e2e-echo"))
            candidates = resolve_dispatch_candidates(db_session=session, project_id=PROJECT_ID)
            results["candidate_client_ids"] = [candidate.client_id for candidate in candidates]
            job = rpa_service.trigger_job(
                db_session=session, project_id=PROJECT_ID, spec_id=spec.spec_id, work_packet={{}},
                aspects=rpa_service.RpaTriggerAspects(candidates=candidates, project_slug="e2e",
                                                      trigger_cause={{"kind": "api"}}))
            results["job_id"] = job.job_id
        finally:
            session.close()

        status, payload = drive("GET", "/api/v1/clients/{{}}/dispatches:next".format(client_id),
                                headers=proxy_identity, query="timeout_seconds=5")
        results["dispatch_status"] = status
        pending = json.loads(payload.decode("utf-8")) if status == 200 else {{}}
        results["dispatch_run_id"] = pending.get("run_id")
        results["dispatch_client_id_matches"] = pending.get("client_id") == client_id
        results["dispatch_job_kind"] = (pending.get("envelope") or {{}}).get("job_kind")
        results["dispatch_signature_key_id"] = pending.get("signature_key_id")

        status, payload = drive("GET", "/api/v1/envelope-signing-keys", headers=proxy_identity)
        keys = json.loads(payload.decode("utf-8")).get("keys", []) if status == 200 else []
        results["signing_key_ids"] = [key.get("key_id") for key in keys]
    except BaseException:
        traceback.print_exc()
    print("RESULTS: " + json.dumps(results, sort_keys=True))
''')


@testbase.register.resource_factory()
def create_pod_job_loop_observations(constraints: Optional[Dict[str, Any]] = None) -> Generator[Dict[str, Any], None, None]:
    """
        Run the production-app driver once and yield its observations.

        :yields: Dict of observations recorded by the driver.
    """
    workdir = tempfile.mkdtemp(prefix="pyc-p26e-")
    try:
        def _write(name: str, content: bytes) -> str:
            path = os.path.join(workdir, name)
            with open(path, "wb") as handle:
                handle.write(content)
            # Key material is private to the service user; the KEK
            # loader refuses a file others can read.
            os.chmod(path, 0o600)
            return path

        presence_dir = os.path.join(workdir, "presence")
        os.makedirs(presence_dir)
        env = os.environ.copy()
        for name in list(env):
            if name.startswith("PYCHESTRATE_"):
                env.pop(name)
        env.update({
            "PYCHESTRATE_RUNTIME_ENVIRONMENT": "testing",
            "PYCHESTRATE_AUTO_CREATE_SCHEMA": "true",
            "PYCHESTRATE_DATABASE_URL": "sqlite:///" + os.path.join(workdir, "e2e.sqlite"),
            "PYCHESTRATE_PRESENCE_DIR": presence_dir,
            "PYCHESTRATE_KEK_SOURCE": "file",
            "PYCHESTRATE_KEK_ID": "e2e-kek",
            "PYCHESTRATE_KEK_FILE_PATH": _write("kek", b"\x5a" * 32),
            "PYCHESTRATE_PASSWORD_PEPPER_SOURCE": "file",
            "PYCHESTRATE_PASSWORD_PEPPER_FILE_PATH": _write("pepper", b"\x3c" * 32),
            "PYCHESTRATE_ENROLLMENT_CA_SOURCE": "file",
            "PYCHESTRATE_ENROLLMENT_CA_FILE_PATH": _write(
                "enrollment-ca.pem", ca_adapter.generate_dev_ca(common_name="p26e Enrollment CA")),
            "PYCHESTRATE_ENROLLMENT_CA_ID": "e2e-ca",
            "PYCHESTRATE_ENVELOPE_SIGNING_KEY_SOURCE": "file",
            "PYCHESTRATE_ENVELOPE_SIGNING_KEY_ID": "e2e-envelope-ed25519",
            "PYCHESTRATE_ENVELOPE_SIGNING_KEY_FILE_PATH": _write(
                "envelope-signing-key", base64.b64encode(os.urandom(32))),
            "PYCHESTRATE_RESULT_PRESIGN_SECRET": "p26e-presign-secret",
            # Test mode completes the setup wizard at boot; otherwise the
            # setup gate redirects every request to /setup/unlock.
            "PYCHESTRATE_TEST_MODE": "true",
            "PYCHESTRATE_TEST_ADMIN_LOGIN": "p26e-admin",
            "PYCHESTRATE_TEST_ADMIN_EMAIL": "p26e-admin@example.invalid",
            "PYCHESTRATE_TEST_ADMIN_PASSWORD": "p26e-admin-password-0123456789",
        })
        process = subprocess.run(
            [sys.executable, "-c", _DRIVER_SCRIPT.format(repo_root=_repo_root())],
            cwd=_repo_root(), env=env, capture_output=True, text=True, timeout=300,
        )
        observations: Dict[str, Any] = {"_stdout_tail": process.stdout[-3000:], "_stderr_tail": process.stderr[-3000:]}
        for line in process.stdout.splitlines():
            if line.startswith("RESULTS: "):
                observations.update(json.loads(line[len("RESULTS: "):]))
        yield observations
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    return


testbase.originate.parameter(
    create_pod_job_loop_observations,
    identifier="loop",
    life_span=ResourceLifespan.Package,
)


def _observed(loop: Dict[str, Any], key: str) -> Any:
    if key not in loop:
        raise AssertionError("driver recorded no '{}'; stderr tail:\n{}".format(key, loop.get("_stderr_tail")))
    rtnval = loop[key]
    return rtnval


def test_pod_redeems_its_enrollment_token(loop: Dict[str, Any]):
    """
    **Feature: pod job loop end to end (ORG-F01)**
    **Property: the pod's redemption with a real CSR answers 200.**
    """
    testbase.assert_equal(_observed(loop, "redeem_status"), 200)
    return


def test_issued_certificate_carries_the_client_id(loop: Dict[str, Any]):
    """
    **Feature: pod job loop end to end (E2E-04)**
    **Property: the certificate returned as PEM has CN = client id.**
    """
    testbase.assert_equal(_observed(loop, "cert_cn_equals_client_id"), True)
    return


def test_heartbeat_with_proxy_verified_identity_is_accepted(loop: Dict[str, Any]):
    """
    **Feature: pod job loop end to end (E2E-03)**
    **Property: through the production WSGI app the heartbeat with the
    loopback proxy's X-Client-Cert headers answers 204.**
    """
    testbase.assert_equal(_observed(loop, "heartbeat_status"), 204)
    return


def test_heartbeat_from_an_untrusted_peer_is_refused(loop: Dict[str, Any]):
    """
    **Feature: pod job loop end to end (E2E-03)**
    **Property: the same headers from a non-proxy address answer 401.**
    """
    testbase.assert_equal(_observed(loop, "heartbeat_untrusted_peer_status"), 401)
    return


def test_underscore_certificate_header_is_not_an_identity(loop: Dict[str, Any]):
    """
    **Feature: pod job loop end to end (E2E-03)**
    **Property: a client-supplied SSL_CLIENT_S_DN_CN request header (an
    HTTP_* environ key) is never taken as an identity.**
    """
    testbase.assert_equal(_observed(loop, "heartbeat_underscore_header_status"), 401)
    return


def test_pod_capability_advertisement_is_accepted(loop: Dict[str, Any]):
    """
    **Feature: pod job loop end to end (E2E-18)**
    **Property: PUT /clients/{id}/capabilities with the pod identity
    answers 200.**
    """
    testbase.assert_equal(_observed(loop, "capabilities_status"), 200)
    return


def test_enrollment_registers_the_pod(loop: Dict[str, Any]):
    """
    **Feature: pod job loop end to end (ORG-F01)**
    **Property: the enrolled client holds one REGISTERED pod
    registration.**
    """
    testbase.assert_equal(_observed(loop, "registered_pods"), 1)
    return


def test_enrolled_pod_is_the_dispatch_candidate(loop: Dict[str, Any]):
    """
    **Feature: pod job loop end to end (ORG-F01)**
    **Property: candidate resolution for the project returns exactly the
    enrolled client.**
    """
    candidates = _observed(loop, "candidate_client_ids")
    testbase.assert_equal(len(candidates), 1)
    return


def test_pod_long_poll_receives_the_triggered_job(loop: Dict[str, Any]):
    """
    **Feature: pod job loop end to end (ORG-F01)**
    **Property: the pod's dispatches:next long-poll answers 200 with the
    envelope of the RPA job just triggered, addressed to this client.**
    """
    testbase.assert_equal(
        (_observed(loop, "dispatch_status"), _observed(loop, "dispatch_run_id") == _observed(loop, "job_id"),
         _observed(loop, "dispatch_client_id_matches"), _observed(loop, "dispatch_job_kind")),
        (200, True, True, "rpa"),
    )
    return


def test_delivered_envelope_is_signed_with_the_published_key(loop: Dict[str, Any]):
    """
    **Feature: pod job loop end to end (LD-02)**
    **Property: the envelope is signed with the provisioned signing key,
    which the pod can fetch with its certificate identity.**
    """
    testbase.assert_equal(
        (_observed(loop, "dispatch_signature_key_id"), _observed(loop, "signing_key_ids")),
        ("e2e-envelope-ed25519", ["e2e-envelope-ed25519"]),
    )
    return
