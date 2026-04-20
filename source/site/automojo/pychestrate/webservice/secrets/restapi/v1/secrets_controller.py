"""
.. module:: secrets.restapi.v1.secrets_controller
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: REST API v1 controller for /api/v1/secrets.

.. moduleauthor:: Automation Mojo LLC

M1 skeleton exposes GET ``/api/v1/secrets`` and GET ``/api/v1/secrets/{ref}``
returning metadata only. The REST surface NEVER returns plaintext.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from flask import g
from flask_restx import Namespace, Resource, fields

from automojo.pychestrate.webservice.secrets.models import SecretRecord


SECRETS_NAMESPACE_PATH = "/secrets"


secrets_ns = Namespace(
    "Secrets v1",
    description="Secret metadata endpoints (1-secrets-vault).",
)


secret_metadata_model = secrets_ns.model(
    "SecretMetadata",
    {
        "secret_ref": fields.String(description="Canonical secret reference"),
        "backend_name": fields.String(description="Owning backend name"),
        "current_version_id": fields.String(description="Currently active version id"),
        "created_at": fields.String(description="Create timestamp (ISO-8601)"),
        "updated_at": fields.String(description="Update timestamp (ISO-8601)"),
    },
)


def _record_to_dict(record: SecretRecord) -> dict:
    """
        Render a :class:`SecretRecord` as a JSON-safe dict.

        :param record: The persistent model instance.

        :returns: Plain dict suitable for JSON serialization.
    """
    rtnval = {
        "secret_ref": record.secret_ref,
        "backend_name": record.backend_name,
        "current_version_id": (
            str(record.current_version_id) if record.current_version_id is not None else None
        ),
        "created_at": record.created_at.isoformat() if record.created_at is not None else None,
        "updated_at": record.updated_at.isoformat() if record.updated_at is not None else None,
    }
    return rtnval


@secrets_ns.route("")
class SecretsList(Resource):
    """
        GET ``/api/v1/secrets`` — list secret metadata.
    """

    @secrets_ns.marshal_list_with(secret_metadata_model)
    def get(self):
        db_session = getattr(g, "db_session", None)
        if db_session is None:
            secrets_ns.abort(503, "Request-scoped db_session not configured")

        records = db_session.query(SecretRecord).order_by(SecretRecord.secret_ref.asc()).all()
        rtnval = [_record_to_dict(rec) for rec in records]
        return rtnval


@secrets_ns.route("/<path:secret_ref>")
@secrets_ns.param("secret_ref", "Canonical secret reference")
class SecretsDetail(Resource):
    """
        GET ``/api/v1/secrets/{secret_ref}`` — return metadata only.
    """

    @secrets_ns.marshal_with(secret_metadata_model)
    def get(self, secret_ref: str):
        db_session = getattr(g, "db_session", None)
        if db_session is None:
            secrets_ns.abort(503, "Request-scoped db_session not configured")

        record = db_session.query(SecretRecord).filter(SecretRecord.secret_ref == secret_ref).first()
        if record is None:
            secrets_ns.abort(404, "Secret not found: {}".format(secret_ref))

        rtnval = _record_to_dict(record)
        return rtnval


def publish_namespaces(version_prefix: str):
    """
        Return namespace registrations for the v1 API wiring.

        :param version_prefix: Version prefix string (``/1``).

        :returns: List of (namespace, path) tuples.
    """
    rtnval = [(secrets_ns, version_prefix + SECRETS_NAMESPACE_PATH)]
    return rtnval
