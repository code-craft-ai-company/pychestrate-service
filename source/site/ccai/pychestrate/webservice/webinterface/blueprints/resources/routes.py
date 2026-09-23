"""
.. module:: webinterface.blueprints.resources.routes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-native consumer-facing UI for /resources
               (E1 slice -- dashboard + resources core).

.. moduleauthor:: Code Craft AI LLC

The resources blueprint owns the consumer-facing ``/resources``
surface. This module lands the dashboard + the seven core
``/resources/*`` routes (list / create / detail / edit / delete
/ checkout):

* ``GET  /resources/`` and ``/resources/dashboard`` -- summary
                                                       statistics
                                                       page.
* ``GET  /resources/list``                          -- list +
                                                       filters
                                                       (pool /
                                                       type / health
                                                       / tags /
                                                       search).
* ``GET  /resources/create``                        -- create form.
* ``POST /resources/create``                        -- create.
* ``GET  /resources/{resource_id}``                 -- detail +
                                                       active
                                                       allocations.
* ``GET  /resources/{resource_id}/edit``            -- edit form.
* ``POST /resources/{resource_id}/edit``            -- update.
* ``POST /resources/{resource_id}/delete``          -- delete.
* ``POST /resources/{resource_id}/checkout``        -- check out a
                                                       resource for
                                                       a job.

Pre-registers the URL patterns for the sibling resource
endpoints (pools / ip_pools / allocations / reservations /
health / tags) so the dashboard sidebar's
``url_for('resources.pool_list')`` etc. resolve at template
render time.

Foundation pieces consumed
--------------------------

The auth resolver, session cookie management, CSRF guard,
flash queue, jinja2 environment, ``url_for`` shim, multi-form
parsing, default-context builder, and the
``_require_permission_or_redirect`` admin guard all come from
:mod:`webinterface.blueprints.config.routes`.

Auth backend
------------

Every authenticated handler routes through
:class:`SecurityManager`. The
``check_permission(user_id, 'resources.manage')`` gate guards
the create / edit / delete handlers via the
``_require_permission_or_redirect`` helper; checkout is
login-required only.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import logging

from typing import Any, Callable, Dict, List, Optional

from ccai.webworks.routing.request import Request
from ccai.webworks.routing.response import (
    HTMLResponse,
    RedirectResponse,
    Response,
)

from ccai.pychestrate.webservice.webinterface.foundation import (
    auth_guard,
    csrf,
    flash,
    url_for as _url_for_module,
)
from ccai.pychestrate.webservice.webinterface.blueprints.config.routes import (
    MultiFormView,
    _attach_session_to_response,
    _build_default_template_context,
    _has_permission,
    _parse_form_multi,
    _parse_form_or_empty,
    _redirect_with_flash,
    _render,
    _require_permission_or_redirect,
    _resolve_authenticated_request,
    _wrap_fragment_handler_in_shell,
)


RESOURCES_PATH = "/resources"

_DEFAULT_RESOURCES_PAGE_TITLE = "Pychestrate"

# Second path segment (/resources/<segment>) -> tab label. Deeper
# paths inherit their section's label.
_RESOURCES_SECTION_TITLE_LABELS: Dict[str, str] = {
    "pools": "Resource Pools",
    "ip-pools": "IP Pools",
    "allocations": "Allocations",
    "reservations": "Reservations",
    "health": "Resource Health",
    "tags": "Tags",
    "create": "New Resource",
}


def _resolve_resources_page_title(*, path: str) -> str:
    """
        Resolve the shell document ``<title>`` for a resources page
        from the request path (``/resources/ip-pools/7`` ->
        ``"IP Pools · Pychestrate"``).

        :param path: Request path.

        :returns: Title string.
    """
    if path is None or len(path) == 0:
        return _DEFAULT_RESOURCES_PAGE_TITLE
    segments = [segment for segment in path.split("/") if len(segment) > 0]
    if len(segments) == 0 or segments[0] != "resources":
        return _DEFAULT_RESOURCES_PAGE_TITLE
    label = "Resources"
    if len(segments) >= 2:
        label = _RESOURCES_SECTION_TITLE_LABELS.get(segments[1], "Resource")
    rtnval = "{} · {}".format(label, _DEFAULT_RESOURCES_PAGE_TITLE)
    return rtnval


def _wrap_resources_handler_in_shell(handler: Any) -> Any:
    """
        Render a resources-blueprint handler's HTML inside the site
        shell (UI remediation Phase 2, finding R-1). The resources
        pages used to ship as standalone documents with their own
        header and sidebar; ``resources/base.html`` is now a fragment
        like the admin and projects bases.

        :param handler: The original handler.

        :returns: Shell-wrapping handler.
    """
    rtnval = _wrap_fragment_handler_in_shell(
        handler, title_resolver=_resolve_resources_page_title
    )
    return rtnval
_LOGGER = logging.getLogger("pychestrate.ui.resources")


_ROUTE_TABLE = (
    ("resources.dashboard_root", "/", ("GET",)),
    ("resources.dashboard", "/dashboard", ("GET",)),
    ("resources.resource_list", "/list", ("GET",)),
    ("resources.resource_create", "/create", ("GET", "POST")),
    ("resources.resource_detail", "/{resource_id}", ("GET",)),
    (
        "resources.resource_edit",
        "/{resource_id}/edit",
        ("GET", "POST"),
    ),
    (
        "resources.resource_delete",
        "/{resource_id}/delete",
        ("POST",),
    ),
    (
        "resources.resource_checkout",
        "/{resource_id}/checkout",
        ("POST",),
    ),
)


# All previously-stubbed resources endpoints have shipped. The
# tuple stays in the source as a hook for any post-E4 additions.
_FUTURE_ENDPOINT_PATTERNS: tuple = ()


_ADMIN_PERMISSION = "system:resources.manage"


def _resources_permission_flags(*, auth: Any) -> Dict[str, Any]:
    """
        Template flags for the resources pages: ``can_manage`` is the
        same probe the write handlers gate on, so templates can hide
        Create / Edit / Delete / Force-checkin controls from users the
        gate would bounce (audit findings R-4, R-12).
        ``current_user_id`` lets a template show owner-only controls
        (checkin, cancel reservation) on the rows the user owns.

        :param auth: Resolution from ``_resolve_authenticated_request``.

        :returns: Dict to merge into the render context.
    """
    rtnval = {
        "can_manage": _has_permission(auth=auth, permission=_ADMIN_PERMISSION),
        "current_user_id": getattr(auth, "user_id", ""),
    }
    return rtnval
# ---------------------------------------------------------------------------
# Lazy-import builder seams (test-patchable)
# ---------------------------------------------------------------------------


def _build_resource_manager(*, db_session: Any) -> Any:
    """
        Construct a :class:`ResourceManager`. Lazy-imports the
        class so tests can patch this builder without importing
        the source module.
    """
    from ccai.pychestrate.core.managers.resource_manager import (  # noqa: E402
        ResourceManager,
    )
    rtnval = ResourceManager(db_session)
    return rtnval


def _build_allocation_manager(*, db_session: Any) -> Any:
    """
        Construct an :class:`AllocationManager`. Lazy-imports.
    """
    from ccai.pychestrate.core.managers.allocation_manager import (  # noqa: E402
        AllocationManager,
    )
    rtnval = AllocationManager(db_session)
    return rtnval


def _build_ip_pool_manager(*, db_session: Any) -> Any:
    """
        Construct an :class:`IPPoolManager`. Lazy-imports.
    """
    from ccai.pychestrate.core.managers.ip_pool_manager import (  # noqa: E402
        IPPoolManager,
    )
    rtnval = IPPoolManager(db_session)
    return rtnval


def _resolve_resource_type(*, resource_type_str: str) -> Any:
    """
        Resolve a ``resource_type`` form value to the manager's
        :class:`ResourceType` enum value. Raises ValueError on
        unknown.
    """
    from ccai.pychestrate.core.orm import (  # noqa: E402
        ResourceType,
    )
    rtnval = ResourceType(resource_type_str)
    return rtnval


def _resolve_health_status_or_none(
        *, health_status_str: Optional[str]
    ) -> Optional[Any]:
    """
        Resolve a ``health_status`` form value to the manager's
        :class:`HealthStatus` enum value. Returns ``None`` on
        empty / unknown so handlers can branch without try/except.
    """
    if health_status_str is None or len(health_status_str) == 0:
        return None
    try:
        from ccai.pychestrate.core.orm import (  # noqa: E402
            HealthStatus,
        )
        rtnval = HealthStatus(health_status_str)
        return rtnval
    except (ValueError, ImportError):
        return None


def _resolve_allocation_mode(*, mode_str: str) -> Any:
    """
        Resolve an ``allocation mode`` form value to the
        :class:`AllocationMode` enum value. Raises ValueError on
        unknown.
    """
    from ccai.pychestrate.core.orm import (  # noqa: E402
        AllocationMode,
    )
    rtnval = AllocationMode(mode_str)
    return rtnval


def _build_resource_create_request(
        *,
        name: str,
        resource_type: Any,
        pool_id: Optional[int],
        description: str,
        metadata: Dict[str, Any],
        tags: List[str],
        capacity: int
    ) -> Any:
    """
        Construct a :class:`ResourceCreateRequest`. Lazy-imports.
    """
    from ccai.pychestrate.core.managers.resource_manager import (  # noqa: E402
        ResourceCreateRequest,
    )
    rtnval = ResourceCreateRequest(
        name=name,
        resource_type=resource_type,
        pool_id=pool_id,
        description=description,
        metadata=metadata,
        tags=tags,
        capacity=capacity,
    )
    return rtnval


def _build_resource_update_request(
        *,
        description: Optional[str],
        metadata: Optional[Dict[str, Any]],
        tags: Optional[List[str]],
        capacity: Optional[int],
        health_status: Optional[Any]
    ) -> Any:
    """
        Construct a :class:`ResourceUpdateRequest`. Lazy-imports.
    """
    from ccai.pychestrate.core.managers.resource_manager import (  # noqa: E402
        ResourceUpdateRequest,
    )
    rtnval = ResourceUpdateRequest(
        description=description,
        metadata=metadata,
        tags=tags,
        capacity=capacity,
        health_status=health_status,
    )
    return rtnval


def _build_checkout_request(
        *,
        resource_id: int,
        job_id: Optional[str],
        mode: Any,
        timeout_minutes: Optional[int],
        reason: str
    ) -> Any:
    """
        Construct a :class:`CheckoutRequest`. Lazy-imports.
    """
    from ccai.pychestrate.core.managers.allocation_manager import (  # noqa: E402
        CheckoutRequest,
    )
    rtnval = CheckoutRequest(
        resource_id=resource_id,
        job_id=job_id,
        mode=mode,
        timeout_minutes=timeout_minutes,
        reason=reason,
    )
    return rtnval


# ---------------------------------------------------------------------------
# Local helpers
# ---------------------------------------------------------------------------


def _coerce_int(*, raw: Any) -> Optional[int]:
    if raw is None:
        return None
    try:
        rtnval = int(raw)
    except (TypeError, ValueError):
        return None
    return rtnval


def _coerce_int_with_default(*, raw: Any, default: int) -> int:
    parsed = _coerce_int(raw=raw)
    if parsed is None:
        return default
    return parsed


def _parse_pagination_params(
        *, request: Request,
        default_per_page: int = 20
    ) -> Dict[str, Any]:
    page = _coerce_int_with_default(
        raw=request.query_params.get("page", None), default=1
    )
    if page < 1:
        page = 1

    per_page = _coerce_int_with_default(
        raw=request.query_params.get("per_page", None),
        default=default_per_page,
    )
    if per_page < 1:
        per_page = default_per_page

    rtnval = {"page": page, "per_page": per_page}
    return rtnval


def _parse_metadata_json_or_default(
        *, raw: str, default: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
    """
        Parse a JSON object string from the metadata textarea.
        Returns ``default`` when ``raw`` is empty. Raises
        ``ValueError`` (caught + flashed by the caller) on a
        decode failure -- mirrors the legacy handler's
        ``json.JSONDecodeError`` -> flash branch.

        :param raw: Form-submitted metadata string.
        :param default: Fallback (None) on empty input.

        :returns: Parsed dict on valid JSON; ``default`` on empty.
        :raises: ValueError when the input is non-empty but not
                 valid JSON.
    """
    if raw is None or len(raw) == 0:
        return default
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("Invalid JSON in metadata field.") from exc
    if not isinstance(parsed, dict):
        raise ValueError(
            "Metadata must be a JSON object, not a {}".format(
                type(parsed).__name__
            )
        )
    return parsed


def _calculate_total_pages(*, total: int, per_page: int) -> int:
    """
        Compute the real page count from a manager's total row
        count. Always at least 1 so templates can render a page
        indicator unconditionally.

        :param total: Total matching rows reported by the manager.
        :param per_page: Page size.

        :returns: Number of pages (>= 1).
    """
    if total <= 0:
        return 1
    rtnval = (total + per_page - 1) // per_page
    return rtnval


def _build_page_window(
        *, page: int, total_pages: int, width: int = 2
    ) -> List[int]:
    """
        Build the run of page numbers to render around the
        current page (first/last/prev/next are rendered
        separately by the pagination template block).

        :param page: Current page (1-based).
        :param total_pages: Real page count.
        :param width: Pages shown on each side of the current page.

        :returns: Contiguous list of page numbers.
    """
    start = page - width
    if start < 1:
        start = 1
    end = page + width
    if end > total_pages:
        end = total_pages
    rtnval = list(range(start, end + 1))
    return rtnval


def _describe_resource_manager_error(*, exc: Exception) -> Optional[str]:
    """
        Map a typed ResourceManager error to its deliberate,
        user-facing message. Returns None when ``exc`` is not one
        of the typed errors -- callers then log the exception and
        flash a generic sentence instead of the raw exception
        text. Lazy-imports so this module stays importable when
        the manager package is absent (test runtimes patch the
        manager builders).

        :param exc: The exception raised by a ResourceManager call.

        :returns: Specific user-facing message, or None.
    """
    try:
        from ccai.pychestrate.core.managers.resource_manager import (  # noqa: E402
            DuplicateResourceError,
            PoolHasResourcesError,
            PoolNotFoundError,
            ResourceHasAllocationsError,
            ResourceNotFoundError,
            ResourceValidationError,
            TagNotFoundError,
        )
    except ImportError:
        return None

    typed_errors = (
        DuplicateResourceError,
        PoolHasResourcesError,
        PoolNotFoundError,
        ResourceHasAllocationsError,
        ResourceNotFoundError,
        ResourceValidationError,
        TagNotFoundError,
    )
    if isinstance(exc, typed_errors):
        rtnval = exc.message
        return rtnval
    return None


def _describe_allocation_error(*, exc: Exception) -> Optional[str]:
    """
        Map a typed AllocationManager error to a specific,
        user-facing message. ``ResourceUnavailableError`` includes
        who currently holds the resource and until when (from the
        ``current_allocation`` payload); capacity / conflict /
        lock errors get actionable guidance. Returns None when
        ``exc`` is not a typed allocation error.

        :param exc: The exception raised by an AllocationManager
                    call.

        :returns: Specific user-facing message, or None.
    """
    try:
        from ccai.pychestrate.core.managers.allocation_manager import (  # noqa: E402
            AllocationError,
            CapacityExceededError,
            ConcurrentModificationError,
            LockTimeoutError,
            ReservationConflictError,
            ResourceUnavailableError,
        )
    except ImportError:
        return None

    if isinstance(exc, ResourceUnavailableError):
        msg_parts = ["{}.".format(exc.message)]
        current = exc.current_allocation
        if current is not None:
            if current.username is not None:
                holder = current.username
            else:
                holder = "user {}".format(current.user_id)
            msg_parts.append(
                "Held by {} (allocation #{}).".format(holder, current.id)
            )
            if current.expected_checkin is not None:
                msg_parts.append(
                    "Expected checkin: {}.".format(
                        current.expected_checkin.strftime("%Y-%m-%d %H:%M")
                    )
                )
            else:
                msg_parts.append("No expected checkin time is set.")
        rtnval = " ".join(msg_parts)
        return rtnval

    if isinstance(exc, CapacityExceededError):
        msg_parts = ["{}.".format(exc.message)]
        if exc.capacity is not None and exc.current_allocations is not None:
            msg_parts.append(
                "{} of {} allocation slots are in use.".format(
                    exc.current_allocations, exc.capacity
                )
            )
        msg_parts.append("Check in an allocation to free capacity.")
        rtnval = " ".join(msg_parts)
        return rtnval

    if isinstance(exc, ReservationConflictError):
        msg_parts = ["{}.".format(exc.message)]
        for conflict in exc.conflicting_reservations[:3]:
            msg_parts.append(
                "Reservation #{} holds {} to {}.".format(
                    conflict.id,
                    conflict.start_time.strftime("%Y-%m-%d %H:%M"),
                    conflict.end_time.strftime("%Y-%m-%d %H:%M"),
                )
            )
        rtnval = " ".join(msg_parts)
        return rtnval

    if isinstance(exc, LockTimeoutError):
        rtnval = "{}. Please try again.".format(exc.message)
        return rtnval

    if isinstance(exc, ConcurrentModificationError):
        rtnval = (
            "{}. Refresh the page and try again.".format(exc.message)
        )
        return rtnval

    if isinstance(exc, AllocationError):
        # Remaining typed errors (offline, not-found, not-owner,
        # invalid-window, no-matching-resource) carry deliberate
        # user-appropriate messages.
        rtnval = exc.message
        return rtnval
    return None


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def handle_dashboard(request: Request) -> Response:
    """
        ``GET /resources/`` and ``/resources/dashboard`` --
        summary statistics page.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        resource_manager = _build_resource_manager(db_session=db_session)
        allocation_manager = _build_allocation_manager(
            db_session=db_session
        )
        ip_pool_manager = _build_ip_pool_manager(db_session=db_session)

        # The summary cards use the managers' real totals -- the
        # ``*ListResponse`` dataclasses carry a ``total`` computed
        # by a count query, and the health cards come from a
        # dedicated aggregate query -- so the dashboard never
        # undercounts past a fetch limit.
        resource_count = resource_manager.list_resources(limit=1).total
        pool_count = resource_manager.list_pools(
            auth.user_id, limit=1
        ).total
        ip_pool_count = ip_pool_manager.list_pools(
            auth.user_id, limit=1
        ).total
        active_allocation_count = allocation_manager.list_allocations(
            status="active", limit=1
        ).total

        health_counts = resource_manager.count_resources_by_health_status()

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="resources.dashboard",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context.update(_resources_permission_flags(auth=auth))
        context["resource_count"] = resource_count
        context["pool_count"] = pool_count
        context["ip_pool_count"] = ip_pool_count
        context["active_allocation_count"] = active_allocation_count
        context["health_counts"] = health_counts

        response = _render(
            template_name="resources/dashboard.html",
            context=context,
        )
        _attach_session_to_response(
            response=response, session=auth.session
        )
        return response
    finally:
        try:
            db_session.close()
        except Exception:
            pass


