"""
.. module:: audit.restapi.v1.audit_controller
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: REST API v1 controller for /api/v1/audit.

.. moduleauthor:: Automation Mojo LLC

M1 skeleton exposes GET ``/api/v1/audit`` and GET
``/api/v1/audit/{sequence_number}``. Chain verification and the
``/sinks`` surface land in M2.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from flask import g, request
from flask_restx import Namespace, Resource, fields

from automojo.pychestrate.webservice.audit.models import AuditRecord


AUDIT_NAMESPACE_PATH = "/audit"


audit_ns = Namespace(
    "Audit v1",
    description="Audit record query endpoints (1-audit-log).",
)


audit_record_model = audit_ns.model(
    "AuditRecord",
    {
        "sequence_number": fields.Integer(description="Monotonic record number"),
        "record_id": fields.String(description="Stable external id"),
        "kind": fields.String(description="Registered audit kind"),
        "source_topic": fields.String(description="Originating bus topic"),
        "actor_user_id": fields.String(description="Acting principal id"),
        "target_ref": fields.String(description="Canonical ref of affected entity"),
        "payload_json": fields.Raw(description="Structured payload"),
        "record_hash_hex": fields.String(description="Hex-encoded record hash"),
        "written_at": fields.String(description="Server-time write timestamp"),
    },
)


def _record_to_dict(record: AuditRecord) -> dict:
    rtnval = {
        "sequence_number": int(record.sequence_number),
        "record_id": str(record.record_id),
        "kind": record.kind,
        "source_topic": record.source_topic,
        "actor_user_id": str(record.actor_user_id) if record.actor_user_id is not None else None,
        "target_ref": record.target_ref,
        "payload_json": record.payload_json,
        "record_hash_hex": bytes(record.record_hash).hex() if record.record_hash is not None else None,
        "written_at": record.written_at.isoformat() if record.written_at is not None else None,
    }
    return rtnval


@audit_ns.route("")
class AuditList(Resource):
    """
        GET ``/api/v1/audit`` — page the audit record stream.
    """

    @audit_ns.marshal_list_with(audit_record_model)
    def get(self):
        db_session = getattr(g, "db_session", None)
        if db_session is None:
            audit_ns.abort(503, "Request-scoped db_session not configured")

        limit_arg = request.args.get("limit", default="50")
        try:
            limit = int(limit_arg)
        except ValueError:
            audit_ns.abort(400, "Invalid 'limit' argument")

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
        rtnval = [_record_to_dict(row) for row in rows]
        return rtnval


@audit_ns.route("/<int:sequence_number>")
@audit_ns.param("sequence_number", "Audit record sequence number")
class AuditDetail(Resource):
    """
        GET ``/api/v1/audit/{sequence_number}`` — fetch one audit record.
    """

    @audit_ns.marshal_with(audit_record_model)
    def get(self, sequence_number: int):
        db_session = getattr(g, "db_session", None)
        if db_session is None:
            audit_ns.abort(503, "Request-scoped db_session not configured")

        row = (
            db_session.query(AuditRecord)
            .filter(AuditRecord.sequence_number == sequence_number)
            .first()
        )
        if row is None:
            audit_ns.abort(404, "Audit record not found: {}".format(sequence_number))

        rtnval = _record_to_dict(row)
        return rtnval


def publish_namespaces(version_prefix: str):
    """
        Return namespace registrations for the v1 API wiring.

        :param version_prefix: Version prefix string (``/1``).

        :returns: List of (namespace, path) tuples.
    """
    rtnval = [(audit_ns, version_prefix + AUDIT_NAMESPACE_PATH)]
    return rtnval
