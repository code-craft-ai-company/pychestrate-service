"""
.. module:: ops.release.restapi.v1.release_channels_routes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks REST routes for the release_channels tag.

.. moduleauthor:: Code Craft AI LLC

Implements the release-channel operations from
``specs/openapi/pychestrate.yaml``:

* ``GET  /api/v1/release-channels``
* ``POST /api/v1/release-channels``
* ``GET  /api/v1/release-channels/{channel_id}``

DOMAIN NOTE -- the in-tree release facade
(``ops.release.release_service``) is the M1 milestone, which
ships ``publish_release``, ``get_release``, ``list_releases``, and
``get_current_manifest`` only. There is NO standalone "release
channel" CRUD entity: a *channel* is the fixed enum
``canary | beta | stable`` (``ops.release.models.ReleaseChannel``)
and the per-channel pointer lives on the ``release_channel_state``
table updated as a side effect of ``publish_release``.

This REST surface therefore models a release-channel resource as a
published *release* row -- the smallest unit a channel advertises.
The ``channel_id`` path parameter is the release UUID.

These channels distribute Pychestrate's own service and agent
builds (the UI calls the page "Pychestrate Updates"); they are not a
project's release channels. Publishing signs the release manifest
with the release-signing key; nothing installs that key at startup
yet, so the list reports ``meta.publishing_available: false`` with
the reason, and a publish attempt answers 503 with the same reason
(audit ORC-31: the UI only showed "HTTP 503").

The following are INTENTIONALLY NOT registered because the M1
domain ships no capability behind them -- promotion + rollback are
M2 milestones (see ``ops.release.errors.ReleaseBakeNotMetError`` /
``ReleaseNotActiveError`` and the ``ops.release.release_service``
module docstring):

* ``PATCH  /release-channels/{channel_id}`` -- releases are
  immutable once published.
* ``DELETE /release-channels/{channel_id}`` -- the release ledger
  is append-only; M2 transitions ``status`` instead of deleting.
* ``POST   /release-channels/{channel_id}:promote`` -- the
  ``promote_release`` facade entry point lands in M2.

Error responses are RFC 7807 problem documents emitted via
:mod:`api.problem_json_webworks`.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import logging

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ccai.webworks.routing.request import Request
from ccai.webworks.routing.response import JSONResponse, Response

from ccai.pychestrate.webservice.api.problem_json_webworks import (
    problem_response_for_http_status,
)
from ccai.pychestrate.webservice.ops.release import (
    manifest_signer,
    release_service,
)
from ccai.pychestrate.webservice.ops.release.errors import (
    ReleaseConflictError,
    ReleaseSigningKeyUnavailableError,
)
from ccai.pychestrate.webservice.ops.release.models import (
    ReleaseChannel,
    ReleaseComponent,
    ReleaseStatus,
)
from ccai.pychestrate.webservice.ops.release.release_aspects import (
    build_default_release_aspects,
)
from ccai.pychestrate.webservice.security.rbac import rbac_evaluator


RELEASE_CHANNELS_PATH = "/release-channels"

#: Why publishing is unavailable when no release-signing key is
#: installed -- shown by the list meta and the publish 503.
PUBLISHING_UNAVAILABLE_REASON = (
    "Publishing is unavailable: this server has no release-signing key,"
    " and this release cannot load one at startup, so Pychestrate"
    " updates cannot be signed and published from this server."
)

#: Problem-document ``reason`` of a publish refused for that cause.
SIGNING_KEY_MISSING = "signing_key_missing"

RELEASE_CHANNELS_READ_PERMISSION_KEY = "system:release_channels.read"
RELEASE_CHANNELS_WRITE_PERMISSION_KEY = "system:release_channels.write"

DEFAULT_PAGE_SIZE = 50
MIN_PAGE_SIZE = 1
MAX_PAGE_SIZE = 500

_LOGGER = logging.getLogger("pychestrate.release_channels.routes")


# ---------------------------------------------------------------------------
# Problem-flow plumbing
# ---------------------------------------------------------------------------


class _ProblemAbort(Exception):
    """
        Internal control-flow exception carrying a webworks
        problem response.
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
        extensions: Optional[Dict[str, Any]] = None
    ) -> None:
    """
        Build a problem response and raise :class:`_ProblemAbort`.

        :param request: Incoming webworks request.
        :param status: HTTP status code.
        :param detail: Occurrence-specific explanation.
        :param extensions: Optional namespaced extension members.

        :returns: Never returns.
    """
    response = problem_response_for_http_status(
        status=status,
        detail=detail,
        instance=request.path,
        extensions=extensions,
    )
    raise _ProblemAbort(response)