def handle_resource_list(request: Request) -> Response:
    """
        ``GET /resources/list`` -- paginated list with optional
        ``?pool_id=`` / ``?resource_type=`` / ``?health_status=``
        / ``?search=`` / ``?tags=t1&tags=t2`` filters.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        params = _parse_pagination_params(request=request)
        offset = (params["page"] - 1) * params["per_page"]

        pool_id = _coerce_int(
            raw=request.query_params.get("pool_id", None)
        )
        resource_type_str = (
            request.query_params.get("resource_type", None) or None
        )
        health_status_str = (
            request.query_params.get("health_status", None) or None
        )
        search = request.query_params.get("search", "") or ""
        # The list filter expects multi-valued ``tags`` -- the
        # query string can carry repeated ``?tags=…`` pairs.
        tag_query = []
        try:
            tag_query = list(request.query_params.getlist("tags"))
        except Exception:
            tag_query = []

        filter_kwargs: Dict[str, Any] = {
            "offset": offset,
            "limit": params["per_page"],
        }
        if pool_id is not None:
            filter_kwargs["pool_id"] = pool_id
        if resource_type_str is not None:
            try:
                filter_kwargs["resource_type"] = _resolve_resource_type(
                    resource_type_str=resource_type_str
                )
            except (ValueError, ImportError):
                pass
        if health_status_str is not None:
            resolved_status = _resolve_health_status_or_none(
                health_status_str=health_status_str
            )
            if resolved_status is not None:
                filter_kwargs["health_status"] = resolved_status
        if len(tag_query) > 0:
            filter_kwargs["tags"] = tag_query
        if len(search) > 0:
            filter_kwargs["search"] = search

        resource_manager = _build_resource_manager(db_session=db_session)
        resources_response = resource_manager.list_resources(
            **filter_kwargs
        )
        resources = resources_response.resources
        pools = resource_manager.list_pools(auth.user_id).pools
        all_tags = resource_manager.list_tags().tags

        total_pages = _calculate_total_pages(
            total=resources_response.total,
            per_page=params["per_page"],
        )
        page_window = _build_page_window(
            page=params["page"], total_pages=total_pages
        )

        filters_active = (
            pool_id is not None
            or resource_type_str is not None
            or health_status_str is not None
            or len(tag_query) > 0
            or len(search) > 0
        )

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="resources.resource_list",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context.update(_resources_permission_flags(auth=auth))
        context["resources"] = resources
        context["resource_total"] = resources_response.total
        context["pools"] = pools
        context["all_tags"] = all_tags
        context["page"] = params["page"]
        context["per_page"] = params["per_page"]
        context["total_pages"] = total_pages
        context["page_window"] = page_window
        context["filters_active"] = filters_active
        context["selected_pool_id"] = pool_id
        context["selected_resource_type"] = resource_type_str
        context["selected_health_status"] = health_status_str
        context["selected_tags"] = tag_query
        context["search"] = search

        response = _render(
            template_name="resources/resources/list.html",
            context=context,
        )
        _attach_session_to_response(
            response=response, session=auth.session
        )
        return response
    finally:
        try:
            db_session.close()
        except Exception:
            pass


def _render_resource_create_form(
        *,
        auth: Any,
        resource_manager: Any,
        form_data: Optional[MultiFormView],
        status_code: int = 200
    ) -> HTMLResponse:
    """
        Helper to render the create-form template for both GET
        and the POST-error re-render path. Pulls the pool /
        all_tags lists out of the manager and merges them with
        the default context.
    """
    pools = resource_manager.list_pools(auth.user_id).pools
    all_tags = resource_manager.list_tags().tags

    flashes = flash.consume_flashes(session=auth.session)
    context = _build_default_template_context(
        session=auth.session,
        request_endpoint="resources.resource_create",
        flashes=flashes,
        csrf_token=auth.csrf_token,
    )
    context.update(_resources_permission_flags(auth=auth))
    context["pools"] = pools
    context["all_tags"] = all_tags
    context["form_data"] = form_data
    response = _render(
        template_name="resources/resources/create.html",
        context=context,
        status_code=status_code,
    )
    _attach_session_to_response(
        response=response, session=auth.session
    )
    return response


def handle_resource_create(request: Request) -> Response:
    """
        ``GET /resources/create`` / ``POST /resources/create``.
        Admin-gated; checkout is on the detail page.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        deny_response = _require_permission_or_redirect(
            auth=auth,
            permission=_ADMIN_PERMISSION,
            deny_redirect_url=_url_for_module.url_for(
                "resources.dashboard"
            ),
        )
        if deny_response is not None:
            return deny_response

        method = request.method.upper()
        resource_manager = _build_resource_manager(db_session=db_session)

        if method == "GET":
            # "Add Resource" from a pool page links here with
            # ?pool_id=; pre-select that pool in the form.
            preselect: Optional[MultiFormView] = None
            requested_pool_id = request.query_params.get("pool_id", None)
            if requested_pool_id is not None and len(str(requested_pool_id)) > 0:
                preselect = MultiFormView(data={
                    "pool_id": [str(requested_pool_id)],
                    "resource_type": ["generic"],
                })
            response = _render_resource_create_form(
                auth=auth,
                resource_manager=resource_manager,
                form_data=preselect,
            )
            return response

        # POST
        single_form = _parse_form_or_empty(request=request)
        multi_form = _parse_form_multi(request=request)
        form_view = MultiFormView(data=multi_form)

        csrf_redirect = auth_guard.enforce_csrf_or_redirect(
            form=single_form,
            session=auth.session,
            fallback_url=_url_for_module.url_for(
                "resources.resource_create"
            ),
        )
        if csrf_redirect is not None:
            _attach_session_to_response(
                response=csrf_redirect, session=auth.session
            )
            return csrf_redirect

        name = str(single_form.get("name", "")).strip()
        resource_type_str = str(
            single_form.get("resource_type", "generic")
        )
        pool_id = _coerce_int(raw=single_form.get("pool_id", None))
        description = str(single_form.get("description", "")).strip()
        capacity = _coerce_int_with_default(
            raw=single_form.get("capacity", None), default=1
        )
        tags = list(multi_form.get("tags", []))
        metadata_str = str(single_form.get("metadata", "")).strip()

        try:
            metadata = _parse_metadata_json_or_default(
                raw=metadata_str, default={}
            )
            if metadata is None:
                metadata = {}
            resource_type = _resolve_resource_type(
                resource_type_str=resource_type_str
            )
            create_request = _build_resource_create_request(
                name=name,
                resource_type=resource_type,
                pool_id=pool_id,
                description=description,
                metadata=metadata,
                tags=tags,
                capacity=capacity,
            )
            created = resource_manager.create_resource(
                create_request, auth.user_id
            )
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for(
                    "resources.resource_detail",
                    resource_id=created.id,
                ),
                message='Resource "{}" created successfully.'.format(
                    name
                ),
                category=flash.CATEGORY_SUCCESS,
            )
            return response
        except ValueError as exc:
            flash.add_flash(
                session=auth.session,
                message=str(exc),
                category=flash.CATEGORY_ERROR,
            )
        except Exception as exc:
            message = _describe_resource_manager_error(exc=exc)
            if message is None:
                _LOGGER.exception("Unexpected error creating resource")
                message = (
                    "An unexpected error occurred while creating the"
                    " resource. The problem has been logged."
                )
            flash.add_flash(
                session=auth.session,
                message=message,
                category=flash.CATEGORY_ERROR,
            )

        # Re-render the form with the submitted values.
        response = _render_resource_create_form(
            auth=auth,
            resource_manager=resource_manager,
            form_data=form_view,
            status_code=400,
        )
        return response
    finally:
        try:
            db_session.close()
        except Exception:
            pass


