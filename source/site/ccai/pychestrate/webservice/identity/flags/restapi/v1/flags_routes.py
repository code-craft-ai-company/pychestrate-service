"""
.. module:: identity.flags.restapi.v1.flags_routes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-native REST routes for /api/v1/flags.

.. moduleauthor:: Code Craft AI LLC

The production webservice runs on ``ccai.webworks`` (see
:mod:`app_pychestrate_main`); the ``flags_controller`` module
sitting next to this one is legacy scaffold that pre-dates
the webworks migration and is not loaded in production. This
module is the webworks-native REST surface for the flag
lifecycle.

Eight routes:

* ``GET    /api/v1/flags``                          — list flags
* ``POST   /api/v1/flags``                          — create flag
* ``GET    /api/v1/flags/{flag_key}``               — read flag
* ``PATCH  /api/v1/flags/{flag_key}``               — update flag
* ``POST   /api/v1/flags/{flag_key}/retire``        — retire flag
* ``GET    /api/v1/flags/{flag_key}/history``       — list versions
* ``POST   /api/v1/flags/{flag_key}/evaluate``      — evaluate flag
* ``GET    /api/v1/flags/backends``                 — list backends

Error responses
---------------
All 4xx / 5xx responses are RFC 7807 problem documents served
with the documented ``application/problem+json`` content type.
The webworks dispatcher does not pass custom bodies through
``HTTPException`` (it rebuilds the body in its content-negotiated
shape), so the helpers here use ``problem_response_for_http_status``
from :mod:`api.problem_json_webworks` and **return** the response
rather than raising. An internal ``_ProblemAbort`` exception lets
nested helpers signal an error without each one threading a
sentinel back to the handler; the handler catches it once at the
boundary and returns ``exc.response``.

Request-scoped values
---------------------
Handlers read the per-request SQLAlchemy session and actor id
from attributes attached to the :class:`Request` object by
:mod:`webservice.middleware_webworks` —
:class:`PychestrateSessionMiddleware` opens a session per request
and attaches it as ``request.db_session``, plus resolves the
session cookie to an :class:`AuthPrincipal` and writes
``request.actor_user_id``. The handlers below read those
attributes via :func:`_resolve_db_session` /
:func:`_resolve_actor_user_id` (module-level so tests can patch
them). When the session attribute is missing — i.e., the
middleware was not installed — the handler returns a 503
problem document with the ``"Request-scoped db_session not
configured"`` detail rather than producing an opaque traceback.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Optional, Tuple

from ccai.errors.exceptions import SemanticError
from ccai.webworks.routing.request import Request
from ccai.webworks.routing.response import JSONResponse, Response

from ccai.pychestrate.webservice.api.problem_json_webworks import (
    problem_response_for_http_status,
)
from ccai.pychestrate.webservice.identity.flags import (
    backend_router,
    flag_evaluator,
    flag_service,
)
from ccai.pychestrate.webservice.identity.flags.exceptions import (
    FlagAlreadyExistsError,
    FlagNotFoundError,
)
from ccai.pychestrate.webservice.identity.flags.models import (
    FeatureFlag,
    FeatureFlagVersion,
    FlagContext,
    FlagKind,
)


FLAGS_PATH = "/flags"


class _ProblemAbort(Exception):
    """
        Internal control-flow exception. Carries a webworks problem
        response so nested helpers can signal an error condition once
        and the handler can convert it to a return at the boundary.

        Never escapes this module; if it does, it is a bug in the
        handler wiring and the caller will see a generic 500.
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
        flag_key: Optional[str] = None
    ) -> None:
    """
        Build a problem response from the request context and raise
        :class:`_ProblemAbort` so the handler returns the response.

        :param request: The incoming webworks request (used for the
                        ``instance`` URI).
        :param status: HTTP status code.
        :param detail: Occurrence-specific explanation.
        :param flag_key: Optional flag key to attach as an extension
                         member when present, supplying per-flag
                         error context.

        :returns: Never returns; raises :class:`_ProblemAbort`.
        :raises: :class:`_ProblemAbort` always.
    """
    extensions: Optional[dict] = None
    if flag_key is not None:
        extensions = {"flag_key": flag_key}

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
        :class:`PychestrateSessionMiddleware`, or ``None`` when no
        middleware has populated it (e.g., misconfigured deployment
        or test bypass).

        Module-level so tests patch this rather than constructing a
        full middleware stack.

        :param request: Incoming webworks request.

        :returns: Session or None.
    """
    rtnval = getattr(request, "db_session", None)
    return rtnval


def _resolve_actor_user_id(request: Request) -> Optional[str]:
    """
        Return the authenticated actor's user id from the request, or
        ``None`` when no auth middleware has populated it.

        :param request: Incoming webworks request.

        :returns: User id string or None.
    """
    rtnval = getattr(request, "actor_user_id", None)
    return rtnval


def _require_session(request: Request) -> Any:
    """
        Resolve the request-scoped db session or abort with a 503
        problem document on misconfigured deployments.

        :param request: Incoming webworks request.

        :returns: Session.
        :raises: :class:`_ProblemAbort` (503) when no session is
                 attached.
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


