"""
.. module:: clients.restapi.v1.enrollment_controller
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: REST API v1 controller for /api/v1/enrollment-tokens and redemption.

.. moduleauthor:: Automation Mojo LLC

M1 routes:

* ``POST /api/v1/enrollment-tokens`` — admin issues a new token for a
  ``(project_id, pod_name)`` scope. Secret returned exactly once.
* ``GET  /api/v1/enrollment-tokens`` — admin list (no secrets).
* ``DELETE /api/v1/enrollment-tokens/{token_id}`` — admin revoke.
* ``POST /api/v1/enrollment-tokens/redeem`` — agent presents the secret
  plus its enrollment payload and receives a bearer token.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import base64

from flask import g, request
from flask_restx import Namespace, Resource, fields

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
from automojo.pychestrate.webservice.clients.enums import RevocationReason, TokenStatus
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


ENROLLMENT_NAMESPACE_PATH = "/enrollment-tokens"


enrollment_ns = Namespace(
    "Client Enrollment v1",
    description="Enrollment token issuance + redemption (3-client-enrollment).",
)


token_issue_request_model = enrollment_ns.model(
    "EnrollmentTokenIssueRequest",
    {
        "project_id": fields.String(required=True, description="Scope project UUID"),
        "pod_name": fields.String(required=True, description="Pod name the token commits to"),
        "ttl_seconds": fields.Integer(required=True, description="Lifetime in seconds (<=86400)"),
        "one_shot": fields.Boolean(required=False, default=True, description="Consume on first redemption"),
    },
)


token_issue_response_model = enrollment_ns.model(
    "EnrollmentTokenIssueResponse",
    {
        "token_id": fields.String(description="Server-assigned token UUID"),
        "secret": fields.String(description="Secret returned exactly once"),
        "project_id": fields.String(description="Scope project UUID"),
        "pod_name": fields.String(description="Pod the token commits to"),
        "expires_at": fields.String(description="ISO-8601 expiry"),
        "algorithm_name": fields.String(description="Issuer algorithm"),
    },
)


token_view_model = enrollment_ns.model(
    "EnrollmentTokenView",
    {
        "token_id": fields.String(description="Token UUID"),
        "project_id": fields.String(description="Scope project UUID"),
        "pod_name": fields.String(description="Pod scope"),
        "status": fields.String(description="PENDING | REDEEMED | EXPIRED | REVOKED"),
        "issued_at": fields.String(description="ISO-8601 issue timestamp"),
        "expires_at": fields.String(description="ISO-8601 expiry timestamp"),
        "one_shot": fields.Boolean(description="One-shot flag"),
        "algorithm_name": fields.String(description="Issuer algorithm"),
        "redeemed_at": fields.String(description="ISO-8601 redemption timestamp"),
        "redeemed_by_client_id": fields.String(description="Redeeming client UUID"),
    },
)


redeem_request_model = enrollment_ns.model(
    "EnrollmentRedeemRequest",
    {
        "secret": fields.String(required=True, description="Secret returned at issue time"),
        "pod_name": fields.String(required=True, description="Pod name the agent claims"),
        "agent_version": fields.String(required=False, description="Reported agent version"),
        "transport_name": fields.String(required=False, description="Transport the agent plans to use"),
        "extras": fields.Raw(required=False, description="Opaque additional fields"),
        "csr_pem": fields.String(
            required=False,
            description=(
                "Optional base64-encoded PEM CSR. When supplied the "
                "service signs it against the internal CA and returns "
                "the issued cert fields alongside the bearer token."
            ),
        ),
    },
)


redeem_response_model = enrollment_ns.model(
    "EnrollmentRedeemResponse",
    {
        "client_id": fields.String(description="Server-assigned client UUID"),
        "project_id": fields.String(description="Scope project UUID"),
        "pod_name": fields.String(description="Pod name"),
        "bearer_token": fields.String(description="Bearer token for future requests"),
        "bearer_algorithm": fields.String(description="Algorithm that produced the digest"),
        "cert_serial": fields.String(
            description="Hex serial of the issued cert, or empty when CSR was not supplied.",
        ),
        "cert_pem": fields.String(
            description="Base64-encoded PEM of the issued cert, or empty.",
        ),
        "cert_chain_pem": fields.String(
            description="Base64-encoded PEM of the issuer chain, or empty.",
        ),
    },
)


revoke_client_request_model = enrollment_ns.model(
    "ClientRevokeRequest",
    {
        "reason": fields.String(
            required=True,
            description="Revocation reason: rotated, decommissioned, compromised, admin_request",
        ),
        "note": fields.String(required=False, description="Optional free-form operator note"),
        "cert_serial": fields.String(
            required=False,
            description=(
                "Optional specific cert serial being revoked. Defaults "
                "to the client's most recently-issued cert serial."
            ),
        ),
    },
)


revoke_client_response_model = enrollment_ns.model(
    "ClientRevokeResponse",
    {
        "client_id": fields.String(description="Client UUID"),
        "status": fields.String(description="Post-revoke client status"),
        "cert_serial": fields.String(description="Cert serial recorded on the revocation row, or empty"),
        "reason": fields.String(description="Reason code applied"),
    },
)


def _get_db_session():
    db_session = getattr(g, "db_session", None)
    if db_session is None:
        enrollment_ns.abort(503, "Request-scoped db_session not configured")
    return db_session


def _parse_status(raw: str):
    if raw is None or len(raw) == 0:
        return None
    try:
        rtnval = TokenStatus(raw)
    except ValueError:
        enrollment_ns.abort(400, "Unknown status: {}".format(raw))
    return rtnval


def _decode_csr_field(raw: str) -> bytes:
    """
        Accept either raw PEM text or base64-encoded PEM for the
        CSR field and return the PEM bytes. Returns ``b""`` for
        empty input.

        :param raw: Value submitted on the ``csr_pem`` request field.

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
        enrollment_ns.abort(400, "csr_pem must be PEM text or base64-encoded PEM")
    return rtnval


