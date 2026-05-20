"""
.. module:: clients.restapi.v1.client_dispatch_routes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Client-pull long-poll endpoints.

.. moduleauthor:: Automation Mojo LLC

PR p19g adds two pod-client-facing endpoints sitting on the
``/api/v1/clients/...`` namespace:

* ``GET /api/v1/clients/{client_id}/dispatches:next``

  Long-polls for the next signed envelope queued for the calling
  client. Returns 200 with the envelope body when a dispatch is
  available, 204 No Content when the wait window elapses with no
  pending work, 401 when no mTLS cert was forwarded, 403 when the
  cert common-name does not match the path ``client_id``.

* ``GET /api/v1/clients/{client_id}/heartbeat``

  Lightweight ping that records the client's liveness via the
  existing :func:`clients.registry.service.record_heartbeat` seam
  and returns 204.

The endpoints are mTLS-only -- there is no ``system:*`` permission
gate. The presence of an nginx-verified client certificate plus a
cert-CN that matches the path ``client_id`` is the auth contract.

The :class:`LongPollTransport` instance is published on the
module-level ``ACTIVE_LONG_POLL_TRANSPORT`` seam by the Phase-6
bootstrap; the handler resolves it lazily so the route module can
import cleanly during register-only callsites.

PR p19h renames this module from ``agent_dispatch_routes`` to
``client_dispatch_routes`` and moves it into the
``clients/restapi/v1`` package so the route prefix
(``/api/v1/clients/...``) matches the canonical "client" naming
used for the pod-side runtime. The pre-existing ``webservice/agents``
package retains the older inventory + capability surface.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import logging

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from automojo.webworks.routing.request import Request
from automojo.webworks.routing.response import JSONResponse, Response

from automojo.pychestrate.webservice.agents.factories.long_poll_transport import (
    DEFAULT_LONG_POLL_TIMEOUT_SECONDS,
    DispatchRecord,
    LONG_POLL_TRANSPORT_NAME,
    LongPollTransport,
    MAX_LONG_POLL_TIMEOUT_SECONDS,
)
from automojo.pychestrate.webservice.api.problem_json_webworks import (
    problem_response_for_http_status,
)
from automojo.pychestrate.webservice.clients.exceptions import (
    ClientNotFoundError,
)
from automojo.pychestrate.webservice.clients.registry import service as client_registry_service
from automojo.pychestrate.webservice.jobs.envelope.canonical import (
    envelope_to_dict,
)


CLIENTS_BASE_PATH = "/clients"

#: WSGI environ key nginx populates with the verified client cert
#: common-name after a successful mTLS handshake. Mirrors the seam
#: documented on :mod:`runs.restapi.v1.runs_routes`.
MTLS_CLIENT_CN_ENVIRON_KEY = "SSL_CLIENT_S_DN_CN"

#: Module-level seam published by :mod:`extensions.phase6_bootstrap`
#: so the production handler can reach the same transport instance
#: the dispatcher writes to. Tests override this via
#: :func:`set_active_long_poll_transport`.
ACTIVE_LONG_POLL_TRANSPORT: Optional[LongPollTransport] = None


_LOGGER = logging.getLogger("pychestrate.clients.dispatch_routes")


# ---------------------------------------------------------------------------
# Seam plumbing
# ---------------------------------------------------------------------------


def set_active_long_poll_transport(
        *, transport: Optional[LongPollTransport]
    ) -> None:
    """
        Publish the production :class:`LongPollTransport` instance
        for the handler to consume. Called by the Phase-6 bootstrap
        after constructing the transport.

        :param transport: Transport instance (or ``None`` to clear).

        :returns: None.
    """
    global ACTIVE_LONG_POLL_TRANSPORT
    ACTIVE_LONG_POLL_TRANSPORT = transport
    return


def _resolve_long_poll_transport() -> Optional[LongPollTransport]:
    """
        Return the module-level :class:`LongPollTransport`, or
        ``None`` when the bootstrap has not run.

        :returns: Transport instance or None.
    """
    rtnval = ACTIVE_LONG_POLL_TRANSPORT
    return rtnval


# ---------------------------------------------------------------------------
# Problem-flow plumbing (mirrors runs_routes._ProblemAbort)
# ---------------------------------------------------------------------------


class _ProblemAbort(Exception):
    """
        Internal control-flow exception. Carries a webworks problem
        response so nested helpers can signal an error condition
        once and the top-level handler can convert it to a return
        value at the boundary.
    """

    def __init__(self, response: Response) -> None:
        super().__init__("problem abort")
        self.response: Response = response
        return


def _abort_problem(
        *,
        request: Request,
        status: int,
        detail: str,
        extensions: Optional[Dict[str, Any]] = None
    ) -> None:
    """
        Build a problem response and raise :class:`_ProblemAbort`.

        :param request: Incoming webworks request.
        :param status: HTTP status code.
        :param detail: Occurrence-specific explanation.
        :param extensions: Optional namespaced extension members.

        :returns: Never returns.
    """
    response = problem_response_for_http_status(
        status=status,
        detail=detail,
        instance=request.path,
        extensions=extensions,
    )
    raise _ProblemAbort(response)


def _resolve_mtls_client_cn(request: Request) -> Optional[str]:
    """
        Return the verified client common-name nginx forwarded for
        this request, or ``None`` when no mTLS handshake completed.

        :param request: Incoming webworks request.

        :returns: Client common-name string or None.
    """
    explicit = getattr(request, "mtls_client_cn", None)
    if isinstance(explicit, str) and len(explicit) > 0:
        rtnval = explicit
        return rtnval

    environ = getattr(request, "environ", None)
    if isinstance(environ, dict):
        candidate = environ.get(MTLS_CLIENT_CN_ENVIRON_KEY, None)
        if isinstance(candidate, str) and len(candidate) > 0:
            rtnval = candidate
            return rtnval

    scope = getattr(request, "scope", None)
    if isinstance(scope, dict):
        candidate = scope.get(MTLS_CLIENT_CN_ENVIRON_KEY, None)
        if isinstance(candidate, str) and len(candidate) > 0:
            rtnval = candidate
            return rtnval

    rtnval = None
    return rtnval


def _require_mtls_client_cn(request: Request) -> str:
    """
        Resolve the mTLS-verified client common-name or abort 401.

        :param request: Incoming webworks request.

        :returns: Client common-name string.
    """
    candidate = _resolve_mtls_client_cn(request=request)
    if candidate is None:
        _abort_problem(
            request=request,
            status=401,
            detail=(
                "Mutual-TLS client certificate required (nginx must"
                " forward SSL_CLIENT_S_DN_CN)."
            ),
        )
    rtnval = candidate
    return rtnval


def _require_cert_matches_client_id(
        *,
        request: Request,
        client_cn: str,
        client_id: str
    ) -> None:
    """
        Enforce that the mTLS-verified client common-name matches
        the path ``client_id``. The cert CN is the client's enrolled
        UUID; a mismatch indicates a misrouted or spoofed call.

        :param request: Incoming webworks request.
        :param client_cn: Common-name nginx forwarded.
        :param client_id: Path-param client UUID.

        :returns: None.
    """
    if client_cn != client_id:
        _abort_problem(
            request=request,
            status=403,
            detail=(
                "Client certificate common-name does not match path"
                " client_id."
            ),
            extensions={
                "path_client_id": client_id,
                "cert_client_cn": client_cn,
            },
        )
    return


def _resolve_db_session(request: Request) -> Optional[Any]:
    """
        Return the request-scoped db session attached by the
        session middleware, or ``None`` when none is bound.

        :param request: Incoming webworks request.

        :returns: SQLAlchemy session or None.
    """
    rtnval = getattr(request, "db_session", None)
    return rtnval


def _parse_timeout_seconds(
        *, request: Request, raw: Optional[str]
    ) -> int:
    """
        Coerce + clamp the ``timeout_seconds`` query param.

        :param request: Incoming webworks request.
        :param raw: Raw query value or None.

        :returns: Clamped timeout in seconds.
    """
    if raw is None or len(raw) == 0:
        rtnval = DEFAULT_LONG_POLL_TIMEOUT_SECONDS
        return rtnval

    try:
        candidate = int(raw)
    except ValueError:
        _abort_problem(
            request=request,
            status=422,
            detail="Query param 'timeout_seconds' must be an integer.",
            extensions={"query_param": "timeout_seconds", "raw_value": raw},
        )
        candidate = DEFAULT_LONG_POLL_TIMEOUT_SECONDS  # unreachable

    if candidate < 0:
        _abort_problem(
            request=request,
            status=422,
            detail="Query param 'timeout_seconds' must be >= 0.",
            extensions={"query_param": "timeout_seconds", "raw_value": raw},
        )
    if candidate > MAX_LONG_POLL_TIMEOUT_SECONDS:
        candidate = MAX_LONG_POLL_TIMEOUT_SECONDS

    rtnval = candidate
    return rtnval


def _validate_client_id_or_abort(
        *, request: Request, client_id: str
    ) -> None:
    """
        Reject empty / obviously malformed path client ids.

        The client enrollment flow issues UUIDv4 client ids; we keep
        the validation cheap (non-empty + length cap) and rely on
        the cert-match check to reject anything that does not match
        a known enrolled identity.

        :param request: Incoming webworks request.
        :param client_id: Path-param value.

        :returns: None.
    """
    if client_id is None or len(client_id) == 0:
        _abort_problem(
            request=request,
            status=422,
            detail="Path parameter 'client_id' must not be empty.",
        )
    if len(client_id) > 256:
        _abort_problem(
            request=request,
            status=422,
            detail="Path parameter 'client_id' is implausibly long.",
            extensions={"client_id_length": len(client_id)},
        )
    return


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def _signed_envelope_signature_hex(*, signature: bytes) -> str:
    """
        Render the Ed25519 detached signature bytes as a hex string
        suitable for embedding in the JSON response. The client
        re-verifies against the canonical payload, so the encoding
        choice is opaque to the server -- hex keeps the body
        human-readable without dragging base64 padding gotchas in.

        :param signature: Raw signature bytes.

        :returns: Lowercase hex string.
    """
    rtnval = signature.hex()
    return rtnval


def _pending_dispatch_to_dict(
        *, record: DispatchRecord
    ) -> Dict[str, Any]:
    """
        Serialize a :class:`DispatchRecord` to the OpenAPI
        ``PendingDispatch`` schema.

        :param record: Queued dispatch record.

        :returns: JSON-friendly dict.
    """
    envelope_dict = envelope_to_dict(envelope=record.signed.envelope)
    rtnval: Dict[str, Any] = {
        "dispatch_attempt_id": record.dispatch_attempt_id,
        "run_id": record.run_id,
        "client_id": record.client_id,
        "pod_id": record.pod_id,
        "envelope_id": record.envelope_id,
        "enqueued_at": record.enqueued_at.isoformat(),
        "ack_deadline_at": record.ack_deadline_at.isoformat(),
        "envelope": envelope_dict,
        "signature": _signed_envelope_signature_hex(
            signature=record.signed.signature,
        ),
        "signature_key_id": record.signed.key_id,
        "signed_at": record.signed.signed_at.isoformat(),
        "transport_name": LONG_POLL_TRANSPORT_NAME,
    }
    return rtnval


# ---------------------------------------------------------------------------
# GET /api/v1/clients/{client_id}/dispatches:next
# ---------------------------------------------------------------------------


def handle_next_dispatch(request: Request) -> Response:
    """
        ``GET /api/v1/clients/{client_id}/dispatches:next`` --
        long-poll for the next signed dispatch envelope queued for
        the calling client.

        :param request: Incoming webworks request.

        :returns: 200 + JSON body on dispatch; 204 on timeout; 401
                  / 403 / 422 problem responses on failure.
    """
    client_id = request.path_params.get("client_id", "")
    try:
        _validate_client_id_or_abort(request=request, client_id=client_id)
        client_cn = _require_mtls_client_cn(request=request)
        _require_cert_matches_client_id(
            request=request, client_cn=client_cn, client_id=client_id,
        )

        transport = _resolve_long_poll_transport()
        if transport is None:
            _abort_problem(
                request=request,
                status=503,
                detail=(
                    "Long-poll transport is not configured on this"
                    " service instance."
                ),
            )

        timeout_seconds = _parse_timeout_seconds(
            request=request,
            raw=request.query_params.get("timeout_seconds", None),
        )

        record = transport.await_pending_dispatch(
            client_id=client_id,
            timeout_seconds=timeout_seconds,
        )

        if record is None:
            _LOGGER.info(
                "clients.dispatches_next.timeout client_id=%s wait=%d",
                client_id,
                timeout_seconds,
            )
            rtnval: Response = Response(status_code=204, body=b"")
            return rtnval

        body = _pending_dispatch_to_dict(record=record)
        _LOGGER.info(
            "clients.dispatches_next.delivered client_id=%s run_id=%s envelope_id=%s",
            client_id,
            record.run_id,
            record.envelope_id,
        )
        rtnval = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# GET /api/v1/clients/{client_id}/heartbeat
# ---------------------------------------------------------------------------


def handle_client_heartbeat(request: Request) -> Response:
    """
        ``GET /api/v1/clients/{client_id}/heartbeat`` -- lightweight
        liveness ping. Updates ``last_seen`` on the client row via
        :func:`clients.registry.service.record_heartbeat` and
        answers 204.

        Returns 204 even when the registry has no row for
        ``client_id`` (the cert match already proved the client
        enrolled; a missing row is a server-side bookkeeping issue
        we surface in logs rather than the client's UI).

        :param request: Incoming webworks request.

        :returns: 204 on success; 401 / 403 / 422 problem responses
                  on auth failure.
    """
    client_id = request.path_params.get("client_id", "")
    try:
        _validate_client_id_or_abort(request=request, client_id=client_id)
        client_cn = _require_mtls_client_cn(request=request)
        _require_cert_matches_client_id(
            request=request, client_cn=client_cn, client_id=client_id,
        )

        db_session = _resolve_db_session(request=request)
        if db_session is not None:
            now = datetime.now(timezone.utc)
            try:
                client_registry_service.record_heartbeat(
                    db_session=db_session,
                    client_id=client_id,
                    received_at=now,
                    agent_version=None,
                    transport_name=LONG_POLL_TRANSPORT_NAME,
                )
            except ClientNotFoundError as xcpt:
                _LOGGER.warning(
                    "clients.heartbeat.client_not_found client_id=%s err=%s",
                    client_id,
                    xcpt,
                )

        rtnval: Response = Response(status_code=204, body=b"")
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_client_dispatch_routes(*, app: Any, version_prefix: str) -> None:
    """
        Attach the client-pull long-poll routes to a webworks
        application.

        :param app: WebWorks application built by
                    ``establish_webapp_persona``.
        :param version_prefix: Versioned API prefix (e.g.
                               ``"/api/v1"``).

        :returns: None.
    """
    base = version_prefix + CLIENTS_BASE_PATH
    app.attach_route(
        base + "/{client_id}/dispatches:next", methods=["GET"],
    )(handle_next_dispatch)
    app.attach_route(
        base + "/{client_id}/heartbeat", methods=["GET"],
    )(handle_client_heartbeat)

    _LOGGER.warning(
        "pychestrate.clients.dispatch_routes.mtls_not_wired: client"
        " pull endpoints require nginx mTLS but will reject every"
        " request with 401 until SSL_CLIENT_S_DN_CN is forwarded."
    )
    return


__all__ = [
    "ACTIVE_LONG_POLL_TRANSPORT",
    "CLIENTS_BASE_PATH",
    "MTLS_CLIENT_CN_ENVIRON_KEY",
    "handle_client_heartbeat",
    "handle_next_dispatch",
    "register_client_dispatch_routes",
    "set_active_long_poll_transport",
]
