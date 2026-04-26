"""
.. module:: security.auth.restapi.v1.auth_controller
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: REST API v1 controller for /api/v1/auth.

.. moduleauthor:: Automation Mojo LLC

Implements the controller-facing endpoints for the
1-authentication feature:

* ``GET /api/v1/auth/providers`` — enumerate enabled
  credential modes for the login picker (P21b).
* ``POST /api/v1/auth/logout`` — close a session (M1 skeleton).
* ``POST /api/v1/auth/mfa/challenge`` — issue a fresh MFA
  challenge for the active actor (M2, T2.12).
* ``POST /api/v1/auth/mfa/verify`` — submit a response to
  consume an active MFA challenge (M2, T2.12).
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from flask import g, request
from flask_restx import Namespace, Resource, fields

from automojo.pychestrate.webservice.security.auth import (
    mfa_service,
    provider_directory,
    session_service,
)
from automojo.pychestrate.webservice.security.auth.exceptions import (
    MfaChallengeExpiredError,
    MfaChallengeRejectedError,
    MfaChallengeUnknownError,
    MfaEnrollmentNotFoundError,
    MfaEnrollmentNotVerifiedError,
    MfaMethodUnknownError,
)


AUTH_NAMESPACE_PATH = "/auth"


auth_ns = Namespace(
    "Auth v1",
    description="Authentication flows (1-authentication).",
)


logout_model = auth_ns.model(
    "AuthLogout",
    {
        "session_id": fields.String(required=True, description="Session id to close"),
    },
)


mfa_challenge_model = auth_ns.model(
    "MfaChallenge",
    {
        "user_id": fields.String(
            required=True,
            description="Authenticated user id requesting the challenge.",
        ),
        "method_name": fields.String(
            required=True,
            description="MFA method to challenge against (e.g. 'totp').",
        ),
    },
)


mfa_verify_model = auth_ns.model(
    "MfaVerify",
    {
        "challenge_id": fields.String(
            required=True,
            description="Id returned by /auth/mfa/challenge.",
        ),
        "response": fields.Raw(
            required=True,
            description="Per-method response payload (e.g. {'code': '123456'}).",
        ),
    },
)


@auth_ns.route("/providers")
class AuthProviders(Resource):
    """
        Resource that exposes GET ``/api/v1/auth/providers``.

        Returns the list of enabled credential modes the
        login picker renders. Each entry carries the
        ``provider_name``, ``kind``, ``display_label``, and
        the ``login_path`` the controller submits to.
    """

    def get(self):
        modes = provider_directory.list_enabled_credential_modes()
        body = {
            "providers": [
                {
                    "kind": m.kind.value,
                    "provider_name": m.provider_name,
                    "display_label": m.display_label,
                    "login_path": m.login_path,
                    "enabled": m.enabled,
                }
                for m in modes
            ],
        }
        rtnval = (body, 200)
        return rtnval


@auth_ns.route("/logout")
class AuthLogout(Resource):
    """
        Resource that exposes POST ``/api/v1/auth/logout``.
    """

    @auth_ns.expect(logout_model, validate=True)
    def post(self):
        payload = request.get_json(force=True, silent=False)
        session_id = payload.get("session_id", "")

        db_session = getattr(g, "db_session", None)
        if db_session is None:
            auth_ns.abort(503, "Request-scoped db_session not configured")

        session_service.close_session(db_session=db_session, session_id=session_id)
        rtnval = ({"session_id": session_id, "status": "closed"}, 200)
        return rtnval


@auth_ns.route("/mfa/challenge")
class AuthMfaChallenge(Resource):
    """
        Resource that exposes POST ``/api/v1/auth/mfa/challenge``.

        Issues a fresh challenge for the (user, method) row and
        stashes it in the active-challenge store so a follow-up
        ``/auth/mfa/verify`` can consume it.
    """

    @auth_ns.expect(mfa_challenge_model, validate=True)
    def post(self):
        payload = request.get_json(force=True, silent=False)
        user_id = str(payload.get("user_id", ""))
        method_name = str(payload.get("method_name", ""))

        db_session = getattr(g, "db_session", None)
        if db_session is None:
            auth_ns.abort(503, "Request-scoped db_session not configured")
        if len(user_id) == 0:
            auth_ns.abort(400, "user_id must be non-empty")
        if len(method_name) == 0:
            auth_ns.abort(400, "method_name must be non-empty")

        try:
            challenge = mfa_service.initiate_challenge(
                db_session=db_session,
                user_id=user_id,
                method_name=method_name,
            )
        except MfaMethodUnknownError:
            auth_ns.abort(404, "method_unknown")
        except MfaEnrollmentNotFoundError:
            auth_ns.abort(404, "enrollment_not_found")
        except MfaEnrollmentNotVerifiedError:
            auth_ns.abort(409, "enrollment_not_verified")

        body = {
            "challenge_id": challenge.challenge_id,
            "method_name": challenge.method_name,
            "user_id": challenge.user_id,
            "issued_at": challenge.issued_at.isoformat(),
            "expires_at": challenge.expires_at.isoformat(),
            "payload": dict(challenge.payload),
        }
        rtnval = (body, 201)
        return rtnval


@auth_ns.route("/mfa/verify")
class AuthMfaVerify(Resource):
    """
        Resource that exposes POST ``/api/v1/auth/mfa/verify``.

        Consumes the named challenge from the active-challenge
        store, verifies the response against the underlying
        :class:`MFAMethodExtension`, and emits the matching
        challenge-verified or challenge-rejected event.
    """

    @auth_ns.expect(mfa_verify_model, validate=True)
    def post(self):
        payload = request.get_json(force=True, silent=False)
        challenge_id = str(payload.get("challenge_id", ""))
        response_fields = payload.get("response", None)

        db_session = getattr(g, "db_session", None)
        if db_session is None:
            auth_ns.abort(503, "Request-scoped db_session not configured")
        if len(challenge_id) == 0:
            auth_ns.abort(400, "challenge_id must be non-empty")
        if response_fields is None or not isinstance(response_fields, dict):
            auth_ns.abort(400, "response must be an object")

        try:
            outcome = mfa_service.verify_challenge(
                db_session=db_session,
                challenge_id=challenge_id,
                response_fields=response_fields,
            )
        except MfaChallengeUnknownError:
            auth_ns.abort(404, "challenge_unknown")
        except MfaChallengeExpiredError:
            auth_ns.abort(410, "challenge_expired")
        except MfaChallengeRejectedError:
            auth_ns.abort(401, "challenge_rejected")
        except MfaEnrollmentNotFoundError:
            auth_ns.abort(404, "enrollment_not_found")

        body = {
            "challenge_id": challenge_id,
            "accepted": outcome.accepted,
            "reason": outcome.reason,
        }
        rtnval = (body, 200)
        return rtnval


def publish_namespaces(version_prefix: str):
    """
        Return namespace registrations for the v1 API wiring.

        :param version_prefix: Version prefix string (``/1``).

        :returns: List of (namespace, path) tuples.
    """
    rtnval = [(auth_ns, version_prefix + AUTH_NAMESPACE_PATH)]
    return rtnval
