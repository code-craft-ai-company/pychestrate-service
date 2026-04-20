"""
.. module:: identity.flags.restapi.v1.flags_controller
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: REST API v1 controller for /api/v1/flags.

.. moduleauthor:: Automation Mojo LLC

M1 skeleton exposes POST ``/api/v1/flags`` (BOOLEAN / PERCENTAGE create)
and GET ``/api/v1/flags/{flag_key}`` (read current). Rollout mutation
and retire arrive in M2.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from flask import g, request
from flask_restx import Namespace, Resource, fields

from automojo.errors.exceptions import SemanticError

from automojo.pychestrate.webservice.identity.flags import flag_service
from automojo.pychestrate.webservice.identity.flags.exceptions import FlagAlreadyExistsError
from automojo.pychestrate.webservice.identity.flags.models import FeatureFlag, FlagKind


FLAGS_NAMESPACE_PATH = "/flags"


flags_ns = Namespace(
    "Flags v1",
    description="Feature flag lifecycle endpoints (1-feature-flags).",
)


flag_create_model = flags_ns.model(
    "FeatureFlagCreate",
    {
        "flag_key": fields.String(required=True, description="Unique flag key"),
        "flag_kind": fields.String(
            required=True, description="BOOLEAN | STRING | ENUM | PERCENTAGE"
        ),
        "default_value": fields.Raw(required=True, description="Encoded default value"),
        "rules": fields.Raw(required=False, description="Optional rules payload"),
    },
)


flag_response_model = flags_ns.model(
    "FeatureFlagResponse",
    {
        "flag_key": fields.String(description="Registered flag key"),
        "flag_kind": fields.String(description="Flag kind enum value"),
        "current_version": fields.Integer(description="Active version"),
        "state": fields.String(description="Flag state enum value"),
        "created_at": fields.String(description="Create timestamp"),
        "updated_at": fields.String(description="Update timestamp"),
    },
)


def _flag_to_dict(flag: FeatureFlag) -> dict:
    rtnval = {
        "flag_key": flag.flag_key,
        "flag_kind": flag.flag_kind.value if flag.flag_kind is not None else None,
        "current_version": int(flag.current_version),
        "state": flag.state.value if flag.state is not None else None,
        "created_at": flag.created_at.isoformat() if flag.created_at is not None else None,
        "updated_at": flag.updated_at.isoformat() if flag.updated_at is not None else None,
    }
    return rtnval


def _parse_kind(flag_kind_raw: str) -> FlagKind:
    try:
        kind = FlagKind(flag_kind_raw)
    except ValueError:
        raise SemanticError("Unknown flag_kind value: {}".format(flag_kind_raw))
    return kind


@flags_ns.route("")
class FlagsList(Resource):
    """
        POST ``/api/v1/flags`` — create a new flag.
    """

    @flags_ns.expect(flag_create_model, validate=True)
    @flags_ns.marshal_with(flag_response_model, code=201)
    def post(self):
        payload = request.get_json(force=True, silent=False)

        db_session = getattr(g, "db_session", None)
        if db_session is None:
            flags_ns.abort(503, "Request-scoped db_session not configured")

        flag_kind = _parse_kind(payload.get("flag_kind", ""))
        actor_user_id = getattr(g, "actor_user_id", None)

        try:
            flag = flag_service.create_flag(
                db_session=db_session,
                flag_key=payload.get("flag_key", ""),
                flag_kind=flag_kind,
                default_value=payload.get("default_value", None),
                rules=payload.get("rules", None),
                actor_user_id=actor_user_id,
            )
        except FlagAlreadyExistsError as xcpt:
            flags_ns.abort(409, str(xcpt))

        rtnval = (_flag_to_dict(flag), 201)
        return rtnval


@flags_ns.route("/<string:flag_key>")
@flags_ns.param("flag_key", "Registered flag key")
class FlagsDetail(Resource):
    """
        GET ``/api/v1/flags/{flag_key}`` — read current flag view.
    """

    @flags_ns.marshal_with(flag_response_model)
    def get(self, flag_key: str):
        db_session = getattr(g, "db_session", None)
        if db_session is None:
            flags_ns.abort(503, "Request-scoped db_session not configured")

        flag = db_session.query(FeatureFlag).filter(FeatureFlag.flag_key == flag_key).first()
        if flag is None:
            flags_ns.abort(404, "Feature flag not found: {}".format(flag_key))

        rtnval = _flag_to_dict(flag)
        return rtnval


def publish_namespaces(version_prefix: str):
    """
        Return namespace registrations for the v1 API wiring.

        :param version_prefix: Version prefix string (``/1``).

        :returns: List of (namespace, path) tuples.
    """
    rtnval = [(flags_ns, version_prefix + FLAGS_NAMESPACE_PATH)]
    return rtnval
