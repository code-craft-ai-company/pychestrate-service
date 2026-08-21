"""
.. module:: webhooks_out.restapi.v1.webhooks_out_routes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks REST routes for the outbound-webhooks tag.

.. moduleauthor:: Code Craft AI LLC

Implements the outbound-webhook operations from
``specs/openapi/pychestrate.yaml``:

* ``GET    /api/v1/webhooks/out/subscriptions`` -- list outbound
  subscriptions for a project.
* ``POST   /api/v1/webhooks/out/subscriptions`` -- register a new
  outbound subscription (a URL + event/topic filter).
* ``GET    /api/v1/webhooks/out/subscriptions/{id}`` -- detail.
* ``PATCH  /api/v1/webhooks/out/subscriptions/{id}`` -- enable /
  disable the subscription (``{"enabled": bool}``).
* ``DELETE /api/v1/webhooks/out/subscriptions/{id}`` -- disable
  the subscription (idempotent).
* ``GET    /api/v1/webhooks/out/subscriptions/{id}/deliveries``
  -- delivery history (success/failure/retries).
* ``POST   /api/v1/webhooks/out/subscriptions/{id}/test`` -- send
  a test event and record the delivery attempt. (The webworks
  matcher cannot place a literal ``:test`` suffix on a param
  segment, so the test action is exposed as a trailing
  ``/test`` sub-resource.)

A "subscription" is the domain's :class:`WebhookTarget`. All
six routes are cookie/RBAC gated and emit RFC 7807 problem
documents via :mod:`api.problem_json_webworks`.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import logging
import secrets as py_secrets

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ccai.webworks.routing.request import Request
from ccai.webworks.routing.response import JSONResponse, Response

from ccai.pychestrate.webservice.api.problem_json_webworks import (
    problem_response_for_http_status,
)
from ccai.pychestrate.webservice.security.rbac import rbac_evaluator
from ccai.pychestrate.webservice.webhooks_out import repository
from ccai.pychestrate.webservice.webhooks_out import service as out_service
from ccai.pychestrate.webservice.webhooks_out.errors import (
    WebhookTargetConflictError,
    WebhookTargetInvalidError,
    WebhookTargetNotFoundError,
)
from ccai.pychestrate.webservice.webhooks_out.models import (
    DeliveryOutcome,
)


WEBHOOKS_OUT_PATH_PREFIX = "/webhooks/out"

WEBHOOKS_READ_PERMISSION_KEY = "system:webhooks.read"
WEBHOOKS_WRITE_PERMISSION_KEY = "system:webhooks.write"

DEFAULT_DELIVERY_LIMIT = 100
MAX_DELIVERY_LIMIT = 500

_LOGGER = logging.getLogger("pychestrate.webhooks_out.routes")


# ---------------------------------------------------------------------------
# Problem-flow plumbing
# ---------------------------------------------------------------------------


class _ProblemAbort(Exception):
    """
        Internal control-flow exception carrying a webworks
        problem response so nested helpers can signal an error
        once and the top-level handler converts it at the
        boundary.
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
        middleware, or ``None`` when the request is anonymous.

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


def _decode_optional_json_object(*, request: Request) -> Dict[str, Any]:
    """
        Decode the request body as a JSON object, treating an
        empty body as an empty object. Aborts 422 only on a
        present-but-malformed body.

        :param request: Incoming webworks request.

        :returns: Decoded dict (possibly empty).
    """
    raw = request.body
    if raw is None or len(raw) == 0:
        rtnval: Dict[str, Any] = {}
        return rtnval
    rtnval = _decode_json_object_or_abort(request=request)
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


def _enum_value_or_str(value: Any) -> str:
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


def _subscription_view_to_dict(view: Any) -> Dict[str, Any]:
    """
        Serialize a :class:`WebhookTargetView` to the OpenAPI
        ``WebhookOutSubscription`` schema.

        :param view: Outbound-target read-model.

        :returns: JSON-friendly dict.
    """
    rtnval: Dict[str, Any] = {
        "subscription_id": str(view.target_id),
        "project_id": str(view.project_id),
        "name": view.name,
        "description": view.description,
        "url": view.url,
        "signature_scheme": _enum_value_or_str(view.signature_scheme),
        "topic_filters": list(view.topic_filters or []),
        "enabled": bool(view.enabled),
        "custom_headers": dict(view.custom_headers or {}),
        "created_by": view.created_by,
        "created_at": _iso_or_none(view.created_at),
        "updated_at": _iso_or_none(view.updated_at),
    }
    return rtnval