def handle_resource_detail(request: Request) -> Response:
    """
        ``GET /resources/{resource_id}`` -- detail page including
        the active allocation list for the resource.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        resource_id = _coerce_int(
            raw=request.path_params.get("resource_id", None)
        )
        if resource_id is None:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("resources.resource_list"),
                message="Resource not found.",
                category=flash.CATEGORY_ERROR,
            )
            return response

        resource_manager = _build_resource_manager(db_session=db_session)
        resource = resource_manager.get_resource(resource_id)
        if resource is None:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("resources.resource_list"),
                message="Resource not found.",
                category=flash.CATEGORY_ERROR,
            )
            return response

        allocation_manager = _build_allocation_manager(
            db_session=db_session
        )
        active_allocations = allocation_manager.get_active_allocations(
            resource_id
        )
        upcoming_reservations = allocation_manager.list_reservations(
            resource_id=resource_id, status="pending", limit=20
        ).reservations

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="resources.resource_detail",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context.update(_resources_permission_flags(auth=auth))
        context["resource"] = resource
        context["active_allocations"] = active_allocations
        context["upcoming_reservations"] = upcoming_reservations
        response = _render(
            template_name="resources/resources/detail.html",
            context=context,
        )
        _attach_session_to_response(
            response=response, session=auth.session
        )
        return response
    finally:
        try:
            db_session.close()
        except Exception:
            pass


def handle_resource_edit(request: Request) -> Response:
    """
        ``GET /resources/{resource_id}/edit`` /
        ``POST /resources/{resource_id}/edit``. Admin-gated.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        deny_response = _require_permission_or_redirect(
            auth=auth,
            permission=_ADMIN_PERMISSION,
            deny_redirect_url=_url_for_module.url_for(
                "resources.dashboard"
            ),
        )
        if deny_response is not None:
            return deny_response

        resource_id = _coerce_int(
            raw=request.path_params.get("resource_id", None)
        )
        if resource_id is None:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("resources.resource_list"),
                message="Resource not found.",
                category=flash.CATEGORY_ERROR,
            )
            return response

        resource_manager = _build_resource_manager(db_session=db_session)
        resource = resource_manager.get_resource(resource_id)
        if resource is None:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("resources.resource_list"),
                message="Resource not found.",
                category=flash.CATEGORY_ERROR,
            )
            return response

        method = request.method.upper()
        form_view: Optional[MultiFormView] = None

        if method == "POST":
            single_form = _parse_form_or_empty(request=request)
            multi_form = _parse_form_multi(request=request)
            form_view = MultiFormView(data=multi_form)

            csrf_redirect = auth_guard.enforce_csrf_or_redirect(
                form=single_form,
                session=auth.session,
                fallback_url=_url_for_module.url_for(
                    "resources.resource_edit",
                    resource_id=resource_id,
                ),
            )
            if csrf_redirect is not None:
                _attach_session_to_response(
                    response=csrf_redirect, session=auth.session
                )
                return csrf_redirect

            # A field the form submitted is an explicit value even when
            # it is empty: clearing the description, unticking every
            # tag or emptying the metadata saves exactly that. Only a
            # field the form did not send at all means "no change".
            description: Optional[str] = None
            if "description" in multi_form:
                description = str(
                    single_form.get("description", "")
                ).strip()
            capacity_raw: Optional[str] = None
            if "capacity" in multi_form:
                capacity_raw = str(
                    single_form.get("capacity", "")
                ).strip()
            # Unticked checkboxes are not submitted, so the form sends a
            # ``tags_present`` marker whenever it shows the tag list; with
            # the marker and no ``tags`` the resource ends up untagged.
            tags: Optional[List[str]] = None
            if "tags_present" in multi_form or "tags" in multi_form:
                tags = list(multi_form.get("tags", []))
            metadata_str: Optional[str] = None
            if "metadata" in multi_form:
                metadata_str = str(single_form.get("metadata", "")).strip()

            try:
                capacity: Optional[int] = None
                if capacity_raw is not None:
                    capacity = _coerce_int(raw=capacity_raw)
                    if capacity is None or capacity < 1:
                        raise ValueError(
                            "Capacity must be a whole number of at least 1."
                        )
                metadata: Optional[Dict[str, Any]] = None
                if metadata_str is not None:
                    metadata = _parse_metadata_json_or_default(
                        raw=metadata_str, default={}
                    )
                # Health status is deliberately NOT editable here:
                # status changes must go through the health page,
                # which records a reason in the audit trail.
                update_request = _build_resource_update_request(
                    description=description,
                    metadata=metadata,
                    tags=tags,
                    capacity=capacity,
                    health_status=None,
                )
                resource_manager.update_resource(
                    resource_id, update_request, auth.user_id
                )
                response = _redirect_with_flash(
                    session=auth.session,
                    url=_url_for_module.url_for(
                        "resources.resource_detail",
                        resource_id=resource_id,
                    ),
                    message="Resource updated successfully.",
                    category=flash.CATEGORY_SUCCESS,
                )
                return response
            except ValueError as exc:
                flash.add_flash(
                    session=auth.session,
                    message=str(exc),
                    category=flash.CATEGORY_ERROR,
                )
            except Exception as exc:
                message = _describe_resource_manager_error(exc=exc)
                if message is None:
                    _LOGGER.exception(
                        "Unexpected error updating resource %s",
                        resource_id,
                    )
                    message = (
                        "An unexpected error occurred while updating"
                        " the resource. The problem has been logged."
                    )
                flash.add_flash(
                    session=auth.session,
                    message=message,
                    category=flash.CATEGORY_ERROR,
                )

        # GET, or POST that fell through. Re-render the edit form
        # -- with the submitted values (``form_data``) when a POST
        # failed, so typed input is never reverted to the DB state.
        pools = resource_manager.list_pools(auth.user_id).pools
        all_tags = resource_manager.list_tags().tags

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="resources.resource_edit",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context.update(_resources_permission_flags(auth=auth))
        context["resource"] = resource
        context["pools"] = pools
        context["all_tags"] = all_tags
        context["form_data"] = form_view
        response = _render(
            template_name="resources/resources/edit.html",
            context=context,
        )
        _attach_session_to_response(
            response=response, session=auth.session
        )
        return response
    finally:
        try:
            db_session.close()
        except Exception:
            pass


