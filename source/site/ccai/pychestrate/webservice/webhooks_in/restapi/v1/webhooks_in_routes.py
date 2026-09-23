"""
.. module:: webhooks_in.restapi.v1.webhooks_in_routes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks REST routes for the inbound-webhooks tag.

.. moduleauthor:: Code Craft AI LLC

Implements the inbound-webhook operations from
``specs/openapi/pychestrate.yaml``:

* ``POST /api/v1/webhooks/in/{provider}/{hook_name}`` -- the
  unauthenticated inbound receiver. External systems POST
  provider-native events here; the handler runs the domain's
  verification (signature check) + replay-cache de-dup +
  normalization + dispatch through
  :func:`webhooks_in.dispatcher.dispatch_inbound_webhook`.
* ``GET  /api/v1/webhooks/in/integrations`` -- list inbound
  integration configurations (operator-facing).
* ``POST /api/v1/webhooks/in/integrations`` -- register a new
  inbound integration configuration.
* ``PATCH /api/v1/webhooks/in/integrations/{webhook_id}`` --
  enable / disable an integration (``{"enabled": bool}``).
* ``GET  /api/v1/webhooks/in/deliveries`` -- recent inbound
  deliveries (replay-cache ledger) for audit/debug.

The inbound receiver is NOT cookie/RBAC gated. Inbound
webhooks authenticate via the domain's per-integration
signature verification (HMAC/secret); the replay-cache
prevents duplicate deliveries. The receiver answers in
webhook-conventional terms: ``200``/``202`` on accept,
``401`` on a bad signature, ``409`` on a replayed delivery,
``404`` for an unknown provider/integration.

The operator-facing integration + delivery routes ARE
cookie/RBAC gated and emit RFC 7807 problem documents via
:mod:`api.problem_json_webworks`.

Shared secrets (audit ORC-29): an integration's HMAC key lives
only in ``1-secrets-vault``. The create route accepts it as the
write-only ``secret`` field (stored in the vault on the caller's
behalf) or binds an existing vault secret through ``secret_ref``;
the configuration row keeps only the vault reference, the
receiver resolves it through the vault on every delivery, and no
response ever carries the key.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import logging
import uuid

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ccai.webworks.routing.request import Request
from ccai.webworks.routing.response import JSONResponse, Response

from ccai.pychestrate.webservice.api.problem_json_webworks import (
    problem_response_for_http_status,
)
from ccai.pychestrate.webservice.projects import repository as projects_repo
from ccai.pychestrate.webservice.secrets.secret_bytes import SecretBytes
from ccai.pychestrate.webservice.security.rbac import rbac_evaluator
from ccai.pychestrate.webservice.webhooks_in import configuration_service
from ccai.pychestrate.webservice.webhooks_in import repository
from ccai.pychestrate.webservice.webhooks_in.dispatcher import (
    dispatch_inbound_webhook,
)
from ccai.pychestrate.webservice.webhooks_in.errors import (
    WebhookConfigurationConflictError,
    WebhookConfigurationInvalidError,
    WebhookConfigurationNotFoundError,
    WebhookProviderUnknownError,
    WebhookSecretAccessDeniedError,
    WebhookSecretInvalidError,
)


WEBHOOKS_IN_PATH_PREFIX = "/webhooks/in"

WEBHOOKS_READ_PERMISSION_KEY = "system:webhooks.read"
WEBHOOKS_WRITE_PERMISSION_KEY = "system:webhooks.write"

DEFAULT_DELIVERY_LIMIT = 100
MAX_DELIVERY_LIMIT = 500

_LOGGER = logging.getLogger("pychestrate.webhooks_in.routes")


# ---------------------------------------------------------------------------
# Problem-flow plumbing (operator-facing routes)
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


def _is_uuid(value: Any) -> bool:
    """
        Whether ``value`` parses as a UUID.

        :param value: Raw value.

        :returns: True for a well-formed UUID.
    """
    try:
        uuid.UUID(str(value))
    except ValueError:
        return False
    return True


def _require_uuid(*, request: Request, name: str, value: str) -> str:
    """
        Abort 422 unless ``value`` is a well-formed UUID. The id
        columns are UUID-typed, so a malformed id would otherwise
        fail inside the database driver as a 500.

        :param request: Incoming webworks request.
        :param name: Field / parameter name (for error context).
        :param value: Raw value.

        :returns: The value, unchanged.
    """
    if _is_uuid(value) is False:
        _abort_problem(
            request=request,
            status=422,
            detail="'{}' must be a UUID.".format(name),
            extensions={"invalid_fields": [name]},
        )
    rtnval = value
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


def _integration_view_to_dict(
        view: Any,
        *,
        secret_configured: bool
    ) -> Dict[str, Any]:
    """
        Serialize a :class:`WebhookConfigurationView` to the
        OpenAPI ``WebhookInIntegration`` schema.

        The shared secret is never serialized. ``secret_ref`` is
        the vault reference the secret is stored under and is
        echoed only when it names an existing vault secret
        (``secret_configured``); anything else -- a deleted vault
        secret, or a row written before secrets moved to the vault
        -- serializes as ``null`` so a stored value that is not a
        reference can never leak.

        :param view: Configuration read-model.
        :param secret_configured: Whether ``view.secret_ref`` names
                                  an existing vault secret.

        :returns: JSON-friendly dict.
    """
    exposed_ref: Optional[str] = None
    if secret_configured is True:
        exposed_ref = view.secret_ref
    rtnval: Dict[str, Any] = {
        "webhook_id": str(view.webhook_id),
        "project_id": str(view.project_id),
        "provider": view.provider,
        "hook_name": view.hook_name,
        "secret_ref": exposed_ref,
        "secret_configured": bool(secret_configured),
        "mtls_required": bool(view.mtls_required),
        "description": view.description,
        "enabled": bool(view.enabled),
        "created_by": view.created_by,
        "created_at": _iso_or_none(view.created_at),
        "disabled_at": _iso_or_none(view.disabled_at),
        "receiver_path": "/api/v1/webhooks/in/{}/{}".format(
            view.provider, view.hook_name,
        ),
    }
    return rtnval


def _seen_delivery_to_dict(row: Any) -> Dict[str, Any]:
    """
        Serialize a :class:`WebhookSeenDelivery` row to the
        OpenAPI ``WebhookInDelivery`` schema.

        :param row: Replay-cache ledger row.

        :returns: JSON-friendly dict.
    """
    rtnval: Dict[str, Any] = {
        "provider": row.provider,
        "hook_name": row.hook_name,
        "delivery_id": row.delivery_id,
        "first_seen_at": _iso_or_none(row.first_seen_at),
        "expires_at": _iso_or_none(row.expires_at),
    }
    return rtnval


# ---------------------------------------------------------------------------
# POST /api/v1/webhooks/in/{provider}/{hook_name} -- inbound receiver
# ---------------------------------------------------------------------------


def handle_receive_webhook(request: Request) -> Response:
    """
        ``POST /api/v1/webhooks/in/{provider}/{hook_name}``

        The unauthenticated inbound receiver. Resolves the
        enabled inbound configurations for the
        ``(provider, hook_name)`` pair, then runs the domain
        verification + replay-cache + normalization + dispatch
        pipeline. Authentication is the domain's signature
        verification -- no cookie/RBAC gate applies.

        Answers in webhook-conventional terms: ``202`` on
        accept (events dispatched or replay short-circuited),
        ``401`` on a bad/missing signature, ``409`` on a
        replayed delivery, ``404`` for an unknown
        provider/integration.

        :param request: Incoming webworks request.

        :returns: JSON response carrying a small accept/reject
                  envelope.
    """
    provider = request.path_params.get("provider", "")
    hook_name = request.path_params.get("hook_name", "")

    db_session = _resolve_db_session(request=request)
    if db_session is None:
        rtnval: Response = JSONResponse(
            content={"status": "error", "detail": "db_session unavailable"},
            status_code=503,
        )
        return rtnval

    raw_bytes = request.body
    headers: Dict[str, str] = {}
    for key, value in request.headers.items():
        headers[str(key)] = str(value)

    remote_ip = request.get_header("X-Forwarded-For", "") or ""
    request_id = request.get_header("X-Request-Id", "") or ""

    # The inbound receiver is unauthenticated -- it must not
    # leak whether an integration exists. Resolve the active
    # configurations for the (provider, hook_name) pair; the
    # dispatcher disambiguates by signature compare.
    configs = repository.list_active_configurations_for_provider(
        db_session=db_session,
        provider=provider,
        hook_name=hook_name,
    )
    if configs is None or len(configs) == 0:
        rtnval = JSONResponse(
            content={
                "status": "rejected",
                "reason": "configuration_not_found",
                "provider": provider,
                "hook_name": hook_name,
            },
            status_code=404,
        )
        return rtnval

    # Try each configured integration's secret. The first one
    # whose signature verifies (or whose dispatch produces a
    # non-401 outcome) wins -- this matches the dispatcher's
    # "M1 returns every enabled row" contract. ``secret_ref`` is
    # a vault reference: the key is resolved through the secrets
    # vault here and never read from the configuration row.
    last_result: Optional[Any] = None
    for config in configs:
        shared_secret = configuration_service.resolve_shared_secret(
            db_session=db_session,
            secret_ref=config.secret_ref,
        )
        if shared_secret is None:
            _LOGGER.warning(
                "pychestrate.webhooks_in.receive.secret_unresolved"
                " webhook_id=%s provider=%s hook_name=%s",
                str(getattr(config, "webhook_id", "")),
                provider,
                hook_name,
            )
            continue
        result = dispatch_inbound_webhook(
            db_session=db_session,
            provider=provider,
            hook_name=hook_name,
            raw_bytes=raw_bytes,
            headers=headers,
            shared_secret=shared_secret,
            remote_ip=remote_ip,
            request_id=request_id if len(request_id) > 0 else None,
        )
        last_result = result
        if result.status != "rejected":
            break
        if result.rejection is not None:
            if result.rejection.status_code != 401:
                break

    if last_result is None:
        # Every matching integration's secret reference failed to
        # resolve (the vault secret was deleted or expired): the
        # delivery cannot be verified, so nothing is dispatched.
        rtnval = JSONResponse(
            content={
                "status": "rejected",
                "reason": "secret_unavailable",
                "provider": provider,
                "hook_name": hook_name,
            },
            status_code=503,
        )
        return rtnval

    result = last_result

    if result.status == "dispatched":
        rtnval = JSONResponse(
            content={
                "status": "accepted",
                "request_id": result.request_id,
                "provider": result.provider,
                "hook_name": result.hook_name,
                "delivery_id": result.delivery_id,
                "domain_event_count": result.domain_event_count,
            },
            status_code=202,
        )
        return rtnval

    if result.status == "replay_ignored":
        rtnval = JSONResponse(
            content={
                "status": "replay_ignored",
                "request_id": result.request_id,
                "provider": result.provider,
                "hook_name": result.hook_name,
                "delivery_id": result.delivery_id,
            },
            status_code=409,
        )
        return rtnval

    rejection = result.rejection
    status_code = 400
    reason = "rejected"
    if rejection is not None:
        status_code = int(rejection.status_code)
        reason = rejection.reason

    _LOGGER.info(
        "pychestrate.webhooks_in.receive provider=%s hook_name=%s"
        " status=rejected reason=%s",
        provider,
        hook_name,
        reason,
    )

    rtnval = JSONResponse(
        content={
            "status": "rejected",
            "reason": reason,
            "request_id": result.request_id,
            "provider": result.provider,
            "hook_name": result.hook_name,
        },
        status_code=status_code,
    )
    return rtnval


# ---------------------------------------------------------------------------
# GET /api/v1/webhooks/in/integrations
# ---------------------------------------------------------------------------


def handle_list_integrations(request: Request) -> Response:
    """
        ``GET /api/v1/webhooks/in/integrations``

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
        _require_uuid(request=request, name="project_id", value=project_id)

        enabled_raw = request.query_params.get("enabled_only", "")
        enabled_only = str(enabled_raw).lower() in ("1", "true", "yes")

        views = configuration_service.list_webhooks(
            db_session=db_session,
            project_id=project_id,
            enabled_only=enabled_only,
        )

        items: List[Dict[str, Any]] = []
        for view in views:
            secret_configured = configuration_service.is_secret_ref_stored(
                db_session=db_session,
                secret_ref=view.secret_ref,
            )
            items.append(
                _integration_view_to_dict(
                    view=view,
                    secret_configured=secret_configured,
                )
            )

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
# POST /api/v1/webhooks/in/integrations
# ---------------------------------------------------------------------------