def _delivery_view_to_dict(view: Any) -> Dict[str, Any]:
    """
        Serialize a :class:`WebhookDeliveryView` to the OpenAPI
        ``WebhookOutDelivery`` schema.

        :param view: Delivery read-model.

        :returns: JSON-friendly dict.
    """
    rtnval: Dict[str, Any] = {
        "delivery_id": str(view.delivery_id),
        "subscription_id": str(view.target_id),
        "project_id": str(view.project_id),
        "topic": view.topic,
        "payload_digest_sha256": view.payload_digest_sha256,
        "signature": view.signature,
        "outcome": _enum_value_or_str(view.outcome),
        "response_status": view.response_status,
        "response_excerpt": view.response_excerpt,
        "duration_ms": view.duration_ms,
        "attempted_at": _iso_or_none(view.attempted_at),
    }
    return rtnval


def _require_subscription_view(
        *,
        request: Request,
        db_session: Any,
        subscription_id: str
    ) -> Any:
    """
        Resolve the outbound subscription, aborting 404 on miss.

        :param request: Incoming webworks request.
        :param db_session: Active SQLAlchemy session.
        :param subscription_id: Subscription UUID from the path.

        :returns: WebhookTargetView.
    """
    try:
        view = out_service.get_target(
            db_session=db_session,
            target_id=subscription_id,
        )
    except WebhookTargetNotFoundError as xcpt:
        _abort_problem(
            request=request,
            status=404,
            detail=str(xcpt),
            extensions={"subscription_id": subscription_id},
        )
        view = None  # unreachable
    rtnval = view
    return rtnval


# ---------------------------------------------------------------------------
# GET /api/v1/webhooks/out/subscriptions
# ---------------------------------------------------------------------------


def handle_list_subscriptions(request: Request) -> Response:
    """
        ``GET /api/v1/webhooks/out/subscriptions``

        Query params: ``project_id`` (required), ``enabled_only``.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with an ``{items, meta}``
                  page or a problem response.
    """
    try:
        db_session = _require_session(request=request)
        _require_permission(
            request=request,
            db_session=db_session,
            permission_key=WEBHOOKS_READ_PERMISSION_KEY,
        )

        project_id = request.query_params.get("project_id", None)
        if project_id is None or len(project_id) == 0:
            _abort_problem(
                request=request,
                status=422,
                detail="Query param 'project_id' is required.",
                extensions={"query_param": "project_id"},
            )

        enabled_raw = request.query_params.get("enabled_only", "")
        enabled_only = str(enabled_raw).lower() in ("1", "true", "yes")

        views = out_service.list_targets_for_project(
            db_session=db_session,
            project_id=project_id,
            enabled_only=enabled_only,
        )

        items: List[Dict[str, Any]] = []
        for view in views:
            items.append(_subscription_view_to_dict(view=view))

        body = {
            "items": items,
            "meta": {
                "page": 1,
                "per_page": len(items),
                "total": len(items),
                "next_cursor": None,
            },
        }
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# POST /api/v1/webhooks/out/subscriptions
# ---------------------------------------------------------------------------