def _encode_pem_field(raw: bytes) -> str:
    """
        Encode a PEM bytes field as base64 for transport over the
        JSON response surface. Returns an empty string when the field
        is ``None`` so the JSON response stays strictly stringly-typed.

        :param raw: PEM bytes (possibly ``None``).

        :returns: Base64 string or empty string.
    """
    if raw is None or len(raw) == 0:
        return ""
    rtnval = base64.b64encode(raw).decode("ascii")
    return rtnval


def _parse_revocation_reason(raw: str) -> RevocationReason:
    """
        Parse an inbound ``reason`` string into :class:`RevocationReason`
        or abort with HTTP 400.

        :param raw: Raw string from the request body.

        :returns: Enum value.
    """
    try:
        rtnval = RevocationReason(raw)
    except ValueError:
        accepted = [v.value for v in RevocationReason]
        err_lines = ["Unknown revocation reason."]
        err_lines.append("RECEIVED: {}".format(raw))
        err_lines.append("ACCEPTED: {}".format(accepted))
        enrollment_ns.abort(400, " | ".join(err_lines))
    return rtnval


def _token_to_dict(view: TokenView) -> dict:
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


@enrollment_ns.route("")
class EnrollmentTokenCollection(Resource):
    """
        POST ``/api/v1/enrollment-tokens`` — admin issue.
        GET  ``/api/v1/enrollment-tokens`` — admin list.
    """

    @enrollment_ns.expect(token_issue_request_model, validate=True)
    @enrollment_ns.marshal_with(token_issue_response_model, code=201)
    def post(self):
        db_session = _get_db_session()
        payload = request.get_json(force=True, silent=False)
        actor = getattr(g, "actor_user_id", None)

        ttl_seconds = int(payload.get("ttl_seconds", 0))
        if ttl_seconds <= 0:
            enrollment_ns.abort(400, "ttl_seconds must be > 0")

        issued = issue_enrollment_token(
            db_session=db_session,
            project_id=payload.get("project_id", ""),
            pod_name=payload.get("pod_name", ""),
            ttl_seconds=ttl_seconds,
            one_shot=bool(payload.get("one_shot", True)),
            issued_by=actor,
        )
        rtnval = ({
            "token_id": issued.token_id,
            "secret": issued.secret,
            "project_id": issued.project_id,
            "pod_name": issued.pod_name,
            "expires_at": issued.expires_at_iso,
            "algorithm_name": issued.algorithm_name,
        }, 201)
        return rtnval

    @enrollment_ns.marshal_list_with(token_view_model)
    def get(self):
        db_session = _get_db_session()
        project_id = request.args.get("project_id", None)
        status = _parse_status(request.args.get("status", ""))
        views = list_enrollment_tokens(
            db_session=db_session,
            project_id=project_id,
            status=status,
        )
        rtnval = [_token_to_dict(v) for v in views]
        return rtnval


