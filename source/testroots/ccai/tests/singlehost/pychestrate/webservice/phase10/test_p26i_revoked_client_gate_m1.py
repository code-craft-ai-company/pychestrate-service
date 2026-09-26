"""
.. module:: test_p26i_revoked_client_gate_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: A revoked client's certificate is refused on the pod routes.

.. moduleauthor:: Code Craft AI LLC

Found live on staging (2026-09-26): after a client was revoked, its
certificate still verified at the TLS terminator and the pod routes
only compare the certificate CN with the path client id, so the
revoked pod's heartbeat answered 204 and its dispatch long-poll was
served. :class:`RevokedClientGateMiddleware` now answers 403 for a
revoked client.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json

from typing import Any, List

from ccai import testbase
from ccai.webworks.routing.middleware import MiddlewarePipeline

from ccai.pychestrate.core.defaults import new_uuid
from ccai.pychestrate.webservice.clients.enums import ClientStatus
from ccai.pychestrate.webservice.clients.mtls_identity import (
    install_client_certificate_identity,
)
from ccai.pychestrate.webservice.clients.registry.service import register_client
from ccai.pychestrate.webservice.clients.revoked_client_gate import (
    REVOKED_CLIENT_GATE_MIDDLEWARE_NAME,
    RevokedClientGateMiddleware,
)

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
    reset_phase1_runtime,
)


class _Request:
    def __init__(self, *, client_cn: Any, db_session: Any) -> None:
        self.mtls_client_cn = client_cn
        self.db_session = db_session
        self.path = "/api/v1/clients/{}/heartbeat".format(client_cn)
        return


def _client(*, session, status: ClientStatus) -> str:
    client = register_client(
        db_session=session, project_id=new_uuid(), pod_name="pod-{}".format(new_uuid()[:8]),
        bearer_token_hash=None, agent_version=None, transport_name=None,
    )
    client.status = status
    session.commit()
    rtnval = str(client.client_id)
    return rtnval


def _run_gate(*, client_cn: Any, db_session: Any):
    handled: List[Any] = []
    request = _Request(client_cn=client_cn, db_session=db_session)
    response = RevokedClientGateMiddleware()(request, lambda req: handled.append(req) or "handled")
    rtnval = (response, len(handled))
    return rtnval


def test_gate_refuses_a_revoked_client_with_403():
    """
    **Feature: revoked client gate**
    **Property: a request whose verified certificate names a REVOKED
    client is answered 403 problem+json and never reaches the route.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()
    client_id = _client(session=session, status=ClientStatus.REVOKED)

    response, handled = _run_gate(client_cn=client_id, db_session=session)
    body = json.loads(response.body)
    testbase.assert_equal(
        (response.status_code, handled, body["client_id"], "revoked" in body["detail"]),
        (403, 0, client_id, True),
    )
    return


def test_gate_passes_active_unknown_and_unidentified_requests():
    """
    **Feature: revoked client gate**
    **Property: an ACTIVE client, a client id with no row, a CN that is
    not a UUID, a request without a certificate and a request without a
    database session all reach the route (which applies its own
    identity checks).**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()
    active_id = _client(session=session, status=ClientStatus.ACTIVE)
    revoked_id = _client(session=session, status=ClientStatus.REVOKED)

    outcomes = [
        _run_gate(client_cn=active_id, db_session=session),
        _run_gate(client_cn=new_uuid(), db_session=session),
        _run_gate(client_cn="lab-pod-a", db_session=session),
        _run_gate(client_cn=None, db_session=session),
        _run_gate(client_cn=revoked_id, db_session=None),
    ]
    testbase.assert_equal(outcomes, [("handled", 1)] * 5)
    return


class _Dispatcher:
    def __init__(self) -> None:
        self.pipeline = MiddlewarePipeline()
        return


class _App:
    def __init__(self) -> None:
        self.dispatcher = _Dispatcher()
        return


def test_install_puts_the_gate_after_the_session_middleware():
    """
    **Feature: revoked client gate**
    **Property: installing the certificate identity also installs the
    gate, at the end of the pipeline -- after the session middleware
    (added at the start) has opened ``request.db_session``.**
    """
    app = _App()
    app.dispatcher.pipeline.add(lambda req, nxt: nxt(req), name="session", position="start")
    install_client_certificate_identity(
        app=app, wsgi_app=lambda environ, start_response: [], trusted_proxies=None,
    )
    names = app.dispatcher.pipeline.get_names()
    testbase.assert_equal(names[-1], REVOKED_CLIENT_GATE_MIDDLEWARE_NAME)
    testbase.assert_equal(names.index("session") < names.index(REVOKED_CLIENT_GATE_MIDDLEWARE_NAME), True)
    return