def handle_create_subscription(request: Request) -> Response:
    """
        ``POST /api/v1/webhooks/out/subscriptions``

        Registers a new outbound subscription (a URL + event
        topic filter).

        When the caller does not supply a ``secret_ref``, the
        route generates an HMAC signing secret for the
        subscription and returns it ONCE as ``signing_secret``
        on the 201 response. It is never readable again through
        the API -- receivers use it to verify the
        ``X-Pychestrate-Signature`` header on deliveries.

        :param request: Incoming webworks request.

        :returns: JSON response (201) carrying the created
                  subscription, or a problem response.
    """
    try:
        db_session = _require_session(request=request)
        principal = _require_permission(
            request=request,
            db_session=db_session,
            permission_key=WEBHOOKS_WRITE_PERMISSION_KEY,
        )

        body = _decode_json_object_or_abort(request=request)

        project_id = body.get("project_id", None)
        name = body.get("name", None)
        url = body.get("url", None)

        missing: List[str] = []
        if not isinstance(project_id, str) or len(project_id) == 0:
            missing.append("project_id")
        if not isinstance(name, str) or len(name) == 0:
            missing.append("name")
        if not isinstance(url, str) or len(url) == 0:
            missing.append("url")
        if len(missing) > 0:
            _abort_problem(
                request=request,
                status=422,
                detail="Required fields are missing or empty.",
                extensions={"missing_fields": missing},
            )

        description = body.get("description", "")
        if isinstance(description, str) is False:
            _abort_problem(
                request=request,
                status=422,
                detail="Field 'description' must be a string.",
            )

        secret_ref = body.get("secret_ref", "")
        if isinstance(secret_ref, str) is False:
            _abort_problem(
                request=request,
                status=422,
                detail="Field 'secret_ref' must be a string.",
            )

        # M1 stores the literal shared secret in ``secret_ref``
        # (the M2 follow-on resolves it through 1-secrets-vault).
        # When the caller supplies none, generate one so every
        # subscription's deliveries are verifiable, and surface
        # it exactly once on the create response.
        generated_signing_secret: Optional[str] = None
        if len(secret_ref) == 0:
            generated_signing_secret = py_secrets.token_hex(32)
            secret_ref = generated_signing_secret

        topic_filters_raw = body.get("topic_filters", [])
        if isinstance(topic_filters_raw, list) is False:
            _abort_problem(
                request=request,
                status=422,
                detail="Field 'topic_filters' must be an array.",
            )
        topic_filters: List[str] = []
        for index, entry in enumerate(topic_filters_raw):
            if isinstance(entry, str) is False:
                _abort_problem(
                    request=request,
                    status=422,
                    detail="Field 'topic_filters[{}]' must be a "
                           "string.".format(index),
                )
            topic_filters.append(entry)

        custom_headers_raw = body.get("custom_headers", {})
        if isinstance(custom_headers_raw, dict) is False:
            _abort_problem(
                request=request,
                status=422,
                detail="Field 'custom_headers' must be an object.",
            )
        custom_headers: Dict[str, str] = {}
        for key, value in custom_headers_raw.items():
            custom_headers[str(key)] = str(value)

        actor_id: Optional[str] = None
        principal_user_id = getattr(principal, "user_id", None)
        if principal_user_id is not None:
            actor_id = str(principal_user_id)

        try:
            view = out_service.register_target(
                db_session=db_session,
                project_id=project_id,
                name=name,
                url=url,
                secret_ref=secret_ref,
                description=description,
                topic_filters=topic_filters,
                custom_headers=custom_headers,
                actor_id=actor_id,
            )
        except WebhookTargetInvalidError as xcpt:
            _abort_problem(
                request=request,
                status=422,
                detail=str(xcpt),
            )
            view = None  # unreachable
        except WebhookTargetConflictError as xcpt:
            _abort_problem(
                request=request,
                status=409,
                detail=str(xcpt),
                extensions={"project_id": project_id, "name": name},
            )
            view = None  # unreachable

        _LOGGER.info(
            "pychestrate.webhooks_out.subscription_created project_id=%s"
            " name=%s subscription_id=%s",
            project_id,
            name,
            str(view.target_id),
        )

        body_dict = _subscription_view_to_dict(view=view)
        if generated_signing_secret is not None:
            body_dict["signing_secret"] = generated_signing_secret
        rtnval: Response = JSONResponse(content=body_dict, status_code=201)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# GET /api/v1/webhooks/out/subscriptions/{subscription_id}
# ---------------------------------------------------------------------------


def handle_read_subscription(request: Request) -> Response:
    """
        ``GET /api/v1/webhooks/out/subscriptions/{subscription_id}``

        :param request: Incoming webworks request.

        :returns: JSON response (200) with the subscription dict
                  or a problem response.
    """
    subscription_id = request.path_params.get("subscription_id", "")
    try:
        db_session = _require_session(request=request)
        _require_permission(
            request=request,
            db_session=db_session,
            permission_key=WEBHOOKS_READ_PERMISSION_KEY,
        )

        view = _require_subscription_view(
            request=request,
            db_session=db_session,
            subscription_id=subscription_id,
        )

        body = _subscription_view_to_dict(view=view)
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# PATCH /api/v1/webhooks/out/subscriptions/{subscription_id}
# ---------------------------------------------------------------------------


