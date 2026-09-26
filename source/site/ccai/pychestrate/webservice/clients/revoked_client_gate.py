"""
.. module:: clients.revoked_client_gate
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Refuse pod requests whose client certificate belongs to a
               revoked client.

.. moduleauthor:: Code Craft AI LLC

Revoking a client does not make its certificate invalid: the TLS
terminator verifies the certificate against the enrollment CA and has
no revocation list, and the pod-facing routes only compare the
certificate's common name (the client id) with the client id they act
on. A revoked pod therefore kept heartbeating, long-polling for
dispatches and posting results.

:class:`RevokedClientGateMiddleware` runs after the database-session
middleware and answers 403 to every request whose verified client
certificate names a REVOKED client. It is installed with the
certificate identity middleware
(:func:`clients.mtls_identity.install_client_certificate_identity`),
so every app that accepts pod certificates also refuses revoked ones.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import logging
import uuid

from typing import Any, Callable, Optional

from ccai.pychestrate.webservice.clients.enums import ClientStatus
from ccai.pychestrate.webservice.clients.models import Client


REVOKED_CLIENT_GATE_MIDDLEWARE_NAME: str = "pychestrate-revoked-client-gate"

_LOGGER = logging.getLogger("pychestrate.clients.revoked_client_gate")


def _as_client_id(*, raw: Any) -> Optional[str]:
    """
        :param raw: A certificate common name.

        :returns: The canonical client UUID text, or None when ``raw``
                  is not a UUID (no client can have that id).
    """
    try:
        rtnval = str(uuid.UUID(str(raw)))
    except (ValueError, TypeError, AttributeError):
        rtnval = None
    return rtnval


def is_client_revoked(*, db_session: Any, client_id: str) -> bool:
    """
        :param db_session: Active SQLAlchemy session.
        :param client_id: Client UUID.

        :returns: True when the client exists and is REVOKED.
    """
    row = (
        db_session.query(Client.status)
        .filter(Client.client_id == client_id)
        .first()
    )
    rtnval = row is not None and row[0] == ClientStatus.REVOKED
    return rtnval


class RevokedClientGateMiddleware:
    """
        WebWorks pipeline middleware answering 403 when the request's
        verified client certificate (``request.mtls_client_cn``) names a
        revoked client. Requests without a certificate, or without a
        database session, pass through: the routes that need a pod
        identity refuse those themselves.
    """

    name: str = REVOKED_CLIENT_GATE_MIDDLEWARE_NAME

    def __call__(self, request: Any, call_next: Callable[[Any], Any]) -> Any:
        """
            :param request: Webworks Request.
            :param call_next: Next callable in the pipeline.

            :returns: The downstream response, or a 403 problem response.
        """
        client_id = None
        db_session = getattr(request, "db_session", None)
        client_cn = getattr(request, "mtls_client_cn", None)
        if client_cn is not None and db_session is not None:
            client_id = _as_client_id(raw=client_cn)

        if client_id is not None and is_client_revoked(db_session=db_session, client_id=client_id):
            from ccai.pychestrate.webservice.api.problem_json_webworks import (  # noqa: E402
                problem_response_for_http_status,
            )
            _LOGGER.warning(
                "clients.revoked_client_gate.refused client_id=%s path=%s",
                client_id, getattr(request, "path", ""),
            )
            rtnval = problem_response_for_http_status(
                status=403,
                detail="This pod's client has been revoked, so its certificate is no longer "
                       "accepted. Enroll the pod again with a new enrollment token.",
                instance=getattr(request, "path", None),
                extensions={"client_id": client_id},
            )
            return rtnval

        rtnval = call_next(request)
        return rtnval


__all__ = [
    "REVOKED_CLIENT_GATE_MIDDLEWARE_NAME",
    "RevokedClientGateMiddleware",
    "is_client_revoked",
]
