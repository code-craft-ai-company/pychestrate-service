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
    revoke_enrollment_token,
)
from automojo.pychestrate.webservice.clients.enums import TokenStatus
from automojo.pychestrate.webservice.clients.exceptions import (
    ClientAlreadyExistsError,
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

        enrollment_payload = EnrollmentPayload(
            pod_name=payload.get("pod_name", ""),
            agent_version=payload.get("agent_version", None),
            transport_name=payload.get("transport_name", None),
            extras=payload.get("extras", {}) or {},
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

        rtnval = {
            "client_id": result.client_id,
            "project_id": result.project_id,
            "pod_name": result.pod_name,
            "bearer_token": result.bearer_token,
            "bearer_algorithm": result.bearer_algorithm,
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