def handle_create_integration(request: Request) -> Response:
    """
        ``POST /api/v1/webhooks/in/integrations``

        Registers a new inbound integration configuration
        (an external source + its verification secret).

        The shared secret arrives in exactly one of two forms:

        * ``secret`` -- the HMAC key itself (write-only). It is
          stored in the secrets vault as a project secret on the
          caller's behalf; the caller therefore needs the vault's
          write permission for the project.
        * ``secret_ref`` -- the name of an existing vault secret
          the caller may read.

        The response carries the vault reference, never the key.

        :param request: Incoming webworks request.

        :returns: JSON response (201) carrying the created
                  integration, or a problem response.
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
        provider = body.get("provider", None)
        hook_name = body.get("hook_name", None)
        secret = body.get("secret", None)
        secret_ref = body.get("secret_ref", None)

        invalid: List[str] = []
        if secret is not None and isinstance(secret, str) is False:
            invalid.append("secret")
        if secret_ref is not None and isinstance(secret_ref, str) is False:
            invalid.append("secret_ref")
        if len(invalid) > 0:
            _abort_problem(
                request=request,
                status=422,
                detail="Fields must be strings: {}.".format(", ".join(invalid)),
                extensions={"invalid_fields": invalid},
            )
        has_secret = isinstance(secret, str) and len(secret) > 0
        has_secret_ref = isinstance(secret_ref, str) and len(secret_ref) > 0

        missing: List[str] = []
        if not isinstance(project_id, str) or len(project_id) == 0:
            missing.append("project_id")
        if not isinstance(provider, str) or len(provider) == 0:
            missing.append("provider")
        if not isinstance(hook_name, str) or len(hook_name) == 0:
            missing.append("hook_name")
        if has_secret is False and has_secret_ref is False:
            missing.append("secret")
        if len(missing) > 0:
            _abort_problem(
                request=request,
                status=422,
                detail=(
                    "Required fields are missing or empty. The shared"
                    " secret goes in 'secret' (stored in the secrets"
                    " vault) or names an existing vault secret in"
                    " 'secret_ref'."
                ),
                extensions={"missing_fields": missing},
            )
        if has_secret is True and has_secret_ref is True:
            _abort_problem(
                request=request,
                status=422,
                detail="Supply either 'secret' or 'secret_ref', not both.",
                extensions={"invalid_fields": ["secret", "secret_ref"]},
            )

        _require_uuid(request=request, name="project_id", value=project_id)
        project_row = projects_repo.get_project_by_id(
            db_session=db_session,
            project_id=project_id,
        )
        if project_row is None:
            _abort_problem(
                request=request,
                status=404,
                detail="Project not found.",
                extensions={"project_id": project_id},
            )

        mtls_required = body.get("mtls_required", False)
        if isinstance(mtls_required, bool) is False:
            _abort_problem(
                request=request,
                status=422,
                detail="Field 'mtls_required' must be a boolean.",
            )

        description = body.get("description", "")
        if isinstance(description, str) is False:
            _abort_problem(
                request=request,
                status=422,
                detail="Field 'description' must be a string.",
            )

        actor_id: Optional[str] = None
        principal_user_id = getattr(principal, "user_id", None)
        if principal_user_id is not None:
            actor_id = str(principal_user_id)

        shared_secret: Optional[SecretBytes] = None
        if has_secret is True:
            shared_secret = SecretBytes(secret.encode("utf-8"))

        try:
            view = configuration_service.create_webhook_with_secret(
                db_session=db_session,
                principal=principal,
                project_id=project_id,
                provider=provider,
                hook_name=hook_name,
                shared_secret=shared_secret,
                secret_ref=secret_ref if has_secret_ref is True else None,
                mtls_required=mtls_required,
                description=description,
                actor_id=actor_id,
            )
        except WebhookConfigurationInvalidError as xcpt:
            _abort_problem(
                request=request,
                status=422,
                detail=str(xcpt),
            )
            view = None  # unreachable
        except WebhookSecretInvalidError as xcpt:
            _abort_problem(
                request=request,
                status=422,
                detail=str(xcpt),
                extensions={"invalid_fields": ["secret_ref"]},
            )
            view = None  # unreachable
        except WebhookSecretAccessDeniedError as xcpt:
            _abort_problem(
                request=request,
                status=403,
                detail=str(xcpt),
            )
            view = None  # unreachable
        except WebhookProviderUnknownError as xcpt:
            _abort_problem(
                request=request,
                status=422,
                detail=str(xcpt),
                extensions={
                    "provider": provider,
                    "registered_providers": (
                        configuration_service.list_registered_providers()
                    ),
                },
            )
            view = None  # unreachable
        except WebhookConfigurationConflictError as xcpt:
            _abort_problem(
                request=request,
                status=409,
                detail=str(xcpt),
                extensions={
                    "project_id": project_id,
                    "provider": provider,
                    "hook_name": hook_name,
                },
            )
            view = None  # unreachable
        finally:
            # The key has been encrypted into the vault (or the
            # create failed); zeroize the request's copy either way.
            if shared_secret is not None:
                shared_secret.close()

        _LOGGER.info(
            "pychestrate.webhooks_in.integration_created project_id=%s"
            " provider=%s hook_name=%s webhook_id=%s",
            project_id,
            provider,
            hook_name,
            str(view.webhook_id),
        )

        body_dict = _integration_view_to_dict(
            view=view,
            secret_configured=configuration_service.is_secret_ref_stored(
                db_session=db_session,
                secret_ref=view.secret_ref,
            ),
        )
        rtnval: Response = JSONResponse(content=body_dict, status_code=201)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# PATCH /api/v1/webhooks/in/integrations/{webhook_id}
# ---------------------------------------------------------------------------


def handle_update_integration(request: Request) -> Response:
    """
        ``PATCH /api/v1/webhooks/in/integrations/{webhook_id}``

        Enables or disables the integration. The only mutable
        field is ``enabled`` -- provider / hook / secret are
        immutable in M1 (the rotate-secret path lands in M2).

        :param request: Incoming webworks request.

        :returns: JSON response (200) with the updated
                  integration or a problem response.
    """
    webhook_id = request.path_params.get("webhook_id", "")
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

        if _is_uuid(webhook_id) is False:
            # A malformed id can name no integration; answer the
            # same 404 an unknown id gets rather than letting the
            # UUID-typed lookup fail as a 500.
            _abort_problem(
                request=request,
                status=404,
                detail="Webhook configuration not found.",
                extensions={"webhook_id": webhook_id},
            )

        try:
            if enabled is True:
                view = configuration_service.enable_webhook(
                    db_session=db_session,
                    webhook_id=webhook_id,
                    actor_id=actor_id,
                )
            else:
                view = configuration_service.disable_webhook(
                    db_session=db_session,
                    webhook_id=webhook_id,
                    actor_id=actor_id,
                )
        except WebhookConfigurationNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                extensions={"webhook_id": webhook_id},
            )
            view = None  # unreachable

        _LOGGER.info(
            "pychestrate.webhooks_in.integration_updated webhook_id=%s"
            " enabled=%s",
            webhook_id,
            enabled,
        )

        body_dict = _integration_view_to_dict(
            view=view,
            secret_configured=configuration_service.is_secret_ref_stored(
                db_session=db_session,
                secret_ref=view.secret_ref,
            ),
        )
        rtnval: Response = JSONResponse(content=body_dict, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# GET /api/v1/webhooks/in/deliveries
# ---------------------------------------------------------------------------


def handle_list_deliveries(request: Request) -> Response:
    """
        ``GET /api/v1/webhooks/in/deliveries``

        Recent inbound deliveries (the replay-cache ledger)
        for audit/debug. Query params: ``provider``,
        ``hook_name``, ``limit``.

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

        limit = _parse_positive_int(
            request=request,
            name="limit",
            raw=request.query_params.get("limit", None),
            default=DEFAULT_DELIVERY_LIMIT,
            minimum=1,
            maximum=MAX_DELIVERY_LIMIT,
        )
        provider_filter = request.query_params.get("provider", None)
        hook_name_filter = request.query_params.get("hook_name", None)

        from ccai.pychestrate.webservice.webhooks_in.models import (
            WebhookSeenDelivery,
        )

        query = db_session.query(WebhookSeenDelivery)
        if provider_filter is not None and len(provider_filter) > 0:
            query = query.filter(
                WebhookSeenDelivery.provider == provider_filter,
            )
        if hook_name_filter is not None and len(hook_name_filter) > 0:
            query = query.filter(
                WebhookSeenDelivery.hook_name == hook_name_filter,
            )
        rows = (
            query.order_by(WebhookSeenDelivery.first_seen_at.desc())
            .limit(limit)
            .all()
        )

        items: List[Dict[str, Any]] = []
        for row in rows:
            items.append(_seen_delivery_to_dict(row=row))

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
# Registration
# ---------------------------------------------------------------------------


