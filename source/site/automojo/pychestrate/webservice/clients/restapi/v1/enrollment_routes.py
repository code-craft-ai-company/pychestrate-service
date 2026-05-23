"""
.. module:: clients.restapi.v1.enrollment_routes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-native REST routes for /api/v1/enrollment-tokens.

.. moduleauthor:: Automation Mojo LLC

The production webservice runs on ``automojo.webworks`` (see
:mod:`app_pychestrate_main`). This module provides the
webworks-native ``enrollment`` controller.

Five routes:

* ``POST   /api/v1/enrollment-tokens``
  — admin issues a new token for ``(project_id, pod_name)``.
  Secret returned exactly once.
* ``GET    /api/v1/enrollment-tokens``
  — admin list (no secrets) with optional ``project_id`` /
  ``status`` filters.
* ``DELETE /api/v1/enrollment-tokens/{token_id}``
  — admin revoke.
* ``POST   /api/v1/enrollment-tokens/redeem``
  — agent presents the secret + payload, receives a bearer
  token (and optionally a signed cert when CSR supplied).
* ``POST   /api/v1/enrollment-tokens/clients/{client_id}/revoke``
  — admin revokes a client identity. Mounted under the
  enrollment namespace because the revocation state lives on
  the enrollment data model.

The fixed ``/redeem`` route is registered BEFORE the
parameterized ``/{token_id}`` route because both share path
depth 3 — without the ordering, the webworks router would match
``POST /enrollment-tokens/redeem`` to a non-existent
``DELETE /{token_id="redeem"}`` (and 405).

Error responses are RFC 7807 problem documents per the
convention in :mod:`api.problem_json_webworks`.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import base64

from typing import Any, Optional

from automojo.webworks.routing.request import Request
from automojo.webworks.routing.response import JSONResponse, Response

from automojo.pychestrate.webservice.api.problem_json_webworks import (
    problem_response_for_http_status,
)
from automojo.pychestrate.webservice.clients.enrollment.factories.identity_verifier import (
    EnrollmentPayload,
)
from automojo.pychestrate.webservice.clients.enrollment.service import (
    TokenView,
    issue_enrollment_token,
    list_enrollment_tokens,
    redeem_enrollment_token,
    revoke_client,
    revoke_enrollment_token,
)
from automojo.pychestrate.webservice.clients.enums import (
    RevocationReason,
    TokenStatus,
)
from automojo.pychestrate.webservice.jobs.envelope import signer
from automojo.pychestrate.webservice.clients.exceptions import (
    CertificateAuthorityUnavailableError,
    ClientAlreadyExistsError,
    ClientNotFoundError,
    CsrScopeMismatchError,
    CsrValidationError,
    EnrollmentRejectedError,
    EnrollmentTokenInvalidError,
    EnrollmentTokenNotFoundError,
)


ENROLLMENT_PATH = "/enrollment-tokens"


class _ProblemAbort(Exception):
    """
        Internal control-flow exception. Carries a webworks problem
        response so nested helpers can signal an error condition once
        and the handler can convert it to a return at the boundary.
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
        extensions: Optional[dict] = None
    ) -> None:
    """
        Build a problem response and raise :class:`_ProblemAbort`.
    """
    response = problem_response_for_http_status(
        status=status,
        detail=detail,
        instance=request.path,
        extensions=extensions,
    )
    raise _ProblemAbort(response)


def _resolve_db_session(request: Request) -> Optional[Any]:
    rtnval = getattr(request, "db_session", None)
    return rtnval


def _resolve_actor_user_id(request: Request) -> Optional[str]:
    rtnval = getattr(request, "actor_user_id", None)
    return rtnval


def _require_session(request: Request) -> Any:
    """
        Resolve the request-scoped db session or abort 503.
    """
    db_session = _resolve_db_session(request=request)
    if db_session is None:
        _abort_problem(
            request=request,
            status=503,
            detail="Request-scoped db_session not configured",
        )
    rtnval = db_session
    return rtnval


def _decode_json_or_abort(*, request: Request) -> dict:
    """
        Decode the request body as JSON, aborting 400 on missing /
        non-dict.
    """
    try:
        payload = request.json()
    except Exception:
        payload = None

    if payload is None:
        _abort_problem(
            request=request, status=400, detail="Request body must be JSON"
        )
    if not isinstance(payload, dict):
        _abort_problem(
            request=request,
            status=400,
            detail="Request body must be a JSON object",
        )

    rtnval = payload
    return rtnval


