"""
.. module:: secrets.restapi.v1.secretsblueprint
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: REST API v1 controller for /api/v1/secrets.

.. moduleauthor:: Automation Mojo LLC

Migrated from Flask + flask-restx to automojo-webworks. The REST surface
NEVER returns plaintext.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from typing import Any, Dict

from automojo.webworks.endpoints.doc import Doc
from automojo.webworks.endpoints.restblueprint import RestBlueprint
from automojo.webworks.routing.exceptions import HTTPException
from automojo.webworks.routing.request import Request
from automojo.webworks.routing.response import JSONResponse

from automojo.pychestrate.webservice.secrets.models import SecretRecord


SECRETS_BASE_PATH = "/api/v1/secrets"


def _record_to_dict(record: SecretRecord) -> Dict[str, Any]:
    """
        Render a :class:`SecretRecord` as a JSON-safe dict.
    """
    if record.current_version_id is not None:
        current_version_field = str(record.current_version_id)
    else:
        current_version_field = None
    if record.created_at is not None:
        created_at_field = record.created_at.isoformat()
    else:
        created_at_field = None
    if record.updated_at is not None:
        updated_at_field = record.updated_at.isoformat()
    else:
        updated_at_field = None
    rtnval = {
        "secret_ref": record.secret_ref,
        "backend_name": record.backend_name,
        "current_version_id": current_version_field,
        "created_at": created_at_field,
        "updated_at": updated_at_field,
    }
    return rtnval


def _require_db_session(*, request: Request) -> Any:
    db_session = getattr(request, "db_session", None)
    if db_session is None:
        err_lines = [
            "Request-scoped db_session not configured.",
            "DbSessionMiddleware must be installed in the pipeline.",
        ]
        err_msg = os.linesep.join(err_lines)
        raise HTTPException(status_code=503, detail=err_msg)
    return db_session


class SecretsBlueprint(RestBlueprint):
    """
        Blueprint grouping the v1 ``/api/v1/secrets`` metadata endpoints.
    """

    base_path = SECRETS_BASE_PATH
    tags = ["secrets", "v1"]

    @RestBlueprint.attach_at(
        path="/api/v1/secrets",
        methods=["GET"],
        doc=Doc(
            summary="List secret metadata",
            description="Return secret metadata only. Plaintext is never exposed.",
        ),
    )
    def list_secrets(request: Request) -> JSONResponse:
        """
            List secret metadata records ordered by ``secret_ref``.
        """
        db_session = _require_db_session(request=request)

        records = (
            db_session.query(SecretRecord)
            .order_by(SecretRecord.secret_ref.asc())
            .all()
        )
        body = [_record_to_dict(record=rec) for rec in records]
        rtnval = JSONResponse(content=body, status_code=200)
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/secrets/{secret_ref}",
        methods=["GET"],
        doc=Doc(
            summary="Read secret metadata",
            description=(
                "Return one secret's metadata. The Flask version "
                "matched ``<path:secret_ref>`` to allow ``/`` in the "
                "ref; on webworks the ref must currently be a single "
                "URL-encoded segment."
            ),
        ),
    )
    def read_secret(request: Request) -> JSONResponse:
        """
            Fetch a single secret's metadata by canonical ref.
        """
        db_session = _require_db_session(request=request)
        secret_ref = request.path_params.get("secret_ref", "")

        record = (
            db_session.query(SecretRecord)
            .filter(SecretRecord.secret_ref == secret_ref)
            .first()
        )
        if record is None:
            err_msg = "Secret not found: {}".format(secret_ref)
            raise HTTPException(status_code=404, detail=err_msg)

        body = _record_to_dict(record=record)
        rtnval = JSONResponse(content=body, status_code=200)
        return rtnval