def _resolve_db_session(request: Request) -> Optional[Any]:
    """
        Return the request-scoped db session or ``None``.

        :param request: Incoming webworks request.

        :returns: SQLAlchemy session or None.
    """
    rtnval = getattr(request, "db_session", None)
    return rtnval


def _require_session(request: Request) -> Any:
    """
        Resolve the request-scoped db session or abort 503.

        :param request: Incoming webworks request.

        :returns: SQLAlchemy session.
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


def _resolve_auth_principal(request: Request) -> Optional[Any]:
    """
        Return the ``AuthPrincipal`` attached by the session
        middleware, or ``None`` for anonymous requests.

        :param request: Incoming webworks request.

        :returns: AuthPrincipal or None.
    """
    rtnval = getattr(request, "auth_principal", None)
    return rtnval


def _require_permission(
        *,
        request: Request,
        db_session: Any,
        permission_key: str
    ) -> Any:
    """
        Require the calling principal to hold ``permission_key``.

        :param request: Incoming webworks request.
        :param db_session: Active SQLAlchemy session.
        :param permission_key: Required ``system:*`` permission key.

        :returns: The :class:`AuthPrincipal`.
    """
    principal = _resolve_auth_principal(request=request)
    if principal is None:
        _abort_problem(
            request=request,
            status=401,
            detail="Authentication required.",
        )

    now = datetime.now(timezone.utc)
    decision = rbac_evaluator.check_permission(
        db_session=db_session,
        principal=principal,
        permission_key=permission_key,
        now=now,
    )
    if decision.allowed is False:
        _abort_problem(
            request=request,
            status=403,
            detail="Permission denied: {}".format(permission_key),
            extensions={"required_permission": permission_key},
        )
    rtnval = principal
    return rtnval


def _decode_json_object_or_abort(*, request: Request) -> Dict[str, Any]:
    """
        Decode the request body as a JSON object, aborting with
        422 on missing / malformed / non-dict bodies.

        :param request: Incoming webworks request.

        :returns: Decoded dict.
    """
    try:
        payload = request.json()
    except Exception:
        payload = None

    if payload is None:
        _abort_problem(
            request=request,
            status=422,
            detail="Request body must be JSON.",
        )
    if isinstance(payload, dict) is False:
        _abort_problem(
            request=request,
            status=422,
            detail="Request body must be a JSON object.",
        )

    rtnval = payload
    return rtnval


def _parse_positive_int(
        *,
        request: Request,
        name: str,
        raw: Optional[str],
        default: int,
        minimum: int,
        maximum: Optional[int] = None
    ) -> int:
    """
        Coerce a positive-integer query param with bounds checking.

        :param request: Incoming webworks request.
        :param name: Query-param name (for error context).
        :param raw: Raw query value or None.
        :param default: Fallback when the param is absent.
        :param minimum: Lower bound (inclusive).
        :param maximum: Optional upper bound (inclusive).

        :returns: Coerced integer.
    """
    if raw is None or len(raw) == 0:
        rtnval = default
        return rtnval

    try:
        candidate = int(raw)
    except ValueError:
        _abort_problem(
            request=request,
            status=400,
            detail="Query param '{}' must be an integer.".format(name),
            extensions={"query_param": name, "raw_value": raw},
        )
        candidate = default  # unreachable

    if candidate < minimum:
        _abort_problem(
            request=request,
            status=400,
            detail="Query param '{}' must be >= {}.".format(name, minimum),
            extensions={"query_param": name, "raw_value": raw},
        )
    if maximum is not None and candidate > maximum:
        _abort_problem(
            request=request,
            status=400,
            detail="Query param '{}' must be <= {}.".format(name, maximum),
            extensions={"query_param": name, "raw_value": raw},
        )

    rtnval = candidate
    return rtnval


def _resolve_enum_or_abort(
        *,
        request: Request,
        enum_cls: Any,
        field_name: str,
        raw_value: Any
    ) -> Any:
    """
        Resolve a string-valued enum member, aborting 422 on a
        missing or unrecognized value.

        :param request: Incoming webworks request.
        :param enum_cls: Target ``str``-enum class.
        :param field_name: Field name (for error context).
        :param raw_value: Raw value from the request body.

        :returns: The resolved enum member.
    """
    if not isinstance(raw_value, str) or len(raw_value) == 0:
        _abort_problem(
            request=request,
            status=422,
            detail="Field '{}' is required.".format(field_name),
            extensions={"missing_fields": [field_name]},
        )

    for member in enum_cls:
        if member.value == raw_value:
            rtnval = member
            return rtnval

    allowed = [member.value for member in enum_cls]
    _abort_problem(
        request=request,
        status=422,
        detail="Field '{}' must be one of: {}.".format(
            field_name, ", ".join(allowed),
        ),
        extensions={field_name: raw_value, "allowed_values": allowed},
    )
    rtnval = None  # unreachable
    return rtnval


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------


def _iso_or_none(value: Any) -> Optional[str]:
    """
        ISO-8601 serialize a datetime or return ``None``.

        :param value: Datetime or None.

        :returns: ISO-formatted string or None.
    """
    if value is None:
        rtnval = None
        return rtnval
    if isinstance(value, datetime):
        rtnval = value.isoformat()
        return rtnval
    rtnval = str(value)
    return rtnval


def _enum_value(value: Any) -> str:
    """
        Return the ``.value`` of a string-enum or its ``str``.

        :param value: Enum instance or scalar.

        :returns: String value.
    """
    extracted = getattr(value, "value", None)
    if extracted is not None:
        rtnval = str(extracted)
        return rtnval
    rtnval = str(value)
    return rtnval


def _release_record_to_dict(record: Any) -> Dict[str, Any]:
    """
        Serialize a :class:`ReleaseRecord` to the OpenAPI
        ``ReleaseChannelEntry`` schema. The signed manifest +
        signature byte blobs are deliberately omitted -- the REST
        surface advertises metadata, not the raw signed payload.

        :param record: Read-model from the release facade.

        :returns: JSON-friendly dict.
    """
    rtnval: Dict[str, Any] = {
        "channel_id": str(record.release_id),
        "release_id": str(record.release_id),
        "component": _enum_value(record.component),
        "version": record.version,
        "channel": _enum_value(record.channel),
        "artifact_uri": record.artifact_uri,
        "artifact_sha256": record.artifact_sha256,
        "issuer_key_id": record.issuer_key_id,
        "issued_at": _iso_or_none(record.issued_at),
        "issued_by": record.issued_by,
        "status": _enum_value(record.status),
        "rollout_fraction": float(record.rollout_fraction),
        "stage_started_at": _iso_or_none(record.stage_started_at),
        "previous_release_id": record.previous_release_id,
    }
    return rtnval


# ---------------------------------------------------------------------------
# GET /api/v1/release-channels
# ---------------------------------------------------------------------------


def publishing_status() -> Dict[str, Any]:
    """
        Whether this server can publish a release: it needs an
        installed release-signing key.

        :returns: ``{"publishing_available": bool,
                  "publishing_unavailable_reason": str | None}``.
    """
    try:
        manifest_signer.get_active_signing_key()
    except ReleaseSigningKeyUnavailableError:
        rtnval: Dict[str, Any] = {
            "publishing_available": False,
            "publishing_unavailable_reason": PUBLISHING_UNAVAILABLE_REASON,
        }
        return rtnval
    rtnval = {
        "publishing_available": True,
        "publishing_unavailable_reason": None,
    }
    return rtnval


def handle_list_release_channels(request: Request) -> Response:
    """
        ``GET /api/v1/release-channels``

        Query params: ``component``, ``channel``, ``status``,
        ``page``, ``per_page``. ``meta`` also says whether this server
        can publish (see :func:`publishing_status`).

        :param request: Incoming webworks request.

        :returns: JSON response (200) with an ``{items, meta}``
                  page or a problem response.
    """
    try:
        db_session = _require_session(request=request)
        _require_permission(
            request=request,
            db_session=db_session,
            permission_key=RELEASE_CHANNELS_READ_PERMISSION_KEY,
        )

        component = _optional_enum_query(
            request=request,
            enum_cls=ReleaseComponent,
            name="component",
        )
        channel = _optional_enum_query(
            request=request,
            enum_cls=ReleaseChannel,
            name="channel",
        )
        status = _optional_enum_query(
            request=request,
            enum_cls=ReleaseStatus,
            name="status",
        )

        page = _parse_positive_int(
            request=request,
            name="page",
            raw=request.query_params.get("page", None),
            default=1,
            minimum=1,
        )
        per_page = _parse_positive_int(
            request=request,
            name="per_page",
            raw=request.query_params.get("per_page", None),
            default=DEFAULT_PAGE_SIZE,
            minimum=MIN_PAGE_SIZE,
            maximum=MAX_PAGE_SIZE,
        )

        all_records = release_service.list_releases(
            db_session=db_session,
            component=component,
            channel=channel,
            status=status,
        )

        total = len(all_records)
        offset = (page - 1) * per_page
        window = all_records[offset:offset + per_page]

        items: List[Dict[str, Any]] = []
        for record in window:
            items.append(_release_record_to_dict(record=record))

        meta: Dict[str, Any] = {
            "page": page,
            "per_page": per_page,
            "total": int(total),
            "next_cursor": None,
        }
        meta.update(publishing_status())
        body = {
            "items": items,
            "meta": meta,
        }
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


def _optional_enum_query(
        *,
        request: Request,
        enum_cls: Any,
        name: str
    ) -> Optional[Any]:
    """
        Resolve an optional enum-valued query param, aborting 400
        on an unrecognized value.

        :param request: Incoming webworks request.
        :param enum_cls: Target ``str``-enum class.
        :param name: Query-param name.

        :returns: Resolved enum member or None when absent.
    """
    raw = request.query_params.get(name, None)
    if raw is None or len(raw) == 0:
        rtnval = None
        return rtnval

    for member in enum_cls:
        if member.value == raw:
            rtnval = member
            return rtnval

    allowed = [member.value for member in enum_cls]
    _abort_problem(
        request=request,
        status=400,
        detail="Query param '{}' must be one of: {}.".format(
            name, ", ".join(allowed),
        ),
        extensions={"query_param": name, "allowed_values": allowed},
    )
    rtnval = None  # unreachable
    return rtnval


# ---------------------------------------------------------------------------
# POST /api/v1/release-channels
# ---------------------------------------------------------------------------


def handle_create_release_channel(request: Request) -> Response:
    """
        ``POST /api/v1/release-channels``

        Publishes a release onto a channel. Delegates to
        :func:`ops.release.release_service.publish_release`.

        :param request: Incoming webworks request.

        :returns: JSON response (201) carrying the freshly-published
                  release entry, or a problem response.
    """
    try:
        db_session = _require_session(request=request)
        principal = _require_permission(
            request=request,
            db_session=db_session,
            permission_key=RELEASE_CHANNELS_WRITE_PERMISSION_KEY,
        )

        body = _decode_json_object_or_abort(request=request)

        component = _resolve_enum_or_abort(
            request=request,
            enum_cls=ReleaseComponent,
            field_name="component",
            raw_value=body.get("component", None),
        )
        channel = _resolve_enum_or_abort(
            request=request,
            enum_cls=ReleaseChannel,
            field_name="channel",
            raw_value=body.get("channel", None),
        )

        version = body.get("version", None)
        if not isinstance(version, str) or len(version) == 0:
            _abort_problem(
                request=request,
                status=422,
                detail="Field 'version' is required.",
                extensions={"missing_fields": ["version"]},
            )

        artifact_uri = body.get("artifact_uri", None)
        if not isinstance(artifact_uri, str) or len(artifact_uri) == 0:
            _abort_problem(
                request=request,
                status=422,
                detail="Field 'artifact_uri' is required.",
                extensions={"missing_fields": ["artifact_uri"]},
            )

        artifact_sha256 = body.get("artifact_sha256", None)
        if not isinstance(artifact_sha256, str) or len(artifact_sha256) != 64:
            _abort_problem(
                request=request,
                status=422,
                detail=(
                    "Field 'artifact_sha256' is required and must be a "
                    "64-character hex digest."
                ),
                extensions={"missing_fields": ["artifact_sha256"]},
            )

        actor_id: Optional[str] = None
        principal_user_id = getattr(principal, "user_id", None)
        if principal_user_id is not None:
            actor_id = str(principal_user_id)

        aspects = build_default_release_aspects()

        try:
            record = release_service.publish_release(
                db_session=db_session,
                component=component,
                version=version,
                channel=channel,
                artifact_uri=artifact_uri,
                artifact_sha256=artifact_sha256,
                aspects=aspects,
                actor_id=actor_id,
            )
        except ReleaseConflictError as xcpt:
            _abort_problem(
                request=request,
                status=409,
                detail=str(xcpt),
                extensions={
                    "component": component.value,
                    "version": version,
                    "channel": channel.value,
                },
            )
            record = None  # unreachable
        except ReleaseSigningKeyUnavailableError:
            _abort_problem(
                request=request,
                status=503,
                detail=PUBLISHING_UNAVAILABLE_REASON,
                extensions={"reason": SIGNING_KEY_MISSING},
            )
            record = None  # unreachable
        except ValueError as xcpt:
            _abort_problem(
                request=request,
                status=422,
                detail=str(xcpt),
            )
            record = None  # unreachable

        _LOGGER.info(
            "pychestrate.release_channels.publish component=%s channel=%s "
            "version=%s release_id=%s",
            component.value,
            channel.value,
            version,
            str(record.release_id),
        )

        body_dict = _release_record_to_dict(record=record)
        rtnval: Response = JSONResponse(content=body_dict, status_code=201)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# GET /api/v1/release-channels/{channel_id}
# ---------------------------------------------------------------------------


def handle_read_release_channel(request: Request) -> Response:
    """
        ``GET /api/v1/release-channels/{channel_id}``

        The ``channel_id`` path parameter is the release UUID.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with the release entry or a
                  problem response.
    """
    channel_id = request.path_params.get("channel_id", "")
    try:
        db_session = _require_session(request=request)
        _require_permission(
            request=request,
            db_session=db_session,
            permission_key=RELEASE_CHANNELS_READ_PERMISSION_KEY,
        )

        record = release_service.get_release(
            db_session=db_session,
            release_id=channel_id,
        )
        if record is None:
            _abort_problem(
                request=request,
                status=404,
                detail="Release-channel entry not found.",
                extensions={"channel_id": channel_id},
            )

        body = _release_record_to_dict(record=record)
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_release_channels_routes(*, app: Any, version_prefix: str) -> None:
    """
        Attach the release-channel REST routes to a webworks app.

        DOMAIN NOTE -- ``PATCH``, ``DELETE``, and ``:promote`` are
        intentionally NOT registered: the M1 release facade ships
        no mutate / delete / promote capability (see module
        docstring).

        :param app: WebWorks application built by
                    ``establish_webapp_persona``.
        :param version_prefix: Versioned API prefix (e.g.
                               ``"/api/v1"``).

        :returns: None.
    """
    base = version_prefix + RELEASE_CHANNELS_PATH
    app.attach_route(
        base, methods=["GET"],
    )(handle_list_release_channels)
    app.attach_route(
        base, methods=["POST"],
    )(handle_create_release_channel)
    app.attach_route(
        base + "/{channel_id}", methods=["GET"],
    )(handle_read_release_channel)
    return


__all__ = [
    "PUBLISHING_UNAVAILABLE_REASON",
    "SIGNING_KEY_MISSING",
    "publishing_status",
    "RELEASE_CHANNELS_PATH",
    "RELEASE_CHANNELS_READ_PERMISSION_KEY",
    "RELEASE_CHANNELS_WRITE_PERMISSION_KEY",
    "DEFAULT_PAGE_SIZE",
    "MAX_PAGE_SIZE",
    "register_release_channels_routes",
    "handle_list_release_channels",
    "handle_create_release_channel",
    "handle_read_release_channel",
]