def _parse_status_or_abort(
        *, request: Request, raw: Optional[str]
    ) -> Optional[TokenStatus]:
    """
        Coerce a ``status`` query string to :class:`TokenStatus`.
        Empty / None returns None; unknown raises 400 with the raw
        value as an extension.

        :param request: Incoming webworks request.
        :param raw: Raw query value or None.

        :returns: :class:`TokenStatus` or None.
    """
    if raw is None or len(raw) == 0:
        return None
    try:
        rtnval = TokenStatus(raw)
    except ValueError:
        _abort_problem(
            request=request,
            status=400,
            detail="Unknown status: {}".format(raw),
            extensions={"requested_status": raw},
        )
    return rtnval


def _decode_csr_field_or_abort(
        *, request: Request, raw: str
    ) -> bytes:
    """
        Accept either raw PEM text or base64-encoded PEM for the
        ``csr_pem`` field and return the PEM bytes. Returns empty
        bytes for empty input. Raises 400 problem+json on
        malformed base64.

        :param request: Incoming webworks request.
        :param raw: Value from the request body.

        :returns: PEM bytes (possibly empty).
    """
    if raw is None or len(raw) == 0:
        return b""
    stripped = raw.strip()
    if stripped.startswith("-----BEGIN"):
        rtnval = stripped.encode("utf-8")
        return rtnval
    try:
        rtnval = base64.b64decode(stripped, validate=False)
    except (ValueError, TypeError):
        _abort_problem(
            request=request,
            status=400,
            detail="csr_pem must be PEM text or base64-encoded PEM",
        )
    return rtnval


def _encode_pem_field(raw: Optional[bytes]) -> str:
    """
        Encode PEM bytes for transport over the JSON response.
        Returns empty string when raw is None / empty so the JSON
        response stays strictly stringly-typed.

        :param raw: PEM bytes or None.

        :returns: Base64 string or empty string.
    """
    if raw is None or len(raw) == 0:
        return ""
    rtnval = base64.b64encode(raw).decode("ascii")
    return rtnval


def _parse_revocation_reason_or_abort(
        *, request: Request, raw: str
    ) -> RevocationReason:
    """
        Coerce a ``reason`` body string to :class:`RevocationReason`.
        Aborts 400 problem+json with the raw value + accepted-list
        as extension members on unknown.

        :param request: Incoming webworks request.
        :param raw: Raw value.

        :returns: :class:`RevocationReason`.
    """
    try:
        rtnval = RevocationReason(raw)
    except ValueError:
        accepted = [v.value for v in RevocationReason]
        err_lines = ["Unknown revocation reason."]
        err_lines.append("RECEIVED: {}".format(raw))
        err_lines.append("ACCEPTED: {}".format(accepted))
        _abort_problem(
            request=request,
            status=400,
            detail=" | ".join(err_lines),
            extensions={"reason": raw, "accepted": accepted},
        )
    return rtnval


def _token_to_dict(view: TokenView) -> dict:
    """
        Render a :class:`TokenView` as the REST response dict.

        :param view: TokenView from the enrollment service.

        :returns: JSON-friendly dict.
    """
    rtnval = {
        "token_id": view.token_id,
        "project_id": view.project_id,
        "pod_name": view.pod_name,
        "status": view.status.value,
        "issued_at": view.issued_at_iso,
        "expires_at": view.expires_at_iso,
        "one_shot": view.one_shot,
        "algorithm_name": view.algorithm_name,
        "redeemed_at": view.redeemed_at_iso,
        "redeemed_by_client_id": view.redeemed_by_client_id,
    }
    return rtnval


# ---------------------------------------------------------------------------
# Handlers — token issue + list + revoke
# ---------------------------------------------------------------------------