@enrollment_ns.route("/<string:token_id>")
@enrollment_ns.param("token_id", "Token UUID")
class EnrollmentTokenResource(Resource):
    """
        DELETE ``/api/v1/enrollment-tokens/{token_id}`` — admin revoke.
    """

    def delete(self, token_id: str):
        db_session = _get_db_session()
        actor = getattr(g, "actor_user_id", None)

        try:
            revoke_enrollment_token(
                db_session=db_session,
                token_id=token_id,
                actor_user_id=actor,
            )
        except EnrollmentTokenNotFoundError as xcpt:
            enrollment_ns.abort(404, str(xcpt))

        rtnval = ({"token_id": token_id, "status": "revoked"}, 200)
        return rtnval


@enrollment_ns.route("/redeem")
class EnrollmentTokenRedemption(Resource):
    """
        POST ``/api/v1/enrollment-tokens/redeem`` — agent redeems a secret.
    """

    @enrollment_ns.expect(redeem_request_model, validate=True)
    @enrollment_ns.marshal_with(redeem_response_model)
    def post(self):
        db_session = _get_db_session()
        payload = request.get_json(force=True, silent=False)

        csr_raw = payload.get("csr_pem", "") or ""
        csr_pem = _decode_csr_field(csr_raw)
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
            enrollment_ns.abort(404, str(xcpt))
        except EnrollmentTokenInvalidError as xcpt:
            enrollment_ns.abort(400, str(xcpt))
        except EnrollmentRejectedError as xcpt:
            enrollment_ns.abort(403, str(xcpt))
        except ClientAlreadyExistsError as xcpt:
            enrollment_ns.abort(409, str(xcpt))
        except CsrScopeMismatchError as xcpt:
            enrollment_ns.abort(403, str(xcpt))
        except CsrValidationError as xcpt:
            enrollment_ns.abort(400, str(xcpt))
        except CertificateAuthorityUnavailableError as xcpt:
            enrollment_ns.abort(503, str(xcpt))

        rtnval = {
            "client_id": result.client_id,
            "project_id": result.project_id,
            "pod_name": result.pod_name,
            "bearer_token": result.bearer_token,
            "bearer_algorithm": result.bearer_algorithm,
            "cert_serial": result.cert_serial or "",
            "cert_pem": _encode_pem_field(result.cert_pem),
            "cert_chain_pem": _encode_pem_field(result.cert_chain_pem),
        }
        return rtnval


@enrollment_ns.route("/clients/<string:client_id>/revoke")
@enrollment_ns.param("client_id", "Client UUID")
class ClientRevocationResource(Resource):
    """
        POST ``/api/v1/enrollment-tokens/clients/{client_id}/revoke`` —
        admin revokes a client identity. Mounts under the enrollment
        namespace because the revocation state lives on the enrollment
        data model (``client_revocations``) and must share the RBAC
        gate with token rescission.
    """

    @enrollment_ns.expect(revoke_client_request_model, validate=True)
    @enrollment_ns.marshal_with(revoke_client_response_model)
    def post(self, client_id: str):
        db_session = _get_db_session()
        actor = getattr(g, "actor_user_id", None)
        body = request.get_json(force=True, silent=False)

        reason_raw = body.get("reason", "")
        if reason_raw is None or len(reason_raw) == 0:
            enrollment_ns.abort(400, "reason is required")
        reason = _parse_revocation_reason(reason_raw)

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
            enrollment_ns.abort(404, str(xcpt))

        rtnval = {
            "client_id": client_id,
            "status": "revoked",
            "cert_serial": cert_serial_in or "",
            "reason": reason.value,
        }
        return rtnval


def publish_namespaces(version_prefix: str):
    """
        Return namespace registrations for the v1 API wiring.

        :param version_prefix: Version prefix string (``/1``).

        :returns: List of (namespace, path) tuples.
    """
    rtnval = [(enrollment_ns, version_prefix + ENROLLMENT_NAMESPACE_PATH)]
    return rtnval
