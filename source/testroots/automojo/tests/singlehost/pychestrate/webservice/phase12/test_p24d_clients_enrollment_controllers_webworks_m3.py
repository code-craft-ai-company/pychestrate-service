"""
.. module:: test_p24d_clients_enrollmentblueprints_webworks_m3
    :synopsis: Tests for P24d — clients + enrollment controllers on webworks.

Exercises the migrated clients (admin) and enrollment (admin + agent)
controllers end-to-end through the webworks dispatcher and the
:class:`DbSessionMiddleware`. Covers happy paths, 503 fallback when the
middleware is absent, 404 / 400 / 409 error responses, query-param
routing, and path-param routing.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import json

from typing import Dict, Tuple

from automojo import testbase

from automojo.webworks.devexp.testing.testclient import TestClient
from automojo.webworks.routing.dispatcher import Dispatcher
from automojo.webworks.routing.middleware import MiddlewarePipeline
from automojo.webworks.routing.request import Request
from automojo.webworks.routing.router import Router

from automojo.pychestrate.core.defaults import new_uuid

from automojo.pychestrate.webservice.clients.enrollment.factories.identity_verifier import (
    EnrollmentPayload,
)
from automojo.pychestrate.webservice.clients.enrollment.service import (
    issue_enrollment_token,
    redeem_enrollment_token,
)
from automojo.pychestrate.webservice.clients.registry.service import (
    register_client,
)
from automojo.pychestrate.webservice.clients.restapi.v1 import (
    clientsblueprint,
    enrollmentblueprint,
)
from automojo.pychestrate.webservice.dbsessionmiddleware import (
    DbSessionMiddleware,
)
from automojo.pychestrate.webservice.secrets.secret_bytes import SecretBytes
from automojo.pychestrate.webservice.security.auth.pepper_loader import (
    reset_active_pepper_for_testing,
    set_active_pepper,
)

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
    reset_phase1_runtime,
)


def _build_app_callable(
        *,
        engine,
        blueprint_cls,
        install_db_session_middleware: bool = True,
    ):
    """
        Build a ``(method, path, headers, body) -> (status, headers,
        body)`` callable that dispatches into a webworks pipeline
        wired with the supplied blueprint.
    """
    from sqlalchemy.orm import sessionmaker

    session_factory = sessionmaker(bind=engine)

    router = Router()
    blueprint_cls.register(router=router)

    pipeline = MiddlewarePipeline()
    if install_db_session_middleware is True:
        middleware = DbSessionMiddleware(session_factory=session_factory)
        pipeline.add(middleware=middleware, name=middleware.name)

    dispatcher = Dispatcher(router=router, pipeline=pipeline)

    def _app_callable(
            method: str,
            path: str,
            headers: Dict[str, str],
            body: bytes,
        ) -> Tuple[int, Dict[str, str], bytes]:
        if "?" in path:
            path_only, _, query_string_str = path.partition("?")
        else:
            path_only = path
            query_string_str = ""
        request = Request(
            method=method,
            path=path_only,
            query_string=query_string_str.encode("utf-8"),
            headers=headers,
            body=body,
        )
        response = dispatcher.dispatch(request=request)
        rtnval = (response.status_code, dict(response.headers), response.body)
        return rtnval

    return _app_callable


def _setup() -> Tuple[object, object]:
    """
        Reset phase-1 runtime, install the password pepper (so
        enrollment-issue / revoke / redeem can run), and build a fresh
        in-memory engine + session.
    """
    reset_phase1_runtime()
    reset_active_pepper_for_testing()
    set_active_pepper(pepper=SecretBytes(b"p24d-test-pepper"))
    engine, session = build_in_memory_session()
    rtnval = (engine, session)
    return rtnval


def _seed_two_clients(*, session) -> Tuple[str, str, str]:
    """
        Seed two clients in different projects.

        :returns: ``(project_a, client_a_id, client_b_id)``.
    """
    project_a = new_uuid()
    project_b = new_uuid()
    client_a = register_client(
        db_session=session,
        project_id=project_a,
        pod_name="pod-a",
        bearer_token_hash=None,
        agent_version="1.0.0",
        transport_name="http",
    )
    client_b = register_client(
        db_session=session,
        project_id=project_b,
        pod_name="pod-b",
        bearer_token_hash=None,
        agent_version="1.0.0",
        transport_name="http",
    )
    session.commit()
    rtnval = (project_a, str(client_a.client_id), str(client_b.client_id))
    return rtnval


# =====================================
# clientsblueprint
# =====================================

def test_clients_list_returns_all_when_no_filters_supplied():
    """
    **Feature: P24d clientsblueprint migration (M3)**
    **Property: GET /api/v1/clients with no query string returns
    every registered client view.**
    """
    engine, session = _setup()
    try:
        _project_a, client_a_id, client_b_id = _seed_two_clients(
            session=session,
        )

        app_callable = _build_app_callable(
            engine=engine,
            blueprint_cls=clientsblueprint.ClientsBlueprint,
        )
        client = TestClient(app=app_callable)

        response = client.get(path="/api/v1/clients")
        testbase.assert_equal(response.status_code, 200)
        body = json.loads(response.body.decode("utf-8"))
        ids = [entry["client_id"] for entry in body]
        testbase.assert_equal(client_a_id in ids, True)
        testbase.assert_equal(client_b_id in ids, True)
    finally:
        session.close()
    return


def test_clients_list_filters_by_project_id_query_param():
    """
    **Feature: P24d clientsblueprint migration (M3)**
    **Property: GET /api/v1/clients?project_id=... reads the query
    param via request.query_params and filters down to the matching
    client(s) only.**
    """
    engine, session = _setup()
    try:
        project_a, client_a_id, _client_b_id = _seed_two_clients(
            session=session,
        )

        app_callable = _build_app_callable(
            engine=engine,
            blueprint_cls=clientsblueprint.ClientsBlueprint,
        )
        client = TestClient(app=app_callable)

        response = client.get(
            path="/api/v1/clients",
            params={"project_id": project_a},
        )
        testbase.assert_equal(response.status_code, 200)
        body = json.loads(response.body.decode("utf-8"))
        testbase.assert_equal(len(body), 1)
        testbase.assert_equal(body[0]["client_id"], client_a_id)
    finally:
        session.close()
    return


def test_clients_detail_returns_404_for_unknown_client_id():
    """
    **Feature: P24d clientsblueprint migration (M3)**
    **Property: GET /api/v1/clients/{unknown} surfaces
    ClientNotFoundError as HTTP 404.**
    """
    engine, session = _setup()
    try:
        app_callable = _build_app_callable(
            engine=engine,
            blueprint_cls=clientsblueprint.ClientsBlueprint,
        )
        client = TestClient(app=app_callable)

        response = client.get(
            path="/api/v1/clients/00000000-0000-4000-8000-000000000099",
        )
        testbase.assert_equal(response.status_code, 404)
    finally:
        session.close()
    return


def test_clients_revoke_flips_status_and_returns_revoked_envelope():
    """
    **Feature: P24d clientsblueprint migration (M3)**
    **Property: POST /api/v1/clients/{id}/revoke with a valid reason
    returns 200 with status=revoked and persists the change so the
    detail endpoint reflects it.**
    """
    engine, session = _setup()
    try:
        _project_a, client_a_id, _client_b_id = _seed_two_clients(
            session=session,
        )

        app_callable = _build_app_callable(
            engine=engine,
            blueprint_cls=clientsblueprint.ClientsBlueprint,
        )
        client = TestClient(app=app_callable)

        revoke_response = client.post(
            path="/api/v1/clients/{}/revoke".format(client_a_id),
            json={"reason": "ROTATED", "note": "rolling key"},
        )
        testbase.assert_equal(revoke_response.status_code, 200)
        revoke_body = json.loads(revoke_response.body.decode("utf-8"))
        testbase.assert_equal(revoke_body["client_id"], client_a_id)
        testbase.assert_equal(revoke_body["status"], "revoked")

        detail_response = client.get(
            path="/api/v1/clients/{}".format(client_a_id),
        )
        testbase.assert_equal(detail_response.status_code, 200)
        detail_body = json.loads(detail_response.body.decode("utf-8"))
        testbase.assert_equal(detail_body["status"], "REVOKED")
    finally:
        session.close()
    return


def test_clients_revoke_returns_400_for_unknown_reason():
    """
    **Feature: P24d clientsblueprint migration (M3)**
    **Property: An unknown revocation reason surfaces SemanticError
    as HTTP 400.**
    """
    engine, session = _setup()
    try:
        _project_a, client_a_id, _client_b_id = _seed_two_clients(
            session=session,
        )

        app_callable = _build_app_callable(
            engine=engine,
            blueprint_cls=clientsblueprint.ClientsBlueprint,
        )
        client = TestClient(app=app_callable)

        response = client.post(
            path="/api/v1/clients/{}/revoke".format(client_a_id),
            json={"reason": "no-such-reason"},
        )
        testbase.assert_equal(response.status_code, 400)
    finally:
        session.close()
    return


def test_clients_returns_503_when_db_session_middleware_absent():
    """
    **Feature: P24d clientsblueprint migration (M3)**
    **Property: With DbSessionMiddleware not installed, a list call
    returns 503.**
    """
    engine, session = _setup()
    try:
        app_callable = _build_app_callable(
            engine=engine,
            blueprint_cls=clientsblueprint.ClientsBlueprint,
            install_db_session_middleware=False,
        )
        client = TestClient(app=app_callable)

        response = client.get(path="/api/v1/clients")
        testbase.assert_equal(response.status_code, 503)
    finally:
        session.close()
    return


# =====================================
# enrollmentblueprint
# =====================================

def test_enrollment_issue_returns_201_with_secret():
    """
    **Feature: P24d enrollmentblueprint migration (M3)**
    **Property: POST /api/v1/enrollment-tokens issues a token and
    returns the secret + token_id at status 201.**
    """
    engine, session = _setup()
    try:
        app_callable = _build_app_callable(
            engine=engine,
            blueprint_cls=enrollmentblueprint.EnrollmentBlueprint,
        )
        client = TestClient(app=app_callable)

        response = client.post(
            path="/api/v1/enrollment-tokens",
            json={
                "project_id": new_uuid(),
                "pod_name": "pod-x",
                "ttl_seconds": 600,
                "one_shot": True,
            },
        )
        testbase.assert_equal(response.status_code, 201)
        body = json.loads(response.body.decode("utf-8"))
        testbase.assert_equal("secret" in body, True)
        testbase.assert_equal(len(body["secret"]) > 0, True)
        testbase.assert_equal("token_id" in body, True)
        testbase.assert_equal(body["pod_name"], "pod-x")
    finally:
        session.close()
    return


def test_enrollment_issue_returns_400_for_zero_ttl():
    """
    **Feature: P24d enrollmentblueprint migration (M3)**
    **Property: ttl_seconds <= 0 surfaces as HTTP 400.**
    """
    engine, session = _setup()
    try:
        app_callable = _build_app_callable(
            engine=engine,
            blueprint_cls=enrollmentblueprint.EnrollmentBlueprint,
        )
        client = TestClient(app=app_callable)

        response = client.post(
            path="/api/v1/enrollment-tokens",
            json={
                "project_id": new_uuid(),
                "pod_name": "pod-x",
                "ttl_seconds": 0,
            },
        )
        testbase.assert_equal(response.status_code, 400)
    finally:
        session.close()
    return


def test_enrollment_list_returns_empty_when_none_issued():
    """
    **Feature: P24d enrollmentblueprint migration (M3)**
    **Property: GET /api/v1/enrollment-tokens returns an empty list
    when no tokens have been issued.**
    """
    engine, session = _setup()
    try:
        app_callable = _build_app_callable(
            engine=engine,
            blueprint_cls=enrollmentblueprint.EnrollmentBlueprint,
        )
        client = TestClient(app=app_callable)

        response = client.get(path="/api/v1/enrollment-tokens")
        testbase.assert_equal(response.status_code, 200)
        body = json.loads(response.body.decode("utf-8"))
        testbase.assert_equal(body, [])
    finally:
        session.close()
    return


def test_enrollment_delete_unknown_token_returns_404():
    """
    **Feature: P24d enrollmentblueprint migration (M3)**
    **Property: DELETE /api/v1/enrollment-tokens/{unknown} surfaces
    EnrollmentTokenNotFoundError as HTTP 404.**
    """
    engine, session = _setup()
    try:
        app_callable = _build_app_callable(
            engine=engine,
            blueprint_cls=enrollmentblueprint.EnrollmentBlueprint,
        )
        client = TestClient(app=app_callable)

        response = client.delete(
            path="/api/v1/enrollment-tokens/00000000-0000-4000-8000-0000000000ff",
        )
        testbase.assert_equal(response.status_code, 404)
    finally:
        session.close()
    return


def test_enrollment_redeem_round_trips_through_pipeline():
    """
    **Feature: P24d enrollmentblueprint migration (M3)**
    **Property: After issuing a token, POST /api/v1/enrollment-tokens
    /redeem with the secret + payload returns 200 with a bearer
    token; ClientAlreadyExistsError surfaces as 409 on the second
    redemption with the same pod_name.**
    """
    engine, session = _setup()
    try:
        project_id = new_uuid()
        # Issue at the service layer so the controller redeem path is
        # the only thing under test.
        issued = issue_enrollment_token(
            db_session=session,
            project_id=project_id,
            pod_name="pod-redeem",
            ttl_seconds=600,
            one_shot=False,
            issued_by=None,
        )
        session.commit()

        app_callable = _build_app_callable(
            engine=engine,
            blueprint_cls=enrollmentblueprint.EnrollmentBlueprint,
        )
        client = TestClient(app=app_callable)

        first = client.post(
            path="/api/v1/enrollment-tokens/redeem",
            json={
                "secret": issued.secret,
                "pod_name": "pod-redeem",
                "agent_version": "1.0.0",
                "transport_name": "http",
            },
        )
        testbase.assert_equal(first.status_code, 200)
        first_body = json.loads(first.body.decode("utf-8"))
        testbase.assert_equal(len(first_body["bearer_token"]) > 0, True)
        testbase.assert_equal(first_body["pod_name"], "pod-redeem")

        # Second redemption with the same pod_name → ClientAlreadyExistsError
        # → 409.
        second = client.post(
            path="/api/v1/enrollment-tokens/redeem",
            json={
                "secret": issued.secret,
                "pod_name": "pod-redeem",
                "agent_version": "1.0.0",
                "transport_name": "http",
            },
        )
        testbase.assert_equal(second.status_code, 409)
    finally:
        session.close()
    return


def test_enrollment_revoke_client_identity_round_trips():
    """
    **Feature: P24d enrollmentblueprint migration (M3)**
    **Property: POST /api/v1/enrollment-tokens/clients/{id}/revoke
    accepts a reason, calls the service, and returns the revocation
    summary. An unknown reason returns 400 (not 500).**
    """
    engine, session = _setup()
    try:
        project_id = new_uuid()
        issued = issue_enrollment_token(
            db_session=session,
            project_id=project_id,
            pod_name="pod-rev",
            ttl_seconds=600,
            one_shot=True,
            issued_by=None,
        )
        session.commit()
        result = redeem_enrollment_token(
            db_session=session,
            secret=issued.secret,
            payload=EnrollmentPayload(
                pod_name="pod-rev",
                agent_version="1.0.0",
                transport_name="http",
                extras={},
                csr_pem=None,
            ),
        )
        session.commit()
        client_id = result.client_id

        app_callable = _build_app_callable(
            engine=engine,
            blueprint_cls=enrollmentblueprint.EnrollmentBlueprint,
        )
        api_client = TestClient(app=app_callable)

        ok_response = api_client.post(
            path="/api/v1/enrollment-tokens/clients/{}/revoke".format(
                client_id,
            ),
            json={"reason": "ROTATED", "note": "key roll"},
        )
        testbase.assert_equal(ok_response.status_code, 200)
        ok_body = json.loads(ok_response.body.decode("utf-8"))
        testbase.assert_equal(ok_body["client_id"], client_id)
        testbase.assert_equal(ok_body["status"], "revoked")
        testbase.assert_equal(ok_body["reason"], "ROTATED")

        bad_response = api_client.post(
            path="/api/v1/enrollment-tokens/clients/{}/revoke".format(
                client_id,
            ),
            json={"reason": "no-such-reason"},
        )
        testbase.assert_equal(bad_response.status_code, 400)
    finally:
        session.close()
    return