def handle_issue_enrollment_token(request: Request) -> Response:
    """
        ``POST /api/v1/enrollment-tokens`` — admin issues a new
        token. Returns 201 with the secret payload (returned
        exactly once).

        :param request: Incoming webworks request.

        :returns: JSON response (201), or problem response on
                  failure.
    """
    try:
        payload = _decode_json_or_abort(request=request)
        db_session = _require_session(request=request)
        actor = _resolve_actor_user_id(request=request)

        ttl_seconds = int(payload.get("ttl_seconds", 0))
        if ttl_seconds <= 0:
            _abort_problem(
                request=request,
                status=400,
                detail="ttl_seconds must be > 0",
                extensions={"ttl_seconds": ttl_seconds},
            )

        issued = issue_enrollment_token(
            db_session=db_session,
            project_id=payload.get("project_id", ""),
            pod_name=payload.get("pod_name", ""),
            ttl_seconds=ttl_seconds,
            one_shot=bool(payload.get("one_shot", True)),
            issued_by=actor,
        )
        body = {
            "token_id": issued.token_id,
            "secret": issued.secret,
            "project_id": issued.project_id,
            "pod_name": issued.pod_name,
            "expires_at": issued.expires_at_iso,
            "algorithm_name": issued.algorithm_name,
        }
        rtnval: Response = JSONResponse(content=body, status_code=201)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


def handle_list_enrollment_tokens(request: Request) -> Response:
    """
        ``GET /api/v1/enrollment-tokens`` — admin list with optional
        ``project_id`` / ``status`` filters.

        :param request: Incoming webworks request.

        :returns: JSON response (200) carrying a list of token view
                  dicts (no secrets), or problem response.
    """
    try:
        db_session = _require_session(request=request)
        project_id = request.query_params.get("project_id", None)
        status = _parse_status_or_abort(
            request=request,
            raw=request.query_params.get("status", ""),
        )

        views = list_enrollment_tokens(
            db_session=db_session,
            project_id=project_id,
            status=status,
        )
        body = [_token_to_dict(view) for view in views]
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


def handle_revoke_enrollment_token(request: Request) -> Response:
    """
        ``DELETE /api/v1/enrollment-tokens/{token_id}`` — admin
        revoke. Returns 200 with ``{token_id, status: "revoked"}``.

        :param request: Incoming webworks request.

        :returns: JSON response (200), or problem response.
    """
    token_id = request.path_params.get("token_id", "")
    try:
        db_session = _require_session(request=request)
        actor = _resolve_actor_user_id(request=request)

        try:
            revoke_enrollment_token(
                db_session=db_session,
                token_id=token_id,
                actor_user_id=actor,
            )
        except EnrollmentTokenNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                extensions={"token_id": token_id},
            )

        body = {"token_id": token_id, "status": "revoked"}
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


# ---------------------------------------------------------------------------
# Handlers — redeem
# ---------------------------------------------------------------------------


def handle_redeem_enrollment_token(request: Request) -> Response:
    """
        ``POST /api/v1/enrollment-tokens/redeem`` — agent presents
        the secret + payload, receives a bearer token (and an
        optional cert when CSR was supplied).

        :param request: Incoming webworks request.

        :returns: JSON response (200) with the redemption result,
                  or problem response on failure.
    """
    try:
        payload = _decode_json_or_abort(request=request)
        db_session = _require_session(request=request)

        csr_raw = payload.get("csr_pem", "") or ""
        csr_pem = _decode_csr_field_or_abort(
            request=request, raw=csr_raw
        )
        csr_for_payload = csr_pem if len(csr_pem) > 0 else None

        enrollment_payload = EnrollmentPayload(
            pod_name=payload.get("pod_name", ""),
            agent_version=payload.get("agent_version", None),
            transport_name=payload.get("transport_name", None),
            extras=payload.get("extras", {}) or {},
            csr_pem=csr_for_payload,
        )

        try:
            result = redeem_enrollment_token(
                db_session=db_session,
                secret=payload.get("secret", ""),
                payload=enrollment_payload,
            )
        except EnrollmentTokenNotFoundError as xcpt:
            _abort_problem(
                request=request, status=404, detail=str(xcpt)
            )
        except EnrollmentTokenInvalidError as xcpt:
            _abort_problem(
                request=request, status=400, detail=str(xcpt)
            )
        except EnrollmentRejectedError as xcpt:
            _abort_problem(
                request=request, status=403, detail=str(xcpt)
            )
        except ClientAlreadyExistsError as xcpt:
            _abort_problem(
                request=request, status=409, detail=str(xcpt)
            )
        except CsrScopeMismatchError as xcpt:
            _abort_problem(
                request=request, status=403, detail=str(xcpt)
            )
        except CsrValidationError as xcpt:
            _abort_problem(
                request=request, status=400, detail=str(xcpt)
            )
        except CertificateAuthorityUnavailableError as xcpt:
            _abort_problem(
                request=request, status=503, detail=str(xcpt)
            )

        # Bundle the envelope-signing public key set so a freshly-
        # enrolled client can verify signed job envelopes on the
        # happy path with zero extra calls. The signer holds only the
        # public half here; the private key never leaves the process.
        # When no signing key is provisioned the list is empty -- the
        # client can refresh later via GET /envelope-signing-keys.
        envelope_signing_keys = signer.active_signing_key_set()

        body = {
            "client_id": result.client_id,
            "project_id": result.project_id,
            "pod_name": result.pod_name,
            "bearer_token": result.bearer_token,
            "bearer_algorithm": result.bearer_algorithm,
            "cert_serial": result.cert_serial or "",
            "cert_pem": _encode_pem_field(result.cert_pem),
            "cert_chain_pem": _encode_pem_field(result.cert_chain_pem),
            "envelope_signing_keys": envelope_signing_keys,
        }
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


