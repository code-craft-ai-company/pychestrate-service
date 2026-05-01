"""
.. module:: identity.flags.restapi.v1.flags_controller
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: REST API v1 controller for /api/v1/flags.

.. moduleauthor:: Automation Mojo LLC

The M2 surface exposes the full lifecycle: list, read, create, update,
retire, version history, and on-demand evaluation. The evaluation
endpoint accepts a :class:`FlagContext` JSON body and is consumed by
``8-cli`` and integration tests.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Tuple

from flask import g, request
from flask_restx import Namespace, Resource, fields

from automojo.errors.exceptions import SemanticError

from automojo.pychestrate.webservice.identity.flags import (
    backend_router,
    flag_evaluator,
    flag_service,
)
from automojo.pychestrate.webservice.identity.flags.exceptions import (
    FlagAlreadyExistsError,
    FlagNotFoundError,
)
from automojo.pychestrate.webservice.identity.flags.models import (
    FeatureFlag,
    FeatureFlagVersion,
    FlagContext,
    FlagKind,
)


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


flag_update_model = flags_ns.model(
    "FeatureFlagUpdate",
    {
        "default_value": fields.Raw(required=True, description="Updated default value"),
        "rules": fields.Raw(required=False, description="Updated rules payload"),
        "flag_kind": fields.String(
            required=False,
            description="Optional kind echo for redundant validation; must equal persisted kind",
        ),
    },
)


flag_retire_model = flags_ns.model(
    "FeatureFlagRetire",
    {
        "grace_seconds": fields.Integer(
            required=False,
            description="Grace window before removal (default 7 days = 604800)",
        ),
    },
)


flag_evaluate_model = flags_ns.model(
    "FeatureFlagEvaluate",
    {
        "bucketing_key": fields.String(
            required=True, description="Stable key used for hash-based rollout"
        ),
        "user_id": fields.String(required=False, description="Optional user identifier"),
        "project_id": fields.String(required=False, description="Optional project identifier"),
        "attributes": fields.Raw(
            required=False,
            description="Optional dict of attribute key/value pairs",
        ),
        "default": fields.Raw(
            required=False,
            description="Fallback value when the flag is unknown or rules do not apply",
        ),
    },
)


flag_response_model = flags_ns.model(
    "FeatureFlagResponse",
    {
        "flag_key": fields.String(description="Registered flag key"),
        "flag_kind": fields.String(description="Flag kind enum value"),
        "current_version": fields.Integer(description="Active version"),
        "state": fields.String(description="Flag state enum value"),
        "retired_at": fields.String(description="Retire timestamp", required=False),
        "grace_expires_at": fields.String(description="Grace expiration", required=False),
        "created_at": fields.String(description="Create timestamp"),
        "updated_at": fields.String(description="Update timestamp"),
    },
)


flag_version_response_model = flags_ns.model(
    "FeatureFlagVersionResponse",
    {
        "flag_key": fields.String(description="Owning flag key"),
        "version": fields.Integer(description="Version number"),
        "default_value": fields.Raw(description="Stored default value"),
        "rules_json": fields.Raw(description="Stored rules payload"),
        "created_at": fields.String(description="Version create timestamp"),
    },
)


flag_evaluate_response_model = flags_ns.model(
    "FeatureFlagEvaluateResponse",
    {
        "flag_key": fields.String(description="Evaluated flag key"),
        "value": fields.Raw(description="Evaluated value"),
        "version": fields.Integer(description="Active version at evaluation"),
    },
)


flag_backend_response_model = flags_ns.model(
    "FeatureFlagBackendResponse",
    {
        "backend_name": fields.String(description="Backend identifier"),
        "flag_key_pattern": fields.String(description="Glob pattern claimed"),
        "precedence": fields.Integer(description="Lower-wins precedence"),
    },
)


def _flag_to_dict(flag: FeatureFlag) -> dict:
    rtnval = {
        "flag_key": flag.flag_key,
        "flag_kind": flag.flag_kind.value if flag.flag_kind is not None else None,
        "current_version": int(flag.current_version),
        "state": flag.state.value if flag.state is not None else None,
        "retired_at": flag.retired_at.isoformat() if flag.retired_at is not None else None,
        "grace_expires_at": (
            flag.grace_expires_at.isoformat() if flag.grace_expires_at is not None else None
        ),
        "created_at": flag.created_at.isoformat() if flag.created_at is not None else None,
        "updated_at": flag.updated_at.isoformat() if flag.updated_at is not None else None,
    }
    return rtnval


def _version_to_dict(version: FeatureFlagVersion) -> dict:
    rtnval = {
        "flag_key": version.flag_key,
        "version": int(version.version),
        "default_value": version.default_value,
        "rules_json": version.rules_json,
        "created_at": version.created_at.isoformat() if version.created_at is not None else None,
    }
    return rtnval


def _parse_kind(flag_kind_raw: str) -> FlagKind:
    try:
        kind = FlagKind(flag_kind_raw)
    except ValueError:
        raise SemanticError("Unknown flag_kind value: {}".format(flag_kind_raw))
    return kind


def _get_session_or_abort():
    db_session = getattr(g, "db_session", None)
    if db_session is None:
        flags_ns.abort(503, "Request-scoped db_session not configured")
    rtnval = db_session
    return rtnval


def _build_context_from_payload(payload: dict) -> FlagContext:
    bucketing_key = payload.get("bucketing_key", "")
    if bucketing_key is None or len(str(bucketing_key)) == 0:
        flags_ns.abort(400, "bucketing_key is required")

    user_id_raw = payload.get("user_id", None)
    project_id_raw = payload.get("project_id", None)
    attributes_raw = payload.get("attributes", None)

    attribute_pairs: Tuple[Tuple[str, str], ...] = tuple()
    if attributes_raw is not None:
        if isinstance(attributes_raw, dict):
            collected = []
            for attr_key, attr_value in attributes_raw.items():
                collected.append((str(attr_key), str(attr_value)))
            collected.sort(key=lambda pair: pair[0])
            attribute_pairs = tuple(collected)
        else:
            flags_ns.abort(400, "attributes must be a JSON object")

    rtnval = FlagContext(
        bucketing_key=str(bucketing_key),
        user_id=str(user_id_raw) if user_id_raw is not None else None,
        project_id=str(project_id_raw) if project_id_raw is not None else None,
        attributes=attribute_pairs,
    )
    return rtnval


@flags_ns.route("")
class FlagsList(Resource):
    """
        ``/api/v1/flags`` — list and create.
    """

    @flags_ns.marshal_list_with(flag_response_model)
    def get(self):
        """
            List every registered flag, ordered by ``flag_key``.
        """
        db_session = _get_session_or_abort()
        flags = flag_service.list_flags(db_session=db_session)
        rtnval = [_flag_to_dict(flag) for flag in flags]
        return rtnval

    @flags_ns.expect(flag_create_model, validate=True)
    @flags_ns.marshal_with(flag_response_model, code=201)
    def post(self):
        """
            Create a new flag at version 1.
        """
        payload = request.get_json(force=True, silent=False)
        db_session = _get_session_or_abort()

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
        except SemanticError as xcpt:
            flags_ns.abort(422, str(xcpt))

        rtnval = (_flag_to_dict(flag), 201)
        return rtnval


@flags_ns.route("/<string:flag_key>")
@flags_ns.param("flag_key", "Registered flag key")
class FlagsDetail(Resource):
    """
        ``/api/v1/flags/{flag_key}`` — read / update.
    """

    @flags_ns.marshal_with(flag_response_model)
    def get(self, flag_key: str):
        """
            Read the current view of a flag.
        """
        db_session = _get_session_or_abort()

        flag = db_session.query(FeatureFlag).filter(FeatureFlag.flag_key == flag_key).first()
        if flag is None:
            flags_ns.abort(404, "Feature flag not found: {}".format(flag_key))

        rtnval = _flag_to_dict(flag)
        return rtnval

    @flags_ns.expect(flag_update_model, validate=True)
    @flags_ns.marshal_with(flag_response_model)
    def patch(self, flag_key: str):
        """
            Bump the active version with new rules / default. flag_kind
            is immutable; passing a different kind returns 422.
        """
        payload = request.get_json(force=True, silent=False)
        db_session = _get_session_or_abort()
        actor_user_id = getattr(g, "actor_user_id", None)

        kind_raw = payload.get("flag_kind", None)
        kind_for_redundant_check = None
        if kind_raw is not None:
            kind_for_redundant_check = _parse_kind(kind_raw)

        try:
            flag = flag_service.update_flag_rules(
                db_session=db_session,
                flag_key=flag_key,
                flag_kind=kind_for_redundant_check,
                default_value=payload.get("default_value", None),
                rules=payload.get("rules", None),
                actor_user_id=actor_user_id,
            )
        except FlagNotFoundError as xcpt:
            flags_ns.abort(404, str(xcpt))
        except SemanticError as xcpt:
            flags_ns.abort(422, str(xcpt))

        rtnval = _flag_to_dict(flag)
        return rtnval


@flags_ns.route("/<string:flag_key>/retire")
@flags_ns.param("flag_key", "Registered flag key")
class FlagRetire(Resource):
    """
        ``POST /api/v1/flags/{flag_key}/retire`` — retire with grace.
    """

    @flags_ns.expect(flag_retire_model, validate=False)
    @flags_ns.marshal_with(flag_response_model)
    def post(self, flag_key: str):
        payload = request.get_json(force=True, silent=True) or {}
        db_session = _get_session_or_abort()
        actor_user_id = getattr(g, "actor_user_id", None)

        grace_seconds_raw = payload.get("grace_seconds", flag_service.DEFAULT_GRACE_SECONDS)
        try:
            grace_seconds = int(grace_seconds_raw)
        except (TypeError, ValueError):
            flags_ns.abort(400, "grace_seconds must be an integer number of seconds")

        try:
            flag = flag_service.retire_flag(
                db_session=db_session,
                flag_key=flag_key,
                grace_seconds=grace_seconds,
                actor_user_id=actor_user_id,
            )
        except FlagNotFoundError as xcpt:
            flags_ns.abort(404, str(xcpt))
        except SemanticError as xcpt:
            flags_ns.abort(422, str(xcpt))

        rtnval = _flag_to_dict(flag)
        return rtnval


@flags_ns.route("/<string:flag_key>/history")
@flags_ns.param("flag_key", "Registered flag key")
class FlagHistory(Resource):
    """
        ``GET /api/v1/flags/{flag_key}/history`` — list versions.
    """

    @flags_ns.marshal_list_with(flag_version_response_model)
    def get(self, flag_key: str):
        db_session = _get_session_or_abort()

        try:
            versions = flag_service.list_flag_versions(
                db_session=db_session, flag_key=flag_key
            )
        except FlagNotFoundError as xcpt:
            flags_ns.abort(404, str(xcpt))

        rtnval = [_version_to_dict(version) for version in versions]
        return rtnval


@flags_ns.route("/<string:flag_key>/evaluate")
@flags_ns.param("flag_key", "Registered flag key")
class FlagEvaluate(Resource):
    """
        ``POST /api/v1/flags/{flag_key}/evaluate`` — evaluate the flag
        against a caller-supplied :class:`FlagContext`.
    """

    @flags_ns.expect(flag_evaluate_model, validate=True)
    @flags_ns.marshal_with(flag_evaluate_response_model)
    def post(self, flag_key: str):
        payload = request.get_json(force=True, silent=False)
        db_session = _get_session_or_abort()

        context = _build_context_from_payload(payload)
        default = payload.get("default", None)

        try:
            value = flag_evaluator.evaluate_flag(
                db_session=db_session,
                flag_key=flag_key,
                context=context,
                default=default,
            )
        except SemanticError as xcpt:
            flags_ns.abort(422, str(xcpt))

        flag = db_session.query(FeatureFlag).filter(FeatureFlag.flag_key == flag_key).first()
        version_value = int(flag.current_version) if flag is not None else 0

        rtnval = {
            "flag_key": flag_key,
            "value": value,
            "version": version_value,
        }
        return rtnval


@flags_ns.route("/backends")
class FlagBackends(Resource):
    """
        ``GET /api/v1/flags/backends`` — list registered backends.
    """

    @flags_ns.marshal_list_with(flag_backend_response_model)
    def get(self):
        snapshot = backend_router.diagnostic_snapshot()
        rtnval = list(snapshot.values())
        rtnval.sort(key=lambda entry: entry.get("precedence", 1000))
        return rtnval


def publish_namespaces(version_prefix: str):
    """
        Return namespace registrations for the v1 API wiring.

        :param version_prefix: Version prefix string (``/1``).

        :returns: List of (namespace, path) tuples.
    """
    rtnval = [(flags_ns, version_prefix + FLAGS_NAMESPACE_PATH)]
    return rtnval