def handle_update_subscription(request: Request) -> Response:
    """
        ``PATCH /api/v1/webhooks/out/subscriptions/{subscription_id}``

        Enables or disables the subscription. The only mutable
        field is ``enabled`` -- name / URL / topic filters are
        immutable in M1 (recreate the subscription to change
        them).

        :param request: Incoming webworks request.

        :returns: JSON response (200) with the updated
                  subscription or a problem response.
    """
    subscription_id = request.path_params.get("subscription_id", "")
    try:
        db_session = _require_session(request=request)
        principal = _require_permission(
            request=request,
            db_session=db_session,
            permission_key=WEBHOOKS_WRITE_PERMISSION_KEY,
        )

        body = _decode_json_object_or_abort(request=request)
        enabled = body.get("enabled", None)
        if isinstance(enabled, bool) is False:
            _abort_problem(
                request=request,
                status=422,
                detail="Field 'enabled' is required and must be a boolean.",
                extensions={"missing_fields": ["enabled"]},
            )

        actor_id: Optional[str] = None
        principal_user_id = getattr(principal, "user_id", None)
        if principal_user_id is not None:
            actor_id = str(principal_user_id)

        try:
            if enabled is True:
                view = out_service.enable_target(
                    db_session=db_session,
                    target_id=subscription_id,
                    actor_id=actor_id,
                )
            else:
                view = out_service.disable_target(
                    db_session=db_session,
                    target_id=subscription_id,
                    actor_id=actor_id,
                )
        except WebhookTargetNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                extensions={"subscription_id": subscription_id},
            )
            view = None  # unreachable

        _LOGGER.info(
            "pychestrate.webhooks_out.subscription_updated"
            " subscription_id=%s enabled=%s",
            subscription_id,
            enabled,
        )

        body_dict = _subscription_view_to_dict(view=view)
        rtnval: Response = JSONResponse(content=body_dict, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# DELETE /api/v1/webhooks/out/subscriptions/{subscription_id}
# ---------------------------------------------------------------------------


def handle_delete_subscription(request: Request) -> Response:
    """
        ``DELETE /api/v1/webhooks/out/subscriptions/{subscription_id}``

        Disables the subscription (idempotent). The domain
        retains the row for the delivery-history audit trail.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with the disabled
                  subscription or a problem response.
    """
    subscription_id = request.path_params.get("subscription_id", "")
    try:
        db_session = _require_session(request=request)
        principal = _require_permission(
            request=request,
            db_session=db_session,
            permission_key=WEBHOOKS_WRITE_PERMISSION_KEY,
        )

        actor_id: Optional[str] = None
        principal_user_id = getattr(principal, "user_id", None)
        if principal_user_id is not None:
            actor_id = str(principal_user_id)

        try:
            view = out_service.disable_target(
                db_session=db_session,
                target_id=subscription_id,
                actor_id=actor_id,
            )
        except WebhookTargetNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                extensions={"subscription_id": subscription_id},
            )
            view = None  # unreachable

        _LOGGER.info(
            "pychestrate.webhooks_out.subscription_disabled"
            " subscription_id=%s",
            subscription_id,
        )

        body = _subscription_view_to_dict(view=view)
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# GET /api/v1/webhooks/out/subscriptions/{subscription_id}/deliveries
# ---------------------------------------------------------------------------


def handle_list_subscription_deliveries(request: Request) -> Response:
    """
        ``GET /api/v1/webhooks/out/subscriptions/{subscription_id}/deliveries``

        Delivery history (success/failure/retries) for one
        subscription, newest-first. Query param: ``limit``.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with an ``{items, meta}``
                  page or a problem response.
    """
    subscription_id = request.path_params.get("subscription_id", "")
    try:
        db_session = _require_session(request=request)
        _require_permission(
            request=request,
            db_session=db_session,
            permission_key=WEBHOOKS_READ_PERMISSION_KEY,
        )

        _require_subscription_view(
            request=request,
            db_session=db_session,
            subscription_id=subscription_id,
        )

        limit = _parse_positive_int(
            request=request,
            name="limit",
            raw=request.query_params.get("limit", None),
            default=DEFAULT_DELIVERY_LIMIT,
            minimum=1,
            maximum=MAX_DELIVERY_LIMIT,
        )

        views = out_service.list_recent_deliveries_for_target(
            db_session=db_session,
            target_id=subscription_id,
            limit=limit,
        )

        items: List[Dict[str, Any]] = []
        for view in views:
            items.append(_delivery_view_to_dict(view=view))

        body = {
            "items": items,
            "meta": {
                "page": 1,
                "per_page": len(items),
                "total": len(items),
                "next_cursor": None,
            },
        }
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# POST /api/v1/webhooks/out/subscriptions/{subscription_id}:test
# ---------------------------------------------------------------------------


