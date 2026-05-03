"""
.. module:: secrets.restapi.v1.secrets_routes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-native REST routes for /api/v1/secrets.

.. moduleauthor:: Automation Mojo LLC

The production webservice runs on ``automojo.webworks`` (see
:mod:`app_pychestrate_main`). This module replaces the flask_restx
``secrets_controller`` next to it.

Two routes (M1, metadata only — never plaintext):

* ``GET /api/v1/secrets`` — list secret metadata.
* ``GET /api/v1/secrets/{secret_ref:path}`` — read one secret's
  metadata. The ``:path`` converter matches multi-segment refs
  like ``project/team/key`` (mirrors the flask
  ``<path:secret_ref>`` converter).

Error responses are RFC 7807 problem documents per the convention
in :mod:`api.problem_json_webworks`.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Optional

from automojo.webworks.routing.request import Request
from automojo.webworks.routing.response import JSONResponse, Response

from automojo.pychestrate.webservice.api.problem_json_webworks import (
    problem_response_for_http_status,
)
from automojo.pychestrate.webservice.secrets.models import SecretRecord


SECRETS_PATH = "/secrets"


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
        secret_ref: Optional[str] = None
    ) -> None:
    """
        Build a problem response from the request context and raise
        :class:`_ProblemAbort` so the handler returns the response.

        :param request: Incoming webworks request.
        :param status: HTTP status code.
        :param detail: Occurrence-specific explanation.
        :param secret_ref: Optional secret_ref to attach as an
                           extension member.

        :returns: Never returns; raises :class:`_ProblemAbort`.
    """
    extensions: Optional[dict] = None
    if secret_ref is not None:
        extensions = {"secret_ref": secret_ref}

    response = problem_response_for_http_status(
        status=status,
        detail=detail,
        instance=request.path,
        extensions=extensions,
    )
    raise _ProblemAbort(response)


def _resolve_db_session(request: Request) -> Optional[Any]:
    """
        Return the request-scoped db session attached by
        :class:`PychestrateSessionMiddleware`.

        :param request: Incoming webworks request.

        :returns: Session or None.
    """
    rtnval = getattr(request, "db_session", None)
    return rtnval


def _require_session(request: Request) -> Any:
    """
        Resolve the request-scoped db session or abort with a 503
        problem document.

        :param request: Incoming webworks request.

        :returns: Session.
        :raises: :class:`_ProblemAbort` (503).
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


def _record_to_dict(record: SecretRecord) -> dict:
    """
        Render a :class:`SecretRecord` ORM row as a JSON-safe dict.
        Metadata only — plaintext is NEVER returned.

        :param record: ORM record.

        :returns: JSON-friendly dict.
    """
    rtnval = {
        "secret_ref": record.secret_ref,
        "backend_name": record.backend_name,
        "current_version_id": (
            str(record.current_version_id)
            if record.current_version_id is not None else None
        ),
        "created_at": (
            record.created_at.isoformat()
            if record.created_at is not None else None
        ),
        "updated_at": (
            record.updated_at.isoformat()
            if record.updated_at is not None else None
        ),
    }
    return rtnval


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def handle_list_secrets(request: Request) -> Response:
    """
        ``GET /api/v1/secrets`` — list secret metadata, ordered by
        ``secret_ref`` ascending.

        :param request: Incoming webworks request.

        :returns: JSON response (200) carrying a list of metadata
                  dicts, or problem response on failure.
    """
    try:
        db_session = _require_session(request=request)
        records = (
            db_session.query(SecretRecord)
            .order_by(SecretRecord.secret_ref.asc())
            .all()
        )
        body = [_record_to_dict(record) for record in records]
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


def handle_read_secret(request: Request) -> Response:
    """
        ``GET /api/v1/secrets/{secret_ref:path}`` — read metadata
        for one secret. Returns 404 problem+json with the secret_ref
        as an extension member when the record does not exist.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with the metadata dict, or
                  problem response on failure.
    """
    secret_ref = request.path_params.get("secret_ref", "")
    try:
        db_session = _require_session(request=request)

        record = (
            db_session.query(SecretRecord)
            .filter(SecretRecord.secret_ref == secret_ref)
            .first()
        )
        if record is None:
            _abort_problem(
                request=request,
                status=404,
                detail="Secret not found: {}".format(secret_ref),
                secret_ref=secret_ref,
            )

        body = _record_to_dict(record)
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_secrets_routes(*, app: Any, version_prefix: str) -> None:
    """
        Attach the secrets metadata routes to a webworks application.

        Note that the fixed ``/secrets`` collection is registered
        BEFORE the ``/{secret_ref:path}`` parameterized route so the
        webworks router resolves the collection deterministically.

        :param app: WebWorks application built by
                    ``establish_webapp_persona``.
        :param version_prefix: Versioned API prefix (e.g.
                               ``"/api/v1"``).

        :returns: None.
    """
    base = version_prefix + SECRETS_PATH

    app.attach_route(base, methods=["GET"])(handle_list_secrets)
    app.attach_route(
        base + "/{secret_ref:path}", methods=["GET"]
    )(handle_read_secret)

    return


__all__ = [
    "SECRETS_PATH",
    "register_secrets_routes",
    "handle_list_secrets",
    "handle_read_secret",
]