# ---------------------------------------------------------------------------
# Handlers — client revoke (mounted under enrollment namespace)
# ---------------------------------------------------------------------------


def handle_revoke_client_under_enrollment(request: Request) -> Response:
    """
        ``POST /api/v1/enrollment-tokens/clients/{client_id}/revoke``
        — admin revokes a client identity. Mounted here because the
        revocation state lives on the enrollment data model.

        Note this duplicates the route surface served by
        :func:`clients_routes.handle_revoke_client` but goes through
        the enrollment-namespaced URL path -- both surfaces are
        retained deliberately for RBAC gate alignment.

        :param request: Incoming webworks request.

        :returns: JSON response (200), or problem response on
                  failure.
    """
    client_id = request.path_params.get("client_id", "")
    try:
        body = _decode_json_or_abort(request=request)
        db_session = _require_session(request=request)
        actor = _resolve_actor_user_id(request=request)

        reason_raw = body.get("reason", "")
        if reason_raw is None or len(reason_raw) == 0:
            _abort_problem(
                request=request,
                status=400,
                detail="reason is required",
                extensions={"client_id": client_id},
            )
        reason = _parse_revocation_reason_or_abort(
            request=request, raw=reason_raw
        )

        note = body.get("note", "") or ""
        cert_serial_in = body.get("cert_serial", None)
        if cert_serial_in is not None and len(cert_serial_in) == 0:
            cert_serial_in = None

        try:
            revoke_client(
                db_session=db_session,
                client_id=client_id,
                reason=reason,
                revoked_by=actor,
                note=note,
                cert_serial=cert_serial_in,
            )
        except ClientNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                extensions={"client_id": client_id},
            )

        response_body = {
            "client_id": client_id,
            "status": "revoked",
            "cert_serial": cert_serial_in or "",
            "reason": reason.value,
        }
        rtnval: Response = JSONResponse(
            content=response_body, status_code=200
        )
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_enrollment_routes(*, app: Any, version_prefix: str) -> None:
    """
        Attach the enrollment-token routes to a webworks
        application.

        Note that the fixed ``/redeem`` and
        ``/clients/{client_id}/revoke`` routes register BEFORE the
        parameterized ``/{token_id}`` route. Both the fixed
        ``/redeem`` and the parameterized ``/{token_id}`` live at
        path depth 3 -- without the ordering, the webworks router
        could match ``POST /enrollment-tokens/redeem`` to a non-
        existent ``DELETE /{token_id="redeem"}``.

        :param app: WebWorks application built by
                    ``establish_webapp_persona``.
        :param version_prefix: Versioned API prefix.

        :returns: None.
    """
    base = version_prefix + ENROLLMENT_PATH

    app.attach_route(
        base, methods=["GET"]
    )(handle_list_enrollment_tokens)
    app.attach_route(
        base, methods=["POST"]
    )(handle_issue_enrollment_token)

    app.attach_route(
        base + "/redeem", methods=["POST"]
    )(handle_redeem_enrollment_token)
    app.attach_route(
        base + "/clients/{client_id}/revoke", methods=["POST"]
    )(handle_revoke_client_under_enrollment)

    app.attach_route(
        base + "/{token_id}", methods=["DELETE"]
    )(handle_revoke_enrollment_token)

    return


__all__ = [
    "ENROLLMENT_PATH",
    "register_enrollment_routes",
    "handle_issue_enrollment_token",
    "handle_list_enrollment_tokens",
    "handle_revoke_enrollment_token",
    "handle_redeem_enrollment_token",
    "handle_revoke_client_under_enrollment",
]
