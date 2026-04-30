"""
.. module:: audit.restapi.v1.auditblueprint
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: REST API v1 controller for /api/v1/audit.

.. moduleauthor:: Automation Mojo LLC

Migrated from Flask + flask-restx to automojo-webworks.
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

from automojo.pychestrate.webservice.audit.models import AuditRecord


AUDIT_BASE_PATH = "/api/v1/audit"


def _record_to_dict(record: AuditRecord) -> Dict[str, Any]:
    """
        Render an :class:`AuditRecord` as the REST response dict.
    """
    if record.actor_user_id is not None:
        actor_field = str(record.actor_user_id)
    else:
        actor_field = None
    if record.record_hash is not None:
        record_hash_field = bytes(record.record_hash).hex()
    else:
        record_hash_field = None
    if record.written_at is not None:
        written_at_field = record.written_at.isoformat()
    else:
        written_at_field = None
    rtnval = {
        "sequence_number": int(record.sequence_number),
        "record_id": str(record.record_id),
        "kind": record.kind,
        "source_topic": record.source_topic,
        "actor_user_id": actor_field,
        "target_ref": record.target_ref,
        "payload_json": record.payload_json,
        "record_hash_hex": record_hash_field,
        "written_at": written_at_field,
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


class AuditBlueprint(RestBlueprint):
    """
        Blueprint grouping the v1 ``/api/v1/audit`` endpoints.
    """

    base_path = AUDIT_BASE_PATH
    tags = ["audit", "v1"]

    @RestBlueprint.attach_at(
        path="/api/v1/audit",
        methods=["GET"],
        doc=Doc(
            summary="List audit records",
            description=(
                "Page the audit record stream by sequence_number "
                "descending. ``limit`` query parameter caps results "
                "(default 50, max 500)."
            ),
        ),
    )
    def list_records(request: Request) -> JSONResponse:
        """
            List the most recent audit records.
        """
        db_session = _require_db_session(request=request)

        limit_arg = request.query_params.get("limit", "50")
        try:
            limit = int(limit_arg)
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=400, detail="Invalid 'limit' argument",
            ) from exc

        if limit < 1:
            limit = 1
        if limit > 500:
            limit = 500

        rows = (
            db_session.query(AuditRecord)
            .order_by(AuditRecord.sequence_number.desc())
            .limit(limit)
            .all()
        )
        body = [_record_to_dict(record=row) for row in rows]
        rtnval = JSONResponse(content=body, status_code=200)
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/audit/{sequence_number:int}",
        methods=["GET"],
        doc=Doc(
            summary="Read audit record",
            description="Fetch one audit record by sequence_number.",
        ),
    )
    def read_record(request: Request) -> JSONResponse:
        """
            Fetch a single audit record by sequence_number.
        """
        db_session = _require_db_session(request=request)
        sequence_number = request.path_params.get("sequence_number")

        row = (
            db_session.query(AuditRecord)
            .filter(AuditRecord.sequence_number == sequence_number)
            .first()
        )
        if row is None:
            err_msg = "Audit record not found: {}".format(sequence_number)
            raise HTTPException(status_code=404, detail=err_msg)

        body = _record_to_dict(record=row)
        rtnval = JSONResponse(content=body, status_code=200)
        return rtnval