def _parse_kind_or_abort(*, request: Request, flag_kind_raw: str) -> FlagKind:
    """
        Coerce a ``flag_kind`` string to a :class:`FlagKind` enum,
        aborting with a 422 problem document on unknown values.

        :param request: Incoming webworks request (for the instance
                        URI).
        :param flag_kind_raw: Raw value from the request payload.

        :returns: The matching :class:`FlagKind`.
        :raises: :class:`_ProblemAbort` (422) on unknown values.
    """
    try:
        kind = FlagKind(flag_kind_raw)
    except ValueError:
        _abort_problem(
            request=request,
            status=422,
            detail="Unknown flag_kind value: {}".format(flag_kind_raw),
        )

    rtnval = kind
    return rtnval


def _build_context_or_abort(
        *,
        request: Request,
        payload: dict,
        flag_key: str
    ) -> FlagContext:
    """
        Build a :class:`FlagContext` from an evaluation payload.
        Aborts with a 400 when ``bucketing_key`` is missing or
        ``attributes`` is the wrong shape.

        :param request: Incoming webworks request.
        :param payload: Decoded JSON request body.
        :param flag_key: The flag key being evaluated (attached as an
                         extension member on error).

        :returns: The constructed :class:`FlagContext`.
        :raises: :class:`_ProblemAbort` (400) on shape errors.
    """
    bucketing_key = payload.get("bucketing_key", "")
    if bucketing_key is None or len(str(bucketing_key)) == 0:
        _abort_problem(
            request=request,
            status=400,
            detail="bucketing_key is required",
            flag_key=flag_key,
        )

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
            _abort_problem(
                request=request,
                status=400,
                detail="attributes must be a JSON object",
                flag_key=flag_key,
            )

    rtnval = FlagContext(
        bucketing_key=str(bucketing_key),
        user_id=str(user_id_raw) if user_id_raw is not None else None,
        project_id=str(project_id_raw) if project_id_raw is not None else None,
        attributes=attribute_pairs,
    )
    return rtnval


def _flag_to_dict(flag: FeatureFlag) -> dict:
    """
        Serialize a :class:`FeatureFlag` to its wire-form dict.

        :param flag: ORM flag instance.

        :returns: JSON-friendly dict.
    """
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
    """
        Serialize a :class:`FeatureFlagVersion` to its wire-form dict.

        :param version: ORM version instance.

        :returns: JSON-friendly dict.
    """
    rtnval = {
        "flag_key": version.flag_key,
        "version": int(version.version),
        "default_value": version.default_value,
        "rules_json": version.rules_json,
        "created_at": (
            version.created_at.isoformat() if version.created_at is not None else None
        ),
    }
    return rtnval


def _decode_json_or_abort(*, request: Request) -> dict:
    """
        Decode the request body as JSON, aborting with a 400 when the
        body is missing or malformed.

        :param request: Incoming webworks request.

        :returns: Decoded JSON object (always a dict; non-dict bodies
                  abort).
        :raises: :class:`_ProblemAbort` (400) on bad input.
    """
    try:
        payload = request.json()
    except Exception:
        payload = None

    if payload is None:
        _abort_problem(
            request=request, status=400, detail="Request body must be JSON"
        )

    if not isinstance(payload, dict):
        _abort_problem(
            request=request,
            status=400,
            detail="Request body must be a JSON object",
        )

    rtnval = payload
    return rtnval


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def handle_list_flags(request: Request) -> Response:
    """
        ``GET /api/v1/flags`` — list every registered flag, ordered by
        ``flag_key``.

        :param request: Incoming webworks request.

        :returns: JSON response (200) carrying a list of flag dicts,
                  or a problem response on failure.
    """
    try:
        db_session = _require_session(request=request)
        flags = flag_service.list_flags(db_session=db_session)
        body = [_flag_to_dict(flag) for flag in flags]
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