def register_webhooks_in_routes(*, app: Any, version_prefix: str) -> None:
    """
        Attach the inbound-webhooks REST routes to a webworks app.

        :param app: WebWorks application built by
                    ``establish_webapp_persona``.
        :param version_prefix: Versioned API prefix (e.g.
                               ``"/api/v1"``).

        :returns: None.
    """
    base = version_prefix + WEBHOOKS_IN_PATH_PREFIX

    # Operator-facing routes register BEFORE the catch-all
    # receiver pattern so the literal ``/integrations`` and
    # ``/deliveries`` segments win the dispatcher match over
    # the two-segment ``{provider}/{hook_name}`` receiver.
    app.attach_route(
        base + "/integrations", methods=["GET"],
    )(handle_list_integrations)
    app.attach_route(
        base + "/integrations", methods=["POST"],
    )(handle_create_integration)
    app.attach_route(
        base + "/integrations/{webhook_id}", methods=["PATCH"],
    )(handle_update_integration)
    app.attach_route(
        base + "/deliveries", methods=["GET"],
    )(handle_list_deliveries)
    app.attach_route(
        base + "/{provider}/{hook_name}", methods=["POST"],
    )(handle_receive_webhook)

    _LOGGER.info(
        "pychestrate.webhooks_in.routes.wired: POST"
        " /webhooks/in/{provider}/{hook_name} runs the inbound"
        " verification + replay + dispatch pipeline."
    )
    return


__all__ = [
    "WEBHOOKS_IN_PATH_PREFIX",
    "WEBHOOKS_READ_PERMISSION_KEY",
    "WEBHOOKS_WRITE_PERMISSION_KEY",
    "register_webhooks_in_routes",
    "handle_receive_webhook",
    "handle_list_integrations",
    "handle_create_integration",
    "handle_update_integration",
    "handle_list_deliveries",
]
