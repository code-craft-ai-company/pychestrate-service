"""
.. module:: webinterface.blueprints.resources.routes_allocations
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-native consumer-facing UI for /resources/allocations
               (E3 slice -- allocation viewing + checkin).

.. moduleauthor:: Code Craft AI LLC

The five allocation routes served under the resources
blueprint:

* ``GET  /resources/allocations``                                 -- active
                                                                     allocations
                                                                     list
                                                                     with
                                                                     resource /
                                                                     user /
                                                                     job_id
                                                                     filters.
* ``GET  /resources/allocations/history``                         -- historical
                                                                     allocations
                                                                     with
                                                                     ISO-date
                                                                     filters.
* ``GET  /resources/allocations/{allocation_id}``                 -- detail
                                                                     page.
* ``POST /resources/allocations/{allocation_id}/checkin``         -- check
                                                                     in
                                                                     (login
                                                                     only).
* ``POST /resources/allocations/{allocation_id}/force-checkin``   -- admin-
                                                                     only
                                                                     force
                                                                     checkin
                                                                     with a
                                                                     reason.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import logging

from datetime import datetime, timedelta, timezone
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
    _attach_session_to_response,
    _build_default_template_context,
    _parse_form_or_empty,
    _not_found_redirect,
    _redirect_with_flash,
    _render,
    _require_permission_or_redirect,
    _resolve_authenticated_request,
)
from ccai.pychestrate.webservice.webinterface.blueprints.resources import exports, utilization
from ccai.pychestrate.webservice.webinterface.blueprints.resources.routes import (
    RESOURCES_MAX_PER_PAGE,
    RESOURCES_PATH,
    _denial_message,
    _resources_permission_flags,
    _wrap_resources_handler_in_shell,
    _build_page_window,
    _calculate_total_pages,
    _describe_allocation_error,
)


_LOGGER = logging.getLogger("pychestrate.ui.resources.allocations")


# Upper bound for the resource-filter dropdown source list. When
# more resources exist than this, the templates render a visible
# "Showing first N of M" note instead of silently truncating.
_RESOURCE_SELECTOR_LIMIT = 1000


_ROUTE_TABLE = (
    ("resources.allocation_list", "/allocations", ("GET",)),
    (
        "resources.allocation_history",
        "/allocations/history",
        ("GET",),
    ),
    # Before the ``{allocation_id}`` route, so "utilization" is not read as an id.
    (
        "resources.allocation_utilization",
        "/allocations/utilization",
        ("GET",),
    ),
    (
        "resources.allocation_detail",
        "/allocations/{allocation_id}",
        ("GET",),
    ),
    (
        "resources.allocation_checkin",
        "/allocations/{allocation_id}/checkin",
        ("POST",),
    ),
    (
        "resources.allocation_force_checkin",
        "/allocations/{allocation_id}/force-checkin",
        ("POST",),
    ),
)


_ADMIN_PERMISSION = "system:resources.manage"

_READ_PERMISSION = "system:resources.read"

#: The most resources, and the most allocations, one utilization report reads. A report that hit a
#: limit says so on the page; the figures for the busiest resources may then be low.
_UTILIZATION_RESOURCE_LIMIT = 1000
_UTILIZATION_ALLOCATION_LIMIT = 50000


# ---------------------------------------------------------------------------
# Lazy-import builder seams (test-patchable; defined locally per
# the E2 lesson on cross-module ``from .routes import _build_*``
# bindings)
# ---------------------------------------------------------------------------


def _build_allocation_manager(*, db_session: Any) -> Any:
    """
        Construct an :class:`AllocationManager`. Lazy-imports.
    """
    from ccai.pychestrate.core.managers.allocation_manager import (  # noqa: E402
        AllocationManager,
    )
    rtnval = AllocationManager(db_session)
    return rtnval


def _build_resource_manager(*, db_session: Any) -> Any:
    """
        Construct a :class:`ResourceManager`. Lazy-imports.
    """
    from ccai.pychestrate.core.managers.resource_manager import (  # noqa: E402
        ResourceManager,
    )
    rtnval = ResourceManager(db_session)
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


def _parse_iso_datetime_or_none(*, raw: Optional[str]) -> Optional[datetime]:
    """
        Parse an ISO-8601 datetime string. Returns ``None`` on
        bad input rather than raising -- matches the legacy
        try/except ValueError -> pass behavior.
    """
    if raw is None or len(raw) == 0:
        return None
    try:
        rtnval = datetime.fromisoformat(raw)
        return rtnval
    except (TypeError, ValueError):
        return None


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
    if per_page > RESOURCES_MAX_PER_PAGE:
        per_page = RESOURCES_MAX_PER_PAGE
    rtnval = {"page": page, "per_page": per_page}
    return rtnval


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def handle_allocation_list(request: Request) -> Response:
    """
        ``GET /resources/allocations`` -- active allocations.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        params = _parse_pagination_params(request=request)
        offset = (params["page"] - 1) * params["per_page"]

        resource_id = _coerce_int(
            raw=request.query_params.get("resource_id", None)
        )
        user_id = _coerce_int(
            raw=request.query_params.get("user_id", None)
        )
        job_id = (
            request.query_params.get("job_id", "") or ""
        ).strip()

        filter_kwargs: Dict[str, Any] = {
            "status": "active",
            "offset": offset,
            "limit": params["per_page"],
        }
        if resource_id is not None:
            filter_kwargs["resource_id"] = resource_id
        if user_id is not None:
            filter_kwargs["user_id"] = user_id
        if len(job_id) > 0:
            filter_kwargs["job_id"] = job_id

        allocation_manager = _build_allocation_manager(
            db_session=db_session
        )
        resource_manager = _build_resource_manager(db_session=db_session)
        allocations_response = allocation_manager.list_allocations(
            **filter_kwargs
        )
        allocations = allocations_response.allocations
        resources_response = resource_manager.list_resources(
            limit=_RESOURCE_SELECTOR_LIMIT
        )
        resources = resources_response.resources

        total_pages = _calculate_total_pages(
            total=allocations_response.total,
            per_page=params["per_page"],
        )
        page_window = _build_page_window(
            page=params["page"], total_pages=total_pages
        )
        filters_active = (
            resource_id is not None
            or user_id is not None
            or len(job_id) > 0
        )

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="resources.allocation_list",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context.update(_resources_permission_flags(auth=auth))
        context["current_user_id"] = auth.user_id
        context["allocations"] = allocations
        context["resources"] = resources
        context["resource_total"] = resources_response.total
        context["page"] = params["page"]
        context["per_page"] = params["per_page"]
        context["total_pages"] = total_pages
        context["total"] = allocations_response.total
        context["page_window"] = page_window
        context["filters_active"] = filters_active
        context["selected_resource_id"] = resource_id
        context["selected_user_id"] = user_id
        context["selected_job_id"] = job_id

        response = _render(
            template_name="resources/allocations/list.html",
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


def _load_utilization_inputs(*, db_session: Any, window_start: Any, window_end: Any) -> Dict[str, Any]:
    """
        Read what the utilization report needs: the resources, and the allocations that overlap the
        period (checked out before its end and not checked in before its start).

        :param db_session: Open SQLAlchemy session.
        :param window_start: Start of the period (UTC).
        :param window_end: End of the period (UTC).

        :returns: ``{"resources": [ResourceRef], "spans": [AllocationSpan], "notes": [str]}``; ``notes`` names
                  each limit that cut the data short.
    """
    from sqlalchemy import or_  # noqa: E402

    from ccai.pychestrate.core.orm import Allocation, Resource  # noqa: E402

    resource_rows = db_session.query(Resource).order_by(Resource.name).limit(_UTILIZATION_RESOURCE_LIMIT + 1).all()
    allocation_rows = (
        db_session.query(Allocation)
        .filter(Allocation.checkout_time <= window_end)
        .filter(or_(Allocation.actual_checkin.is_(None), Allocation.actual_checkin >= window_start))
        .order_by(Allocation.checkout_time.desc())
        .limit(_UTILIZATION_ALLOCATION_LIMIT + 1)
        .all()
    )
    notes: List[str] = []
    if len(resource_rows) > _UTILIZATION_RESOURCE_LIMIT:
        resource_rows = resource_rows[:_UTILIZATION_RESOURCE_LIMIT]
        notes.append("Showing the first {} resources.".format(_UTILIZATION_RESOURCE_LIMIT))
    if len(allocation_rows) > _UTILIZATION_ALLOCATION_LIMIT:
        allocation_rows = allocation_rows[:_UTILIZATION_ALLOCATION_LIMIT]
        notes.append(
            "Only the latest {} allocations in this period were read, so the figures for the busiest resources may be low.".format(
                _UTILIZATION_ALLOCATION_LIMIT
            )
        )
    resources = [
        utilization.ResourceRef(
            resource_id=row.id, name=str(row.name), pool=str(row.pool.name) if getattr(row, "pool", None) is not None else "",
        )
        for row in resource_rows
    ]
    spans = [
        utilization.AllocationSpan(
            resource_id=row.resource_id, checkout_time=row.checkout_time, actual_checkin=row.actual_checkin,
            expected_checkin=row.expected_checkin, status=str(row.status),
        )
        for row in allocation_rows
    ]
    return {"resources": resources, "spans": spans, "notes": notes}


def handle_allocation_utilization(request: Request) -> Response:
    """
        ``GET /resources/allocations/utilization`` -- how long each resource was in use over the last
        7, 30, 90 or 365 days (``?days=``, 30 by default), or the same as a spreadsheet with
        ``?format=csv`` (ORG-F22).
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        deny_response = _require_permission_or_redirect(
            auth=auth,
            permission=_READ_PERMISSION,
            deny_message=_denial_message(action="see resource utilization"),
            deny_redirect_url=_url_for_module.url_for("resources.dashboard"),
        )
        if deny_response is not None:
            return deny_response

        period_days = utilization.parse_period_days(request.query_params.get("days", None))
        window_end = datetime.now(timezone.utc)
        inputs = _load_utilization_inputs(
            db_session=db_session, window_start=window_end - timedelta(days=period_days), window_end=window_end,
        )
        report = utilization.compute_utilization(
            resources=inputs["resources"], spans=inputs["spans"], period_days=period_days, now=window_end,
        )

        if (request.query_params.get("format", "") or "").strip().lower() == "csv":
            from ccai.pychestrate.webservice.csv_export import csv_response, render_csv  # noqa: E402

            stamp = window_end.strftime("%Y%m%d-%H%M")
            return csv_response(
                filename="pychestrate-utilization-{}d-{}.csv".format(period_days, stamp),
                body=render_csv(columns=utilization.EXPORT_COLUMNS, rows=utilization.export_records(report)),
                truncated=len(inputs["notes"]) > 0,
            )

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="resources.allocation_utilization",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context.update(_resources_permission_flags(auth=auth))
        context["utilization"] = report
        context["period_days"] = period_days
        context["period_choices"] = utilization.PERIOD_CHOICES
        context["truncation_notes"] = inputs["notes"]

        response = _render(
            template_name="resources/allocations/utilization.html",
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


def handle_allocation_history(request: Request) -> Response:
    """
        ``GET /resources/allocations/history`` -- historical
        allocations with ISO-date filters.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        params = _parse_pagination_params(request=request)
        offset = (params["page"] - 1) * params["per_page"]

        resource_id = _coerce_int(
            raw=request.query_params.get("resource_id", None)
        )
        user_id = _coerce_int(
            raw=request.query_params.get("user_id", None)
        )
        start_date_str = (
            request.query_params.get("start_date", "") or ""
        )
        end_date_str = (
            request.query_params.get("end_date", "") or ""
        )

        start_date = _parse_iso_datetime_or_none(raw=start_date_str)
        end_date = _parse_iso_datetime_or_none(raw=end_date_str)

        if exports.wants_csv(request.query_params.get("format", None)):
            # Every allocation the filters match, as a spreadsheet (ORG-F22), not one page of it.
            deny_response = _require_permission_or_redirect(
                auth=auth,
                permission=_READ_PERMISSION,
                deny_message=_denial_message(action="export allocation history"),
                deny_redirect_url=_url_for_module.url_for("resources.dashboard"),
            )
            if deny_response is not None:
                return deny_response
            export_manager = _build_allocation_manager(db_session=db_session)

            def _fetch_allocations(page_offset: int, page_limit: int) -> Any:
                page_response = export_manager.get_allocation_history(
                    resource_id=resource_id, user_id=user_id, start_date=start_date, end_date=end_date,
                    offset=page_offset, limit=page_limit,
                )
                return page_response.allocations, page_response.total

            export_rows, export_truncated = exports.collect_rows(_fetch_allocations)
            return exports.csv_download(
                base_name="allocation-history", columns=exports.ALLOCATION_COLUMNS,
                records=exports.allocation_records(export_rows), truncated=export_truncated,
            )

        allocation_manager = _build_allocation_manager(
            db_session=db_session
        )
        resource_manager = _build_resource_manager(db_session=db_session)

        allocations_response = allocation_manager.get_allocation_history(
            resource_id=resource_id,
            user_id=user_id,
            start_date=start_date,
            end_date=end_date,
            offset=offset,
            limit=params["per_page"],
        )
        allocations = allocations_response.allocations
        resources_response = resource_manager.list_resources(
            limit=_RESOURCE_SELECTOR_LIMIT
        )
        resources = resources_response.resources

        total_pages = _calculate_total_pages(
            total=allocations_response.total,
            per_page=params["per_page"],
        )
        page_window = _build_page_window(
            page=params["page"], total_pages=total_pages
        )
        filters_active = (
            resource_id is not None
            or user_id is not None
            or start_date is not None
            or end_date is not None
        )

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="resources.allocation_history",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["csv_url"] = exports.export_url(
            RESOURCES_PATH + "/allocations/history",
            [("resource_id", resource_id), ("user_id", user_id), ("start_date", start_date_str), ("end_date", end_date_str)],
        )
        context.update(_resources_permission_flags(auth=auth))
        context["allocations"] = allocations
        context["resources"] = resources
        context["resource_total"] = resources_response.total
        context["page"] = params["page"]
        context["per_page"] = params["per_page"]
        context["total_pages"] = total_pages
        context["total"] = allocations_response.total
        context["page_window"] = page_window
        context["filters_active"] = filters_active
        context["selected_resource_id"] = resource_id
        context["selected_user_id"] = user_id
        context["start_date"] = start_date_str
        context["end_date"] = end_date_str

        response = _render(
            template_name="resources/allocations/history.html",
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


def handle_allocation_detail(request: Request) -> Response:
    """
        ``GET /resources/allocations/{allocation_id}``.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        allocation_id = _coerce_int(
            raw=request.path_params.get("allocation_id", None)
        )
        if allocation_id is None:
            response = _not_found_redirect(
                session=auth.session,
                url=_url_for_module.url_for(
                    "resources.allocation_list"
                ),
                message="Allocation not found.",
            )
            return response

        allocation_manager = _build_allocation_manager(
            db_session=db_session
        )
        allocation = allocation_manager.get_allocation(allocation_id)
        if allocation is None:
            response = _not_found_redirect(
                session=auth.session,
                url=_url_for_module.url_for(
                    "resources.allocation_list"
                ),
                message="Allocation not found.",
            )
            return response

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="resources.allocation_detail",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context.update(_resources_permission_flags(auth=auth))
        context["current_user_id"] = auth.user_id
        context["allocation"] = allocation
        response = _render(
            template_name="resources/allocations/detail.html",
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


def handle_allocation_checkin(request: Request) -> Response:
    """
        ``POST /resources/allocations/{allocation_id}/checkin``
        (login-only -- the checkin grant is implicit in the
        original allocator).
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        allocation_id = _coerce_int(
            raw=request.path_params.get("allocation_id", None)
        )
        single_form = _parse_form_or_empty(request=request)

        csrf_redirect = auth_guard.enforce_csrf_or_redirect(
            form=single_form,
            session=auth.session,
            fallback_url=_url_for_module.url_for(
                "resources.allocation_list"
            ),
        )
        if csrf_redirect is not None:
            _attach_session_to_response(
                response=csrf_redirect, session=auth.session
            )
            return csrf_redirect

        if allocation_id is None:
            response = _not_found_redirect(
                session=auth.session,
                url=_url_for_module.url_for(
                    "resources.allocation_list"
                ),
                message="Allocation not found.",
            )
            return response

        allocation_manager = _build_allocation_manager(
            db_session=db_session
        )
        try:
            allocation_manager.checkin(allocation_id, auth.user_id)
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for(
                    "resources.allocation_list"
                ),
                message="Resource checked in successfully.",
                category=flash.CATEGORY_SUCCESS,
            )
            return response
        except Exception as exc:
            message = _describe_allocation_error(exc=exc)
            if message is None:
                _LOGGER.exception(
                    "Unexpected error checking in allocation %s",
                    allocation_id,
                )
                message = (
                    "An unexpected error occurred while checking in"
                    " the resource. The problem has been logged."
                )
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for(
                    "resources.allocation_list"
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


def handle_allocation_force_checkin(request: Request) -> Response:
    """
        ``POST /resources/allocations/{allocation_id}/force-checkin``
        (admin-gated). Mirrors the legacy admin-required +
        ``reason`` form-field shape.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        deny_response = _require_permission_or_redirect(
            auth=auth,
            permission=_ADMIN_PERMISSION,
            deny_message=_denial_message(action="force check in someone else's allocation"),
            deny_redirect_url=_url_for_module.url_for(
                "resources.dashboard"
            ),
        )
        if deny_response is not None:
            return deny_response

        allocation_id = _coerce_int(
            raw=request.path_params.get("allocation_id", None)
        )
        single_form = _parse_form_or_empty(request=request)

        csrf_redirect = auth_guard.enforce_csrf_or_redirect(
            form=single_form,
            session=auth.session,
            fallback_url=_url_for_module.url_for(
                "resources.allocation_list"
            ),
        )
        if csrf_redirect is not None:
            _attach_session_to_response(
                response=csrf_redirect, session=auth.session
            )
            return csrf_redirect

        if allocation_id is None:
            response = _not_found_redirect(
                session=auth.session,
                url=_url_for_module.url_for(
                    "resources.allocation_list"
                ),
                message="Allocation not found.",
            )
            return response

        reason = str(
            single_form.get("reason", "Administrative force checkin")
        )

        allocation_manager = _build_allocation_manager(
            db_session=db_session
        )
        try:
            allocation_manager.force_checkin(
                allocation_id, auth.user_id, reason
            )
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for(
                    "resources.allocation_list"
                ),
                message="Resource force checked in successfully.",
                category=flash.CATEGORY_SUCCESS,
            )
            return response
        except Exception as exc:
            message = _describe_allocation_error(exc=exc)
            if message is None:
                _LOGGER.exception(
                    "Unexpected error force checking in allocation %s",
                    allocation_id,
                )
                message = (
                    "An unexpected error occurred while force checking"
                    " in the resource. The problem has been logged."
                )
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for(
                    "resources.allocation_list"
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
    "resources.allocation_list": handle_allocation_list,
    "resources.allocation_history": handle_allocation_history,
    "resources.allocation_utilization": handle_allocation_utilization,
    "resources.allocation_detail": handle_allocation_detail,
    "resources.allocation_checkin": handle_allocation_checkin,
    "resources.allocation_force_checkin": handle_allocation_force_checkin,
}


def register_allocations_routes(*, app: Any) -> None:
    """
        Attach the allocation routes to a webworks app and
        register their endpoint names with the url_for shim.
    """
    for endpoint_name, relative_path, methods in _ROUTE_TABLE:
        full_path = RESOURCES_PATH + relative_path
        _url_for_module.register_endpoint(
            endpoint=endpoint_name, pattern=full_path
        )
        handler = _HANDLERS_BY_ENDPOINT[endpoint_name]
        wrapped_handler = _wrap_resources_handler_in_shell(handler)
        app.attach_route(full_path, methods=list(methods))(wrapped_handler)
    return


__all__ = [
    "register_allocations_routes",
    "handle_allocation_list",
    "handle_allocation_history",
    "handle_allocation_utilization",
    "handle_allocation_detail",
    "handle_allocation_checkin",
    "handle_allocation_force_checkin",
]