def handle_resource_delete(request: Request) -> Response:
    """
        ``POST /resources/{resource_id}/delete``. Admin-gated.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        deny_response = _require_permission_or_redirect(
            auth=auth,
            permission=_ADMIN_PERMISSION,
            deny_redirect_url=_url_for_module.url_for(
                "resources.dashboard"
            ),
        )
        if deny_response is not None:
            return deny_response

        resource_id = _coerce_int(
            raw=request.path_params.get("resource_id", None)
        )
        single_form = _parse_form_or_empty(request=request)

        csrf_redirect = auth_guard.enforce_csrf_or_redirect(
            form=single_form,
            session=auth.session,
            fallback_url=_url_for_module.url_for(
                "resources.resource_list"
            ),
        )
        if csrf_redirect is not None:
            _attach_session_to_response(
                response=csrf_redirect, session=auth.session
            )
            return csrf_redirect

        if resource_id is None:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("resources.resource_list"),
                message="Resource not found.",
                category=flash.CATEGORY_ERROR,
            )
            return response

        resource_manager = _build_resource_manager(db_session=db_session)
        try:
            resource_manager.delete_resource(resource_id, auth.user_id)
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("resources.resource_list"),
                message="Resource deleted successfully.",
                category=flash.CATEGORY_SUCCESS,
            )
            return response
        except Exception as exc:
            message = _describe_resource_manager_error(exc=exc)
            if message is None:
                _LOGGER.exception(
                    "Unexpected error deleting resource %s", resource_id
                )
                message = (
                    "An unexpected error occurred while deleting the"
                    " resource. The problem has been logged."
                )
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("resources.resource_list"),
                message=message,
                category=flash.CATEGORY_ERROR,
            )
            return response
    finally:
        try:
            db_session.close()
        except Exception:
            pass


def handle_resource_checkout(request: Request) -> Response:
    """
        ``POST /resources/{resource_id}/checkout``. Login-gated
        (no admin requirement -- any user can check out).
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        resource_id = _coerce_int(
            raw=request.path_params.get("resource_id", None)
        )
        single_form = _parse_form_or_empty(request=request)

        csrf_redirect = auth_guard.enforce_csrf_or_redirect(
            form=single_form,
            session=auth.session,
            fallback_url=_url_for_module.url_for(
                "resources.resource_list"
            ),
        )
        if csrf_redirect is not None:
            _attach_session_to_response(
                response=csrf_redirect, session=auth.session
            )
            return csrf_redirect

        if resource_id is None:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("resources.resource_list"),
                message="Resource not found.",
                category=flash.CATEGORY_ERROR,
            )
            return response

        job_id_raw = str(single_form.get("job_id", "")).strip()
        mode_str = str(single_form.get("mode", "exclusive"))
        timeout_minutes = _coerce_int(
            raw=single_form.get("timeout_minutes", None)
        )
        reason = str(single_form.get("reason", "")).strip()

        allocation_manager = _build_allocation_manager(
            db_session=db_session
        )
        try:
            mode = _resolve_allocation_mode(mode_str=mode_str)
            checkout_request = _build_checkout_request(
                resource_id=resource_id,
                job_id=job_id_raw if len(job_id_raw) > 0 else None,
                mode=mode,
                timeout_minutes=timeout_minutes,
                reason=reason,
            )
            allocation = allocation_manager.checkout(
                checkout_request, auth.user_id
            )
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for(
                    "resources.resource_detail",
                    resource_id=resource_id,
                ),
                message=(
                    "Resource checked out successfully."
                    " Allocation ID: {}".format(allocation.id)
                ),
                category=flash.CATEGORY_SUCCESS,
            )
            return response
        except Exception as exc:
            message = _describe_allocation_error(exc=exc)
            if message is None:
                _LOGGER.exception(
                    "Unexpected error checking out resource %s",
                    resource_id,
                )
                message = (
                    "An unexpected error occurred while checking out"
                    " the resource. The problem has been logged."
                )
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for(
                    "resources.resource_detail",
                    resource_id=resource_id,
                ),
                message=message,
                category=flash.CATEGORY_ERROR,
            )
            return response
    finally:
        try:
            db_session.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


