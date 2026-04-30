"""
.. module:: clients.restapi.v1.enrollment_controller
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: REST API v1 controller for /api/v1/enrollment-tokens and redemption.

.. moduleauthor:: Automation Mojo LLC

Migrated from Flask + flask-restx to automojo-webworks. Pattern follows
the worked example documented in
:mod:`automojo.pychestrate.webservice.security.auth.restapi.v1.auth_controller`.

Endpoints (unchanged URLs):

* ``POST   /api/v1/enrollment-tokens`` — admin issue.
* ``GET    /api/v1/enrollment-tokens`` — admin list.
* ``DELETE /api/v1/enrollment-tokens/{token_id}`` — admin revoke.
* ``POST   /api/v1/enrollment-tokens/redeem`` — agent redeem.
* ``POST   /api/v1/enrollment-tokens/clients/{client_id}/revoke`` —
  admin revoke of a client identity (mounted under enrollment so it
  shares the RBAC gate with token rescission).
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import base64
import os

from typing import Any, Dict, Optional

from automojo.webworks.endpoints.doc import Doc
from automojo.webworks.endpoints.restblueprint import RestBlueprint
from automojo.webworks.routing.exceptions import HTTPException
from automojo.webworks.routing.request import Request
from automojo.webworks.routing.response import JSONResponse
from automojo.webworks.security.accesspolicy import AccessPolicy


_ADMIN_POLICY = AccessPolicy(roles=("system-admin",))

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
from automojo.pychestrate.webservice.dbsessionmiddleware import (
    get_request_actor_user_id,
)


ENROLLMENT_BASE_PATH = "/api/v1/enrollment-tokens"


def _token_to_dict(view: TokenView) -> Dict[str, Any]:
    """
        Render a :class:`TokenView` as the REST response dict.

        :param view: The view object.

        :returns: A plain dict suitable for JSON serialization.
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


def _parse_status(*, raw: Optional[str]) -> Optional[TokenStatus]:
    """
        Coerce a query-param string to a :class:`TokenStatus`.

        :param raw: Raw query-string value, possibly None.

        :returns: The matching enum, or None when ``raw`` is empty.

        :raises HTTPException: 400 when ``raw`` is non-empty and unknown.
    """
    if raw is None:
        return None
    if len(raw) == 0:
        return None
    try:
        rtnval = TokenStatus(raw)
    except ValueError as exc:
        err_msg = "Unknown status: {}".format(raw)
        raise HTTPException(status_code=400, detail=err_msg) from exc
    return rtnval


def _decode_csr_field(*, raw: Optional[str]) -> bytes:
    """
        Accept either raw PEM text or base64-encoded PEM and return
        the PEM bytes.

        :param raw: Value submitted on the ``csr_pem`` field.

        :returns: PEM bytes (possibly empty).

        :raises HTTPException: 400 when the value is not valid base64
                               or PEM.
    """
    if raw is None:
        return b""
    if len(raw) == 0:
        return b""
    stripped = raw.strip()
    if stripped.startswith("-----BEGIN"):
        rtnval = stripped.encode("utf-8")
        return rtnval
    try:
        rtnval = base64.b64decode(stripped, validate=False)
    except (ValueError, TypeError) as exc:
        err_msg = "csr_pem must be PEM text or base64-encoded PEM"
        raise HTTPException(status_code=400, detail=err_msg) from exc
    return rtnval


def _encode_pem_field(*, raw: Optional[bytes]) -> str:
    """
        Encode a PEM bytes field as base64 for the JSON response.

        :param raw: PEM bytes (possibly None).

        :returns: Base64 string or empty string.
    """
    if raw is None:
        return ""
    if len(raw) == 0:
        return ""
    rtnval = base64.b64encode(raw).decode("ascii")
    return rtnval


def _parse_revocation_reason(*, raw: str) -> RevocationReason:
    """
        Parse an inbound ``reason`` string into :class:`RevocationReason`.

        :param raw: Raw string from the request body.

        :returns: Enum value.

        :raises HTTPException: 400 with the accepted-value list when
                               ``raw`` is unknown.
    """
    try:
        rtnval = RevocationReason(raw)
    except ValueError as exc:
        accepted = [v.value for v in RevocationReason]
        err_lines = [
            "Unknown revocation reason.",
            "RECEIVED: {}".format(raw),
            "ACCEPTED: {}".format(accepted),
        ]
        err_msg = " | ".join(err_lines)
        raise HTTPException(status_code=400, detail=err_msg) from exc
    return rtnval


def _require_db_session(*, request: Request) -> Any:
    """
        Pull the request-scoped ``db_session`` set by
        :class:`DbSessionMiddleware`, or 503.
    """
    db_session = getattr(request, "db_session", None)
    if db_session is None:
        err_lines = [
            "Request-scoped db_session not configured.",
            "DbSessionMiddleware must be installed in the pipeline.",
        ]
        err_msg = os.linesep.join(err_lines)
        raise HTTPException(status_code=503, detail=err_msg)
    return db_session