def handle_create_flag(request: Request) -> Response:
    """
        ``POST /api/v1/flags`` — create a new flag at version 1.
    """
    try:
        payload = _decode_json_or_abort(request=request)
        db_session = _require_session(request=request)

        flag_key = payload.get("flag_key", "")
        flag_kind = _parse_kind_or_abort(
            request=request, flag_kind_raw=payload.get("flag_kind", "")
        )
        actor_user_id = _resolve_actor_user_id(request=request)

        try:
            flag = flag_service.create_flag(
                db_session=db_session,
                flag_key=flag_key,
                flag_kind=flag_kind,
                default_value=payload.get("default_value", None),
                rules=payload.get("rules", None),
                actor_user_id=actor_user_id,
            )
        except FlagAlreadyExistsError as xcpt:
            _abort_problem(
                request=request, status=409, detail=str(xcpt), flag_key=flag_key
            )
        except SemanticError as xcpt:
            _abort_problem(
                request=request, status=422, detail=str(xcpt), flag_key=flag_key
            )

        body = _flag_to_dict(flag)
        rtnval: Response = JSONResponse(content=body, status_code=201)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


def handle_read_flag(request: Request) -> Response:
    """
        ``GET /api/v1/flags/{flag_key}`` — read the current view of a
        flag.
    """
    flag_key = request.path_params.get("flag_key", "")
    try:
        db_session = _require_session(request=request)
        flag = (
            db_session.query(FeatureFlag)
            .filter(FeatureFlag.flag_key == flag_key)
            .first()
        )
        if flag is None:
            _abort_problem(
                request=request,
                status=404,
                detail="Feature flag not found: {}".format(flag_key),
                flag_key=flag_key,
            )

        body = _flag_to_dict(flag)
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


def handle_update_flag(request: Request) -> Response:
    """
        ``PATCH /api/v1/flags/{flag_key}`` — bump the active version
        with new rules / default. ``flag_kind`` is immutable; passing
        a different kind returns 422.
    """
    flag_key = request.path_params.get("flag_key", "")
    try:
        payload = _decode_json_or_abort(request=request)
        db_session = _require_session(request=request)
        actor_user_id = _resolve_actor_user_id(request=request)

        kind_raw = payload.get("flag_kind", None)
        kind_for_redundant_check: Optional[FlagKind] = None
        if kind_raw is not None:
            kind_for_redundant_check = _parse_kind_or_abort(
                request=request, flag_kind_raw=kind_raw
            )

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
            _abort_problem(
                request=request, status=404, detail=str(xcpt), flag_key=flag_key
            )
        except SemanticError as xcpt:
            _abort_problem(
                request=request, status=422, detail=str(xcpt), flag_key=flag_key
            )

        body = _flag_to_dict(flag)
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


def handle_retire_flag(request: Request) -> Response:
    """
        ``POST /api/v1/flags/{flag_key}/retire`` — retire with a grace
        window before removal.
    """
    flag_key = request.path_params.get("flag_key", "")
    try:
        try:
            payload_raw = request.json()
        except Exception:
            payload_raw = None
        payload = payload_raw if isinstance(payload_raw, dict) else {}

        db_session = _require_session(request=request)
        actor_user_id = _resolve_actor_user_id(request=request)

        grace_seconds_raw = payload.get(
            "grace_seconds", flag_service.DEFAULT_GRACE_SECONDS
        )
        try:
            grace_seconds = int(grace_seconds_raw)
        except (TypeError, ValueError):
            _abort_problem(
                request=request,
                status=400,
                detail="grace_seconds must be an integer number of seconds",
            )

        try:
            flag = flag_service.retire_flag(
                db_session=db_session,
                flag_key=flag_key,
                grace_seconds=grace_seconds,
                actor_user_id=actor_user_id,
            )
        except FlagNotFoundError as xcpt:
            _abort_problem(
                request=request, status=404, detail=str(xcpt), flag_key=flag_key
            )
        except SemanticError as xcpt:
            _abort_problem(
                request=request, status=422, detail=str(xcpt), flag_key=flag_key
            )

        body = _flag_to_dict(flag)
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