_HANDLERS_BY_ENDPOINT: Dict[str, Callable[[Request], Response]] = {
    "resources.dashboard_root": handle_dashboard,
    "resources.dashboard": handle_dashboard,
    "resources.resource_list": handle_resource_list,
    "resources.resource_create": handle_resource_create,
    "resources.resource_detail": handle_resource_detail,
    "resources.resource_edit": handle_resource_edit,
    "resources.resource_delete": handle_resource_delete,
    "resources.resource_checkout": handle_resource_checkout,
}


def register_resources_routes(*, app: Any) -> None:
    """
        Attach the E1 resources core routes to a webworks app
        and register their endpoint names with the url_for shim.

        Also pre-registers the URL patterns for E2/E3/E4
        endpoints so the dashboard sidebar template's
        ``url_for('resources.pool_list')`` / ``ip_pool_list`` /
        ``allocation_list`` / ``reservation_list`` /
        ``health_dashboard`` / ``tag_list`` calls all resolve
        before those handlers ship.

        :param app: WebWorks application built by
                    ``establish_webapp_persona``.

        :returns: None.
    """
    for endpoint_name, relative_path, methods in _ROUTE_TABLE:
        full_path = RESOURCES_PATH + relative_path
        if full_path.endswith("/") and full_path != "/":
            full_path = (
                RESOURCES_PATH if relative_path == "/" else full_path
            )

        _url_for_module.register_endpoint(
            endpoint=endpoint_name, pattern=full_path
        )
        handler = _HANDLERS_BY_ENDPOINT[endpoint_name]
        wrapped_handler = _wrap_resources_handler_in_shell(handler)
        app.attach_route(full_path, methods=list(methods))(wrapped_handler)
    for endpoint_name, relative_path in _FUTURE_ENDPOINT_PATTERNS:
        full_path = RESOURCES_PATH + relative_path
        _url_for_module.register_endpoint(
            endpoint=endpoint_name, pattern=full_path
        )

    # E2 features -- pools + ip pools. Lazy-imported so this
    # module remains importable when a per-feature module fails
    # to load (matches the config/routes.py register_*_routes
    # dispatch pattern from D2-D4).
    from ccai.pychestrate.webservice.webinterface.blueprints.resources.routes_pools import (  # noqa: E402
        register_pools_routes,
    )
    from ccai.pychestrate.webservice.webinterface.blueprints.resources.routes_ip_pools import (  # noqa: E402
        register_ip_pools_routes,
    )
    register_pools_routes(app=app)
    register_ip_pools_routes(app=app)

    # E3 features -- allocations + reservations.
    from ccai.pychestrate.webservice.webinterface.blueprints.resources.routes_allocations import (  # noqa: E402
        register_allocations_routes,
    )
    from ccai.pychestrate.webservice.webinterface.blueprints.resources.routes_reservations import (  # noqa: E402
        register_reservations_routes,
    )
    register_allocations_routes(app=app)
    register_reservations_routes(app=app)

    # E4 features -- health + tags.
    from ccai.pychestrate.webservice.webinterface.blueprints.resources.routes_health import (  # noqa: E402
        register_health_routes,
    )
    from ccai.pychestrate.webservice.webinterface.blueprints.resources.routes_tags import (  # noqa: E402
        register_tags_routes,
    )
    register_health_routes(app=app)
    register_tags_routes(app=app)

    return


__all__ = [
    "RESOURCES_PATH",
    "register_resources_routes",
    "handle_dashboard",
    "handle_resource_list",
    "handle_resource_create",
    "handle_resource_detail",
    "handle_resource_edit",
    "handle_resource_delete",
    "handle_resource_checkout",
]