def _read_json_body(*, request: Request) -> Dict[str, Any]:
    """
        Parse the request body as a JSON object.
    """
    raw_body = request.body
    if raw_body is None:
        raise HTTPException(status_code=400, detail="request body required")
    if len(raw_body) == 0:
        raise HTTPException(status_code=400, detail="request body required")
    try:
        decoded = request.json()
    except Exception as exc:
        err_msg = "request body must be valid JSON"
        raise HTTPException(status_code=400, detail=err_msg) from exc
    if not isinstance(decoded, dict):
        raise HTTPException(
            status_code=400, detail="request body must be a JSON object",
        )
    rtnval = decoded
    return rtnval


class EnrollmentBlueprint(RestBlueprint):
    """
        Blueprint grouping the v1 ``/api/v1/enrollment-tokens`` endpoints.
    """

    base_path = ENROLLMENT_BASE_PATH
    tags = ["enrollment", "v1"]

    @RestBlueprint.attach_at(
        path="/api/v1/enrollment-tokens",
        methods=["POST"],
        doc=Doc(
            summary="Issue an enrollment token",
            description=(
                "Issue a new enrollment token for a (project_id, "
                "pod_name) scope. The secret is returned exactly once."
            ),
        ),
        access_policy=_ADMIN_POLICY,
    )
    def issue_token(request: Request) -> JSONResponse:
        """
            Issue a new enrollment token.

            :param request: The incoming HTTP request.

            :returns: 201 with the issued-token payload.
        """
        db_session = _require_db_session(request=request)
        payload = _read_json_body(request=request)
        actor_user_id = get_request_actor_user_id(request=request)

        ttl_seconds_raw = payload.get("ttl_seconds", 0)
        try:
            ttl_seconds = int(ttl_seconds_raw)
        except (TypeError, ValueError) as exc:
            err_msg = "ttl_seconds must be an integer"
            raise HTTPException(status_code=400, detail=err_msg) from exc
        if ttl_seconds <= 0:
            raise HTTPException(
                status_code=400, detail="ttl_seconds must be > 0",
            )

        issued = issue_enrollment_token(
            db_session=db_session,
            project_id=payload.get("project_id", ""),
            pod_name=payload.get("pod_name", ""),
            ttl_seconds=ttl_seconds,
            one_shot=bool(payload.get("one_shot", True)),
            issued_by=actor_user_id,
        )
        body = {
            "token_id": issued.token_id,
            "secret": issued.secret,
            "project_id": issued.project_id,
            "pod_name": issued.pod_name,
            "expires_at": issued.expires_at_iso,
            "algorithm_name": issued.algorithm_name,
        }
        rtnval = JSONResponse(content=body, status_code=201)
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/enrollment-tokens",
        methods=["GET"],
        doc=Doc(
            summary="List enrollment tokens",
            description=(
                "List enrollment tokens (no secrets). Supports "
                "project_id and status query-string filters."
            ),
        ),
    )
    def list_tokens(request: Request) -> JSONResponse:
        """
            List enrollment tokens with optional filters.

            :param request: The incoming HTTP request.

            :returns: 200 with a JSON list of token views.
        """
        db_session = _require_db_session(request=request)
        project_id = request.query_params.get("project_id", None)
        status_raw = request.query_params.get("status", "")
        status = _parse_status(raw=status_raw)

        views = list_enrollment_tokens(
            db_session=db_session,
            project_id=project_id,
            status=status,
        )
        body = [_token_to_dict(view=v) for v in views]
        rtnval = JSONResponse(content=body, status_code=200)
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/enrollment-tokens/{token_id}",
        methods=["DELETE"],
        doc=Doc(
            summary="Revoke an enrollment token",
            description="Admin revoke of an enrollment token by id.",
        ),
        access_policy=_ADMIN_POLICY,
    )
    def delete_token(request: Request) -> JSONResponse:
        """
            Revoke an enrollment token.

            :param request: The incoming HTTP request.

            :returns: 200 with ``{"token_id": ..., "status":
                      "revoked"}``.
        """
        db_session = _require_db_session(request=request)
        actor_user_id = get_request_actor_user_id(request=request)
        token_id = request.path_params.get("token_id", "")

        try:
            revoke_enrollment_token(
                db_session=db_session,
                token_id=token_id,
                actor_user_id=actor_user_id,
            )
        except EnrollmentTokenNotFoundError as exc:
            raise HTTPException(
                status_code=404, detail=str(exc),
            ) from exc

        body = {"token_id": token_id, "status": "revoked"}
        rtnval = JSONResponse(content=body, status_code=200)
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/enrollment-tokens/redeem",
        methods=["POST"],
        doc=Doc(
            summary="Redeem an enrollment token",
            description=(
                "Agent presents the enrollment secret plus payload and "
                "receives a bearer token (and, optionally, a signed "
                "client cert). This endpoint is intentionally NOT "
                "gated by AccessPolicy: the agent has no cookie yet "
                "at redemption time and the secret itself is the "
                "authentication factor."
            ),
        ),
    )
    def redeem_token(request: Request) -> JSONResponse:
        """
            Redeem an enrollment token.

            :param request: The incoming HTTP request.

            :returns: 200 with the redemption result.
        """
        db_session = _require_db_session(request=request)
        payload = _read_json_body(request=request)

        csr_raw = payload.get("csr_pem", "")
        if csr_raw is None:
            csr_raw = ""
        csr_pem = _decode_csr_field(raw=csr_raw)
        if len(csr_pem) > 0:
            csr_for_payload = csr_pem
        else:
            csr_for_payload = None

        extras_raw = payload.get("extras", {})
        if extras_raw is None:
            extras_raw = {}

        enrollment_payload = EnrollmentPayload(
            pod_name=payload.get("pod_name", ""),
            agent_version=payload.get("agent_version", None),
            transport_name=payload.get("transport_name", None),
            extras=extras_raw,
            csr_pem=csr_for_payload,
        )

        try:
            result = redeem_enrollment_token(
                db_session=db_session,
                secret=payload.get("secret", ""),
                payload=enrollment_payload,
            )
        except EnrollmentTokenNotFoundError as exc:
            raise HTTPException(
                status_code=404, detail=str(exc),
            ) from exc
        except EnrollmentTokenInvalidError as exc:
            raise HTTPException(
                status_code=400, detail=str(exc),
            ) from exc
        except EnrollmentRejectedError as exc:
            raise HTTPException(
                status_code=403, detail=str(exc),
            ) from exc
        except ClientAlreadyExistsError as exc:
            raise HTTPException(
                status_code=409, detail=str(exc),
            ) from exc
        except CsrScopeMismatchError as exc:
            raise HTTPException(
                status_code=403, detail=str(exc),
            ) from exc
        except CsrValidationError as exc:
            raise HTTPException(
                status_code=400, detail=str(exc),
            ) from exc
        except CertificateAuthorityUnavailableError as exc:
            raise HTTPException(
                status_code=503, detail=str(exc),
            ) from exc

        body = {
            "client_id": result.client_id,
            "project_id": result.project_id,
            "pod_name": result.pod_name,
            "bearer_token": result.bearer_token,
            "bearer_algorithm": result.bearer_algorithm,
            "cert_serial": result.cert_serial if result.cert_serial else "",
            "cert_pem": _encode_pem_field(raw=result.cert_pem),
            "cert_chain_pem": _encode_pem_field(raw=result.cert_chain_pem),
        }
        rtnval = JSONResponse(content=body, status_code=200)
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/enrollment-tokens/clients/{client_id}/revoke",
        methods=["POST"],
        doc=Doc(
            summary="Revoke a client identity",
            description=(
                "Admin revokes a client identity. Mounted under the "
                "enrollment namespace because the revocation row lives "
                "on the enrollment data model."
            ),
        ),
        access_policy=_ADMIN_POLICY,
    )
    def revoke_client_identity(request: Request) -> JSONResponse:
        """
            Revoke a client identity.

            :param request: The incoming HTTP request.

            :returns: 200 with the revocation summary.
        """
        db_session = _require_db_session(request=request)
        actor_user_id = get_request_actor_user_id(request=request)
        body_payload = _read_json_body(request=request)
        client_id = request.path_params.get("client_id", "")

        reason_raw = body_payload.get("reason", "")
        if reason_raw is None:
            raise HTTPException(
                status_code=400, detail="reason is required",
            )
        if len(reason_raw) == 0:
            raise HTTPException(
                status_code=400, detail="reason is required",
            )
        reason = _parse_revocation_reason(raw=reason_raw)

        note = body_payload.get("note", "")
        if note is None:
            note = ""

        cert_serial_in = body_payload.get("cert_serial", None)
        if cert_serial_in is not None:
            if len(cert_serial_in) == 0:
                cert_serial_in = None

        try:
            revoke_client(
                db_session=db_session,
                client_id=client_id,
                reason=reason,
                revoked_by=actor_user_id,
                note=note,
                cert_serial=cert_serial_in,
            )
        except ClientNotFoundError as exc:
            raise HTTPException(
                status_code=404, detail=str(exc),
            ) from exc

        body = {
            "client_id": client_id,
            "status": "revoked",
            "cert_serial": cert_serial_in if cert_serial_in else "",
            "reason": reason.value,
        }
        rtnval = JSONResponse(content=body, status_code=200)
        return rtnval