def handle_test_subscription(request: Request) -> Response:
    """
        ``POST /api/v1/webhooks/out/subscriptions/{subscription_id}/test``

        Builds a signed test event for the subscription and
        records the delivery attempt. The actual HTTP write
        lands in the M2 dispatcher -- this route records the
        attempt as :data:`DeliveryOutcome.PENDING` so the
        operator sees the test in the delivery history.

        Optional JSON body: ``{"topic": "...", "payload": {...}}``.

        :param request: Incoming webworks request.

        :returns: JSON response (202) with the recorded
                  delivery, or a problem response.
    """
    subscription_id = request.path_params.get("subscription_id", "")
    try:
        db_session = _require_session(request=request)
        _require_permission(
            request=request,
            db_session=db_session,
            permission_key=WEBHOOKS_WRITE_PERMISSION_KEY,
        )

        target_row = repository.find_target_by_id(
            db_session=db_session,
            target_id=subscription_id,
        )
        if target_row is None:
            _abort_problem(
                request=request,
                status=404,
                detail="Webhook subscription not found.",
                extensions={"subscription_id": subscription_id},
            )

        if target_row.enabled is False:
            _abort_problem(
                request=request,
                status=409,
                detail="Cannot send a test event for a disabled "
                       "subscription.",
                extensions={"subscription_id": subscription_id},
            )

        body = _decode_optional_json_object(request=request)
        topic = body.get("topic", "entity.webhook.test")
        if isinstance(topic, str) is False or len(topic) == 0:
            topic = "entity.webhook.test"
        payload = body.get("payload", {})
        if isinstance(payload, dict) is False:
            _abort_problem(
                request=request,
                status=422,
                detail="Field 'payload' must be an object.",
            )

        event_payload = {
            "topic": topic,
            "event": "test",
            "subscription_id": subscription_id,
            "payload": dict(payload),
        }
        raw_body = json.dumps(event_payload, sort_keys=True).encode("utf-8")

        # M1 stores the literal shared secret in ``secret_ref``;
        # the M2 follow-on resolves it through 1-secrets-vault.
        secret = (target_row.secret_ref or "").encode("utf-8")

        signed = out_service.build_signed_request(
            db_session=db_session,
            target_id=subscription_id,
            topic=topic,
            body=raw_body,
            secret=secret,
        )

        delivery_view = out_service.record_delivery_attempt(
            db_session=db_session,
            target_id=subscription_id,
            delivery_id=signed.delivery_id,
            topic=topic,
            payload_digest_sha256=signed.payload_digest_sha256,
            signature=signed.signature,
            request_headers=dict(signed.headers),
            outcome=DeliveryOutcome.PENDING,
        )

        _LOGGER.info(
            "pychestrate.webhooks_out.test_event subscription_id=%s"
            " delivery_id=%s topic=%s",
            subscription_id,
            signed.delivery_id,
            topic,
        )

        body_dict = {
            "status": "queued",
            "delivery": _delivery_view_to_dict(view=delivery_view),
        }
        rtnval: Response = JSONResponse(content=body_dict, status_code=202)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_webhooks_out_routes(*, app: Any, version_prefix: str) -> None:
    """
        Attach the outbound-webhooks REST routes to a webworks
        app.

        :param app: WebWorks application built by
                    ``establish_webapp_persona``.
        :param version_prefix: Versioned API prefix (e.g.
                               ``"/api/v1"``).

        :returns: None.
    """
    base = version_prefix + WEBHOOKS_OUT_PATH_PREFIX + "/subscriptions"

    app.attach_route(base, methods=["GET"])(handle_list_subscriptions)
    app.attach_route(base, methods=["POST"])(handle_create_subscription)
    app.attach_route(
        base + "/{subscription_id}", methods=["GET"],
    )(handle_read_subscription)
    app.attach_route(
        base + "/{subscription_id}", methods=["PATCH"],
    )(handle_update_subscription)
    app.attach_route(
        base + "/{subscription_id}", methods=["DELETE"],
    )(handle_delete_subscription)
    app.attach_route(
        base + "/{subscription_id}/deliveries", methods=["GET"],
    )(handle_list_subscription_deliveries)
    app.attach_route(
        base + "/{subscription_id}/test", methods=["POST"],
    )(handle_test_subscription)

    _LOGGER.info(
        "pychestrate.webhooks_out.routes.wired: outbound subscription"
        " CRUD + delivery history + test-event surface."
    )
    return


__all__ = [
    "WEBHOOKS_OUT_PATH_PREFIX",
    "WEBHOOKS_READ_PERMISSION_KEY",
    "WEBHOOKS_WRITE_PERMISSION_KEY",
    "register_webhooks_out_routes",
    "handle_list_subscriptions",
    "handle_create_subscription",
    "handle_read_subscription",
    "handle_update_subscription",
    "handle_delete_subscription",
    "handle_list_subscription_deliveries",
    "handle_test_subscription",
]
