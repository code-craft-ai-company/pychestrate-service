"""
.. module:: security.auth.restapi.v1.auth_controller
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: REST API v1 controller for /api/v1/auth.

.. moduleauthor:: Automation Mojo LLC

Implements the M1 skeleton of POST ``/api/v1/auth/logout`` — session
close is the first real flow that exercises the session service
end-to-end without requiring the Argon2id verifier to land.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from flask import g, request
from flask_restx import Namespace, Resource, fields

from automojo.pychestrate.webservice.security.auth import session_service


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


def publish_namespaces(version_prefix: str):
    """
        Return namespace registrations for the v1 API wiring.

        :param version_prefix: Version prefix string (``/1``).

        :returns: List of (namespace, path) tuples.
    """
    rtnval = [(auth_ns, version_prefix + AUTH_NAMESPACE_PATH)]
    return rtnval