def handle_list_flag_versions(request: Request) -> Response:
    """
        ``GET /api/v1/flags/{flag_key}/history`` — list every version
        for a flag.
    """
    flag_key = request.path_params.get("flag_key", "")
    try:
        db_session = _require_session(request=request)

        try:
            versions = flag_service.list_flag_versions(
                db_session=db_session, flag_key=flag_key
            )
        except FlagNotFoundError as xcpt:
            _abort_problem(
                request=request, status=404, detail=str(xcpt), flag_key=flag_key
            )

        body = [_version_to_dict(version) for version in versions]
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


def handle_evaluate_flag(request: Request) -> Response:
    """
        ``POST /api/v1/flags/{flag_key}/evaluate`` — evaluate the flag
        against a caller-supplied :class:`FlagContext`.
    """
    flag_key = request.path_params.get("flag_key", "")
    try:
        payload = _decode_json_or_abort(request=request)
        db_session = _require_session(request=request)

        context = _build_context_or_abort(
            request=request, payload=payload, flag_key=flag_key
        )
        default = payload.get("default", None)

        try:
            value = flag_evaluator.evaluate_flag(
                db_session=db_session,
                flag_key=flag_key,
                context=context,
                default=default,
            )
        except SemanticError as xcpt:
            _abort_problem(
                request=request, status=422, detail=str(xcpt), flag_key=flag_key
            )

        flag = (
            db_session.query(FeatureFlag)
            .filter(FeatureFlag.flag_key == flag_key)
            .first()
        )
        version_value = int(flag.current_version) if flag is not None else 0

        body = {
            "flag_key": flag_key,
            "value": value,
            "version": version_value,
        }
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


def handle_list_flag_backends(request: Request) -> Response:
    """
        ``GET /api/v1/flags/backends`` — list registered backends.
    """
    snapshot = backend_router.diagnostic_snapshot()
    entries = list(snapshot.values())
    entries.sort(key=lambda entry: entry.get("precedence", 1000))
    rtnval = JSONResponse(content=entries, status_code=200)
    return rtnval


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_flags_routes(*, app: Any, version_prefix: str) -> None:
    """
        Attach the flag-lifecycle routes to a webworks application.

        Called from :func:`pychestrate_website_main` -
        :func:`register_service_extensions` before
        ``app.startup``. Order with respect to other registration
        calls is irrelevant; routes are queued until the
        infrastructure-ready phase and flushed there.

        Note that the ``/backends`` route is registered BEFORE the
        ``/{flag_key}`` route would otherwise greedily match it. The
        webworks router resolves overlapping patterns by registration
        order; declaring ``/backends`` first guarantees ``GET
        /api/v1/flags/backends`` does not get routed to
        :func:`handle_read_flag` with a path param of ``"backends"``.

        :param app: WebWorks application built by
                    ``establish_webapp_persona``.
        :param version_prefix: Versioned API prefix (e.g.
                               ``"/api/v1"``).

        :returns: None.
    """
    base = version_prefix + FLAGS_PATH

    app.attach_route(base + "/backends", methods=["GET"])(
        handle_list_flag_backends
    )

    app.attach_route(base, methods=["GET"])(handle_list_flags)
    app.attach_route(base, methods=["POST"])(handle_create_flag)

    app.attach_route(base + "/{flag_key}", methods=["GET"])(handle_read_flag)
    app.attach_route(base + "/{flag_key}", methods=["PATCH"])(handle_update_flag)

    app.attach_route(base + "/{flag_key}/retire", methods=["POST"])(
        handle_retire_flag
    )
    app.attach_route(base + "/{flag_key}/history", methods=["GET"])(
        handle_list_flag_versions
    )
    app.attach_route(base + "/{flag_key}/evaluate", methods=["POST"])(
        handle_evaluate_flag
    )

    return


__all__ = [
    "FLAGS_PATH",
    "register_flags_routes",
    "handle_list_flags",
    "handle_create_flag",
    "handle_read_flag",
    "handle_update_flag",
    "handle_retire_flag",
    "handle_list_flag_versions",
    "handle_evaluate_flag",
    "handle_list_flag_backends",
]
