"""
.. module:: test_p25d_accesspolicy_rollout_m3
    :synopsis: Verifies the broader AccessPolicy rollout actually gates writes.

After P25d every write endpoint on the migrated controllers carries
``access_policy=AccessPolicy(roles=("system-admin",))``. This test
boots the full :class:`PychestrateApplication` and confirms an
anonymous request to each gated endpoint returns 401, while the same
request from a system-admin principal proceeds past the policy gate
(the response code may be 4xx for other reasons such as missing body
content — what matters is that the dispatcher does **not** short-
circuit at 401).

Endpoints exercised (one per blueprint):

* POST   /api/v1/identity/users
* POST   /api/v1/flags
* POST   /api/v1/rbac/bindings
* POST   /api/v1/clients/{id}/revoke
* POST   /api/v1/enrollment-tokens
* POST   /api/v1/retention/policies
* POST   /api/v1/notifications/channels
* POST   /api/v1/projects/{slug}/archive
* POST   /api/v1/projects/{pid}/pod-definitions
* PUT    /api/v1/variables/{scope}/{id}/{name}
* POST   /api/v1/agent-rollouts
* POST   /api/v1/tags/{kind}/{id}
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import os
import tempfile

from typing import Optional, Tuple

import sqlalchemy as sa

from sqlalchemy.orm import sessionmaker

from automojo import testbase

from automojo.webworks.authentication.core import (
    AuthenticationContext,
    Principal,
)
from automojo.webworks.routing.request import Request

from automojo.pychestrate.webservice.persistence.schema import (
    PychestratePhase1Base,
)
from automojo.pychestrate.webservice.pychestrateapplication import (
    PychestrateApplication,
)

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    reset_phase1_runtime,
)


_GATED_PROBES = [
    ("POST", "/api/v1/identity/users", b"{}"),
    ("POST", "/api/v1/flags", b"{}"),
    ("POST", "/api/v1/rbac/bindings", b"{}"),
    (
        "POST",
        "/api/v1/clients/00000000-0000-0000-0000-000000000001/revoke",
        b"{}",
    ),
    ("POST", "/api/v1/enrollment-tokens", b"{}"),
    ("POST", "/api/v1/retention/policies", b"{}"),
    ("POST", "/api/v1/notifications/channels", b"{}"),
    (
        "POST",
        "/api/v1/projects/some-slug/archive",
        b"",
    ),
    (
        "POST",
        "/api/v1/projects/00000000-0000-0000-0000-0000000000aa/pod-definitions",
        b"{}",
    ),
    (
        "PUT",
        "/api/v1/variables/system/00000000-0000-0000-0000-0000000000ab/x",
        b"{}",
    ),
    ("POST", "/api/v1/agent-rollouts", b"{}"),
    (
        "POST",
        "/api/v1/tags/project/00000000-0000-0000-0000-0000000000ac",
        b"{}",
    ),
]


def _make_admin_context() -> AuthenticationContext:
    rtnval = AuthenticationContext(
        principal=Principal(
            identifier="00000000-0000-4000-8000-00000000a999",
            display_name="Admin",
            roles={"system-admin"},
        ),
        scheme="test-injection",
    )
    return rtnval


def _build_app() -> Tuple[PychestrateApplication, str]:
    reset_phase1_runtime()
    fd, path = tempfile.mkstemp(prefix="pych_p25d_", suffix=".db")
    os.close(fd)
    engine = sa.create_engine("sqlite:///{0}".format(path))
    PychestratePhase1Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    app = PychestrateApplication(
        session_factory=factory,
        register_extensions=False,
        debug=False,
    )
    return app, path


def _wrap_with_auth(
        *,
        app: PychestrateApplication,
        context: Optional[AuthenticationContext],
    ) -> None:
    original = app.dispatcher.dispatch

    def _wrapped(*, request):
        request.auth = context
        rtnval = original(request=request)
        return rtnval

    app.dispatcher.dispatch = _wrapped
    return


def test_anonymous_writes_get_401_across_every_gated_endpoint():
    """
    **Feature: P25d AccessPolicy rollout (M3)**
    **Property: Every write endpoint listed in _GATED_PROBES rejects
    anonymous requests with HTTP 401, proving the rollout reached
    each blueprint.**
    """
    app, path = _build_app()
    _wrap_with_auth(app=app, context=None)
    try:
        failures = []
        for method, request_path, body in _GATED_PROBES:
            request = Request(
                method=method,
                path=request_path,
                headers={"Content-Type": "application/json"},
                body=body,
            )
            response = app.dispatcher.dispatch(request=request)
            if response.status_code != 401:
                failures.append(
                    "{0} {1} -> {2}".format(
                        method, request_path, response.status_code,
                    ),
                )
        testbase.assert_equal(failures, [])
    finally:
        app.flow_runtime.shutdown(wait=True)
        os.unlink(path)
    return


def test_admin_auth_passes_the_policy_gate_on_every_endpoint():
    """
    **Feature: P25d AccessPolicy rollout (M3)**
    **Property: With a system-admin AuthenticationContext attached,
    every gated endpoint dispatches PAST the AccessPolicy gate. The
    handler may then raise SemanticError (mapped by the dispatcher
    to 500) or return any 2xx / 4xx for missing fields — what
    matters is that the response is **not** 401 / 403, which would
    indicate the gate rejected the request.**
    """
    from automojo.errors.exceptions import SemanticError as _SemanticError

    app, path = _build_app()
    _wrap_with_auth(app=app, context=_make_admin_context())
    try:
        gate_rejections = []
        for method, request_path, body in _GATED_PROBES:
            request = Request(
                method=method,
                path=request_path,
                headers={"Content-Type": "application/json"},
                body=body,
            )
            try:
                response = app.dispatcher.dispatch(request=request)
                status_code = response.status_code
            except _SemanticError:
                # Per CLAUDE.md SemanticError is never caught — it
                # bubbles past the dispatcher. Reaching this branch
                # means the handler ran (the gate was cleared) and
                # only then complained about the body.
                status_code = 500
            if status_code in (401, 403):
                gate_rejections.append(
                    "{0} {1} -> {2}".format(
                        method, request_path, status_code,
                    ),
                )
        testbase.assert_equal(gate_rejections, [])
    finally:
        app.flow_runtime.shutdown(wait=True)
        os.unlink(path)
    return


def test_redeem_endpoint_remains_publicly_accessible():
    """
    **Feature: P25d AccessPolicy rollout (M3)**
    **Property: POST /api/v1/enrollment-tokens/redeem is intentionally
    NOT gated — agents redeeming during enrollment present the secret
    as their authentication factor and have no cookie yet.**
    """
    app, path = _build_app()
    _wrap_with_auth(app=app, context=None)
    try:
        request = Request(
            method="POST",
            path="/api/v1/enrollment-tokens/redeem",
            headers={"Content-Type": "application/json"},
            body=json.dumps({
                "secret": "no-such-secret",
                "pod_name": "p",
            }).encode("utf-8"),
        )
        response = app.dispatcher.dispatch(request=request)
        # The endpoint is reachable and processes the body. The
        # response is a 4xx because the secret is invalid, but the
        # status code is NOT 401 (which would indicate the gate
        # rejected the request).
        testbase.assert_equal(response.status_code != 401, True)
        testbase.assert_equal(response.status_code != 403, True)
    finally:
        app.flow_runtime.shutdown(wait=True)
        os.unlink(path)
    return
