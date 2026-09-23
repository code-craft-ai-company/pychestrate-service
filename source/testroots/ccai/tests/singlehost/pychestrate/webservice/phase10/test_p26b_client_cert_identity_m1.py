"""
.. module:: test_p26b_client_cert_identity_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The verified pod client-certificate identity reaches the
               request handlers (E2E-03).

.. moduleauthor:: Code Craft AI LLC

Covers :mod:`clients.mtls_identity`:

* which requests carry a verified identity (trusted proxy headers,
  server-populated environ keys) and which do not (untrusted peers,
  failed or missing verification);
* the client-certificate headers never reach the application;
* the identity arrives as ``request.mtls_client_cn`` through a real
  webworks ``WSGIApplication`` -- whose ``Request`` carries no environ
  -- and the pod heartbeat route accepts it;
* through a real gunicorn server the hyphenated ``X-Client-Cert-CN``
  header works while the old underscore ``SSL_CLIENT_S_DN_CN`` header
  is dropped by gunicorn.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import http.client
import json
import os
import socket
import subprocess
import sys
import tempfile
import textwrap
import time

from typing import Any, Callable, Dict, Generator, List, Optional

from ccai import testbase
from ccai.testbase.resourcelifespan import ResourceLifespan
from ccai.webworks.routing.middleware import MiddlewarePipeline
from ccai.webworks.wsgi.application import create_wsgi_application

from ccai.pychestrate.webservice.clients import mtls_identity
from ccai.pychestrate.webservice.clients.mtls_identity import (
    ClientCertificateIdentityMiddleware,
    ClientCertificateIdentityWsgiMiddleware,
    current_verified_client_cn,
    parse_trusted_proxy_addresses,
    resolve_verified_client_cn,
)
from ccai.pychestrate.webservice.clients.restapi.v1 import client_dispatch_routes


_CLIENT_ID = "6f1f8f0e-6d0b-4f7e-9a53-3c1f1b3a9d21"
_LOOPBACK = parse_trusted_proxy_addresses(raw=None)


def _environ(**overrides: Any) -> Dict[str, Any]:
    """
        A minimal PEP-3333 environ for a pod heartbeat from 127.0.0.1.
    """
    environ: Dict[str, Any] = {
        "REQUEST_METHOD": "GET",
        "PATH_INFO": "/api/v1/clients/{}/heartbeat".format(_CLIENT_ID),
        "QUERY_STRING": "",
        "SERVER_NAME": "pyc.invalid",
        "SERVER_PORT": "8888",
        "SERVER_PROTOCOL": "HTTP/1.1",
        "REMOTE_ADDR": "127.0.0.1",
        "wsgi.url_scheme": "http",
        "wsgi.input": None,
    }
    environ.update(overrides)
    rtnval = environ
    return rtnval


def _proxy_headers(*, cn: str = _CLIENT_ID, verify: str = "SUCCESS") -> Dict[str, str]:
    rtnval = {
        "HTTP_X_CLIENT_CERT_CN": cn,
        "HTTP_X_CLIENT_CERT_VERIFY": verify,
    }
    return rtnval


# ---------------------------------------------------------------------------
# Identity resolution
# ---------------------------------------------------------------------------


def test_trusted_proxy_headers_with_success_yield_the_cn():
    """
    **Feature: pod client-certificate identity (E2E-03)**
    **Property: X-Client-Cert-CN from a trusted proxy with
    X-Client-Cert-Verify SUCCESS is the verified identity.**
    """
    cn = resolve_verified_client_cn(environ=_environ(**_proxy_headers()), trusted_proxies=_LOOPBACK)
    testbase.assert_equal(cn, _CLIENT_ID)
    return


def test_headers_from_an_untrusted_peer_are_ignored():
    """
    **Feature: pod client-certificate identity (E2E-03)**
    **Property: the same headers from a peer that is not a trusted proxy
    establish no identity (a client cannot claim one directly).**
    """
    environ = _environ(REMOTE_ADDR="10.20.30.40", **_proxy_headers())
    cn = resolve_verified_client_cn(environ=environ, trusted_proxies=_LOOPBACK)
    testbase.assert_equal(cn, None)
    return


def test_headers_without_successful_verification_are_ignored():
    """
    **Feature: pod client-certificate identity (E2E-03)**
    **Property: a verify result other than SUCCESS (NONE, FAILED:...)
    establishes no identity even from a trusted proxy.**
    """
    results = []
    for verify in ("NONE", "FAILED:certificate has expired", ""):
        environ = _environ(**_proxy_headers(verify=verify))
        results.append(resolve_verified_client_cn(environ=environ, trusted_proxies=_LOOPBACK))
    testbase.assert_equal(results, [None, None, None])
    return


def test_server_populated_environ_keys_yield_the_cn():
    """
    **Feature: pod client-certificate identity (E2E-03)**
    **Property: SSL_CLIENT_S_DN_CN put in the environ by a TLS-terminating
    server (not a request header) is the verified identity.**
    """
    environ = _environ(SSL_CLIENT_S_DN_CN=_CLIENT_ID, SSL_CLIENT_VERIFY="SUCCESS")
    cn = resolve_verified_client_cn(environ=environ, trusted_proxies=tuple())
    testbase.assert_equal(cn, _CLIENT_ID)
    return


def test_trusted_proxy_networks_accept_cidr_entries():
    """
    **Feature: pod client-certificate identity (E2E-03)**
    **Property: PYCHESTRATE_TRUSTED_PROXY_ADDRESSES accepts CIDR
    networks, so a proxy inside 10.0.0.0/8 is trusted.**
    """
    trusted = parse_trusted_proxy_addresses(raw="10.0.0.0/8, 127.0.0.1")
    environ = _environ(REMOTE_ADDR="10.1.2.3", **_proxy_headers())
    testbase.assert_equal(resolve_verified_client_cn(environ=environ, trusted_proxies=trusted), _CLIENT_ID)
    return


def test_none_trusts_no_proxy():
    """
    **Feature: pod client-certificate identity (E2E-03)**
    **Property: ``none`` disables header trust, even from loopback.**
    """
    trusted = parse_trusted_proxy_addresses(raw="none")
    cn = resolve_verified_client_cn(environ=_environ(**_proxy_headers()), trusted_proxies=trusted)
    testbase.assert_equal((trusted, cn), (tuple(), None))
    return


def test_ipv4_mapped_loopback_peer_is_trusted():
    """
    **Feature: pod client-certificate identity (E2E-03)**
    **Property: an IPv4-mapped IPv6 loopback peer (::ffff:127.0.0.1) is
    the trusted loopback proxy.**
    """
    environ = _environ(REMOTE_ADDR="::ffff:127.0.0.1", **_proxy_headers())
    testbase.assert_equal(resolve_verified_client_cn(environ=environ, trusted_proxies=_LOOPBACK), _CLIENT_ID)
    return


def test_invalid_trusted_proxy_entry_is_rejected():
    """
    **Feature: pod client-certificate identity (E2E-03)**
    **Property: a malformed PYCHESTRATE_TRUSTED_PROXY_ADDRESSES entry is a
    configuration error naming the entry.**
    """
    message = ""
    try:
        parse_trusted_proxy_addresses(raw="127.0.0.1, nginx.local")
    except ValueError as xcpt:
        message = str(xcpt)
    testbase.assert_equal("nginx.local" in message, True)
    return


# ---------------------------------------------------------------------------
# WSGI + pipeline middleware
# ---------------------------------------------------------------------------


def _capture_app(captured: Dict[str, Any]) -> Callable:
    def _app(environ: Dict[str, Any], start_response: Callable) -> List[bytes]:
        captured["cn"] = current_verified_client_cn()
        captured["keys"] = sorted(key for key in environ if "CLIENT_CERT" in key)
        start_response("200 OK", [("Content-Type", "text/plain")])
        rtnval = [b"ok"]
        return rtnval
    rtnval = _app
    return rtnval


def test_wsgi_middleware_strips_client_certificate_headers():
    """
    **Feature: pod client-certificate identity (E2E-03)**
    **Property: the wrapped application never sees X-Client-Cert-*
    headers, whether or not they came from a trusted proxy.**
    """
    captured: Dict[str, Any] = {}
    middleware = ClientCertificateIdentityWsgiMiddleware(app=_capture_app(captured), trusted_proxies=_LOOPBACK)
    seen = []
    for remote_addr in ("127.0.0.1", "10.20.30.40"):
        list(middleware(_environ(REMOTE_ADDR=remote_addr, **_proxy_headers()), lambda *a: None))
        seen.append(captured["keys"])
    testbase.assert_equal(seen, [[], []])
    return


def test_wsgi_middleware_publishes_identity_only_during_the_request():
    """
    **Feature: pod client-certificate identity (E2E-03)**
    **Property: the verified identity is published while the wrapped
    application runs and is gone afterwards.**
    """
    captured: Dict[str, Any] = {}
    middleware = ClientCertificateIdentityWsgiMiddleware(app=_capture_app(captured), trusted_proxies=_LOOPBACK)
    list(middleware(_environ(**_proxy_headers()), lambda *a: None))
    testbase.assert_equal((captured["cn"], current_verified_client_cn()), (_CLIENT_ID, None))
    return


def test_wsgi_middleware_publishes_identity_to_a_lazy_application():
    """
    **Feature: pod client-certificate identity (E2E-03)**
    **Property: an application that only runs when its body is iterated
    (a generator, like webworks' WSGIApplication) still sees the
    identity.**
    """
    captured: Dict[str, Any] = {}

    def _lazy_app(environ: Dict[str, Any], start_response: Callable):
        captured["cn"] = current_verified_client_cn()
        start_response("200 OK", [])
        yield b"ok"

    middleware = ClientCertificateIdentityWsgiMiddleware(app=_lazy_app, trusted_proxies=_LOOPBACK)
    list(middleware(_environ(**_proxy_headers()), lambda *a: None))
    testbase.assert_equal(captured["cn"], _CLIENT_ID)
    return


class _PlainRequest:
    pass


def test_pipeline_middleware_clears_an_identity_the_request_did_not_verify():
    """
    **Feature: pod client-certificate identity (E2E-03)**
    **Property: with no verified identity published, the pipeline
    middleware sets request.mtls_client_cn to None -- only the verified
    identity can ever populate it.**
    """
    request = _PlainRequest()
    request.mtls_client_cn = "forged-identity"
    seen = []
    ClientCertificateIdentityMiddleware()(request, lambda req: seen.append(req.mtls_client_cn))
    testbase.assert_equal(seen, [None])
    return


def _webworks_heartbeat_app(*, trusted_proxies) -> Callable:
    """
        A real webworks WSGIApplication whose handler runs the identity
        pipeline middleware and then the real pod heartbeat route (no
        database session bound, so it answers 204 once the identity
        checks pass), wrapped in the WSGI identity middleware.
    """
    pipeline = MiddlewarePipeline()
    pipeline.add(ClientCertificateIdentityMiddleware(), name="identity", position="start")

    def _handler(request):
        request.path_params = {"client_id": _CLIENT_ID}
        rtnval = pipeline.execute(request, client_dispatch_routes.handle_client_heartbeat)
        if not hasattr(rtnval, "content_type"):
            rtnval.content_type = None
        return rtnval

    wsgi_app = create_wsgi_application(config={"handler": _handler})
    rtnval = ClientCertificateIdentityWsgiMiddleware(app=wsgi_app, trusted_proxies=trusted_proxies)
    return rtnval


def _drive(app: Callable, environ: Dict[str, Any]) -> str:
    status: Dict[str, str] = {}

    def _start_response(line, headers, exc_info=None):
        status["line"] = line
        return lambda chunk: None

    body = app(environ, _start_response)
    for _chunk in body:
        pass
    close = getattr(body, "close", None)
    if callable(close):
        close()
    rtnval = status.get("line", "")
    return rtnval


def test_heartbeat_through_webworks_accepts_proxy_verified_identity():
    """
    **Feature: pod client-certificate identity (E2E-03)**
    **Property: through a real webworks WSGIApplication (whose Request
    carries no environ) the pod heartbeat answers 204 for a request that
    a trusted proxy verified -- it answered 401 for every header
    spelling before.**
    """
    app = _webworks_heartbeat_app(trusted_proxies=_LOOPBACK)
    status_line = _drive(app, _environ(**_proxy_headers()))
    testbase.assert_equal(status_line.split(" ")[0], "204")
    return


def test_heartbeat_through_webworks_refuses_an_unverified_request():
    """
    **Feature: pod client-certificate identity (E2E-03)**
    **Property: the same request from an untrusted peer answers 401.**
    """
    app = _webworks_heartbeat_app(trusted_proxies=_LOOPBACK)
    status_line = _drive(app, _environ(REMOTE_ADDR="10.20.30.40", **_proxy_headers()))
    testbase.assert_equal(status_line.split(" ")[0], "401")
    return


# ---------------------------------------------------------------------------
# Through gunicorn
# ---------------------------------------------------------------------------


_PROBE_APP_SOURCE = textwrap.dedent('''\
    import json

    from ccai.pychestrate.webservice.clients.mtls_identity import (
        ClientCertificateIdentityWsgiMiddleware,
        current_verified_client_cn,
        parse_trusted_proxy_addresses,
    )


    def _inner(environ, start_response):
        body = json.dumps({"cn": current_verified_client_cn()}).encode("utf-8")
        start_response("200 OK", [("Content-Type", "application/json"),
                                  ("Content-Length", str(len(body)))])
        return [body]


    app = ClientCertificateIdentityWsgiMiddleware(
        app=_inner, trusted_proxies=parse_trusted_proxy_addresses(raw="127.0.0.1,::1"))
''')


def _free_port() -> int:
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", 0))
    rtnval = probe.getsockname()[1]
    probe.close()
    return rtnval


@testbase.register.resource_factory()
def create_gunicorn_identity_probe(constraints: Optional[Dict[str, Any]] = None) -> Generator[int, None, None]:
    """
        Serve a probe WSGI app wrapped in the identity middleware with
        a real gunicorn on a free loopback port.

        :yields: The port gunicorn listens on.
    """
    workdir = tempfile.mkdtemp(prefix="pyc-p26b-")
    with open(os.path.join(workdir, "identity_probe_app.py"), "w", encoding="utf-8") as handle:
        handle.write(_PROBE_APP_SOURCE)
    port = _free_port()
    process = subprocess.Popen(
        [sys.executable, "-m", "gunicorn", "identity_probe_app:app", "--chdir", workdir,
         "--bind", "127.0.0.1:{}".format(port), "--workers", "1", "--threads", "2"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=dict(os.environ),
    )
    try:
        deadline = time.time() + 20
        while time.time() < deadline:
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
                break
            except OSError:
                time.sleep(0.2)
        yield port
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
    return


testbase.originate.parameter(
    create_gunicorn_identity_probe,
    identifier="gunicorn_port",
    life_span=ResourceLifespan.Package,
)


def _gunicorn_cn(*, port: int, headers: Dict[str, str]) -> Optional[str]:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        connection.request("GET", "/api/v1/clients/{}/heartbeat".format(_CLIENT_ID), headers=headers)
        rtnval = json.loads(connection.getresponse().read().decode("utf-8")).get("cn")
    finally:
        connection.close()
    return rtnval


def test_gunicorn_delivers_the_hyphenated_certificate_headers(gunicorn_port: int):
    """
    **Feature: pod client-certificate identity (E2E-03)**
    **Property: through gunicorn, X-Client-Cert-CN / X-Client-Cert-Verify
    from the (loopback) proxy become the verified identity.**
    """
    cn = _gunicorn_cn(port=gunicorn_port, headers={
        mtls_identity.CLIENT_CERT_CN_HEADER: _CLIENT_ID,
        mtls_identity.CLIENT_CERT_VERIFY_HEADER: "SUCCESS",
    })
    testbase.assert_equal(cn, _CLIENT_ID)
    return


def test_gunicorn_drops_the_underscore_header_spelling(gunicorn_port: int):
    """
    **Feature: pod client-certificate identity (E2E-03)**
    **Property: the SSL_CLIENT_S_DN_CN / SSL_CLIENT_VERIFY header spelling
    the deployment used before never reaches the app through gunicorn --
    the reason the proxy must send the hyphenated headers.**
    """
    cn = _gunicorn_cn(port=gunicorn_port, headers={
        "SSL_CLIENT_S_DN_CN": _CLIENT_ID,
        "SSL_CLIENT_VERIFY": "SUCCESS",
    })
    testbase.assert_equal(cn, None)
    return
