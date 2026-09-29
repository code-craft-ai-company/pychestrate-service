"""
.. module:: webinterface.blueprints.projects.routes_calendar
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-native consumer-facing UI for /projects/*/calendar
               (F5 slice -- read-only release-event calendar).

.. moduleauthor:: Code Craft AI LLC

The three calendar routes served under the projects blueprint.
All read-only -- release-event lifecycle
runs through the build pipeline + REST API, not the consumer UI.

* ``GET /projects/{project_id}/calendar``
        -- month-window calendar view.
* ``GET /projects/{project_id}/calendar/events``
        -- paginated release-event list.
* ``GET /projects/{project_id}/calendar/events/{event_id}``
        -- release-event detail with phases / branches /
        merge-events / pull-events.

The endpoint names ``projects.release_event_list`` and
``projects.release_event_detail`` are kept for template
compatibility (the existing templates use those names; the
endpoint name is unrelated to the URL path).
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import calendar as calendar_util

from datetime import date, datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

from ccai.webworks.routing.request import Request
from ccai.webworks.routing.response import (
    HTMLResponse,
    RedirectResponse,
    Response,
)

from ccai.pychestrate.webservice.webinterface.foundation import (
    flash,
    url_for as _url_for_module,
)
from ccai.pychestrate.webservice.webinterface.blueprints.config.routes import (
    _AuthResolution,
    _attach_session_to_response,
    _build_default_template_context,
    _redirect_with_flash,
    _render,
    _resolve_authenticated_request,
)
from ccai.pychestrate.webservice.webinterface.blueprints.projects.routes import (
    PROJECTS_PATH,
    _require_project_permission_or_redirect,
    _resolve_project_or_redirect,
)


_ROUTE_TABLE = (
    (
        "projects.calendar_view",
        "/{project_id}/calendar",
        ("GET",),
    ),
    (
        "projects.release_event_list",
        "/{project_id}/calendar/events",
        ("GET",),
    ),
    (
        "projects.release_event_detail",
        "/{project_id}/calendar/events/{event_id}",
        ("GET",),
    ),
)


# ---------------------------------------------------------------------------
# Lazy-import builder seams (defined locally per the E2 lesson -- never
# import a builder from another per-feature module, otherwise mock patches
# to one module freeze the binding in the other module forever).
# ---------------------------------------------------------------------------


def _build_project_manager(*, db_session: Any) -> Any:
    from ccai.pychestrate.webservice.webinterface.blueprints.projects.project_access import (  # noqa: E402
        build_access_aware_project_manager,
    )
    rtnval = build_access_aware_project_manager(db_session=db_session)
    return rtnval


def _build_release_manager(*, db_session: Any) -> Any:
    from ccai.pychestrate.core.managers.release_manager import (  # noqa: E402
        ReleaseManager,
    )
    rtnval = ReleaseManager(db_session)
    return rtnval


# ---------------------------------------------------------------------------
# Local helpers (mirror the F4 pattern)
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
        *, request: Request, default_per_page: int = 20
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


def _total_pages_from_count(*, total: int, per_page: int) -> int:
    """
        Compute the real page count from a list response's
        ``total`` field.

        :param total: Total matching rows reported by the manager.
        :param per_page: Page size.

        :returns: Number of pages (at least 1).
    """
    if total is None:
        return 1
    if total <= 0:
        return 1
    rtnval = (total + per_page - 1) // per_page
    return rtnval


def _parse_iso_datetime(*, raw: Any) -> Optional[datetime]:
    """
        Best-effort ISO parser for the ``start_date`` / ``end_date``
        query params on the calendar view. Returns ``None`` on
        malformed input rather than 500-ing.
    """
    if raw is None:
        return None
    if not isinstance(raw, str):
        return None
    if len(raw) == 0:
        return None
    try:
        rtnval = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return rtnval


def _default_calendar_window() -> Dict[str, datetime]:
    """
        Default calendar window: the current calendar month (start
        of month .. start of next month minus one second).
    """
    now = datetime.now()
    start = now.replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    # End of month -- jump 4 days into the 28th to land somewhere
    # in the next month, then back to the 1st of that month minus
    # 1 second.
    next_month = start.replace(day=28) + timedelta(days=4)
    end = (
        next_month.replace(day=1, hour=0, minute=0, second=0,
                           microsecond=0)
        - timedelta(seconds=1)
    )
    rtnval = {"start": start, "end": end}
    return rtnval


def _month_window(*, year: int, month: int) -> Dict[str, datetime]:
    """
        Calendar window covering one calendar month (start of the
        month .. last second of the month).

        :param year: Four-digit year.
        :param month: Month number 1..12.

        :returns: Dict with ``start`` and ``end`` datetimes.
    """
    start = datetime(year, month, 1)
    last_day = calendar_util.monthrange(year, month)[1]
    end = datetime(year, month, last_day, 23, 59, 59)
    rtnval = {"start": start, "end": end}
    return rtnval


# Maps the manager's ``event_type`` values onto the short CSS
# suffixes the calendar template styles (``.event-release`` /
# ``.event-merge`` / ``.event-pull``).
_EVENT_TYPE_CSS_SUFFIXES: Dict[str, str] = {
    "release_event": "release",
    "merge_event": "merge",
    "pull_event": "pull",
}


def _build_calendar_days(
        *, year: int, month: int, events: List[Any]
    ) -> List[Dict[str, Any]]:
    """
        Build the flat list of day cells the calendar grid
        template iterates. Weeks run Sunday..Saturday to match
        the template's header row; leading/trailing days from the
        adjacent months are flagged ``other_month``.

        Each cell dict carries ``day`` / ``other_month`` /
        ``is_today`` / ``events``; each event entry carries
        ``event_type`` (short CSS suffix) and ``title``.

        :param year: Grid year.
        :param month: Grid month 1..12.
        :param events: Calendar event rows from
                       :meth:`ReleaseManager.get_calendar_events`.

        :returns: Flat list of day-cell dicts (multiple of 7).
    """
    month_grid = calendar_util.Calendar(firstweekday=6)
    grid_dates: List[date] = []
    for week in month_grid.monthdatescalendar(year, month):
        grid_dates.extend(week)

    grid_start = grid_dates[0]
    grid_end = grid_dates[-1]

    events_by_date: Dict[date, List[Dict[str, Any]]] = {}
    for event in events:
        start_time = getattr(event, "start_time", None)
        if start_time is None:
            continue
        end_time = getattr(event, "end_time", None)
        if end_time is None:
            end_time = start_time

        if isinstance(start_time, datetime):
            span_start = start_time.date()
        else:
            span_start = start_time
        if isinstance(end_time, datetime):
            span_end = end_time.date()
        else:
            span_end = end_time

        if span_end < grid_start:
            continue
        if span_start > grid_end:
            continue
        if span_start < grid_start:
            span_start = grid_start
        if span_end > grid_end:
            span_end = grid_end

        raw_type = str(getattr(event, "event_type", ""))
        css_suffix = _EVENT_TYPE_CSS_SUFFIXES.get(
            raw_type, "release"
        )
        entry_template = {
            "event_type": css_suffix,
            "title": getattr(event, "name", ""),
        }

        current = span_start
        while current <= span_end:
            day_events = events_by_date.setdefault(current, [])
            day_events.append(dict(entry_template))
            current = current + timedelta(days=1)

    today = date.today()
    rtnval: List[Dict[str, Any]] = []
    for day_date in grid_dates:
        cell = {
            "day": day_date.day,
            "other_month": day_date.month != month,
            "is_today": day_date == today,
            "events": events_by_date.get(day_date, []),
        }
        rtnval.append(cell)
    return rtnval


def _resolve_view_authorized_project(
        *, request: Request, auth: _AuthResolution
    ) -> Any:
    project_id = _coerce_int(
        raw=request.path_params.get("project_id", None)
    )
    project_manager = _build_project_manager(db_session=auth.db_session)
    resolved = _resolve_project_or_redirect(
        auth=auth,
        project_manager=project_manager,
        project_id=project_id,
    )
    if isinstance(resolved, RedirectResponse):
        return (project_id, project_manager, resolved)
    project = resolved

    deny_response = _require_project_permission_or_redirect(
        project_manager=project_manager,
        auth=auth,
        project_id=project_id,
        permission="view",
        deny_redirect_url=_url_for_module.url_for(
            "projects.project_list"
        ),
        deny_message=(
            "You do not have permission to view this project."
        ),
    )
    if deny_response is not None:
        return (project_id, project_manager, deny_response)
    return (project_id, project_manager, project)


def _can_manage(
        *, project_manager: Any, project_id: int, user_id: str
    ) -> bool:
    try:
        rtnval = project_manager.check_permission(
            project_id, user_id, "developer"
        )
    except Exception:
        rtnval = False
    return rtnval


def _resolve_owned_event_or_redirect(
        *,
        auth: _AuthResolution,
        project_id: int,
        release_manager: Any,
        event_id: Optional[int]
    ) -> Any:
    """
        Look up a release event via :class:`ReleaseManager` and
        verify it belongs to the supplied project. On any failure
        returns a redirect to the calendar event list with a
        ``Release event not found.`` flash.
    """
    list_url = _url_for_module.url_for(
        "projects.release_event_list", project_id=project_id
    )
    if event_id is None:
        rtnval = _redirect_with_flash(
            session=auth.session,
            url=list_url,
            message="Release event not found.",
            category=flash.CATEGORY_ERROR,
        )
        return rtnval
    event = release_manager.get_release_event(event_id)
    if event is None:
        rtnval = _redirect_with_flash(
            session=auth.session,
            url=list_url,
            message="Release event not found.",
            category=flash.CATEGORY_ERROR,
        )
        return rtnval
    if getattr(event, "project_id", None) != project_id:
        rtnval = _redirect_with_flash(
            session=auth.session,
            url=list_url,
            message="Release event not found.",
            category=flash.CATEGORY_ERROR,
        )
        return rtnval
    return event


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def handle_calendar_view(request: Request) -> Response:
    """
        ``GET /projects/{project_id}/calendar``.

        Month-grid calendar view. ``year`` / ``month`` query
        params (used by the template's Previous / Next links)
        select the month; ``start_date`` / ``end_date`` ISO
        params are honored as an explicit window override;
        otherwise the current month is shown.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        project_id, project_manager, project_or_redirect = (
            _resolve_view_authorized_project(
                request=request, auth=auth
            )
        )
        if isinstance(project_or_redirect, RedirectResponse):
            return project_or_redirect
        project = project_or_redirect

        year_param = _coerce_int(
            raw=request.query_params.get("year", None)
        )
        month_param = _coerce_int(
            raw=request.query_params.get("month", None)
        )
        start_param = _parse_iso_datetime(
            raw=request.query_params.get("start_date", None)
        )
        end_param = _parse_iso_datetime(
            raw=request.query_params.get("end_date", None)
        )

        if (
            year_param is not None
            and month_param is not None
            and 1 <= month_param <= 12
            and 1 <= year_param <= 9999
        ):
            window = _month_window(
                year=year_param, month=month_param
            )
            start_date = window["start"]
            end_date = window["end"]
        else:
            if start_param is not None:
                start_date = start_param
            else:
                start_date = _default_calendar_window()["start"]
            if end_param is not None:
                end_date = end_param
            else:
                # If the caller supplied only start_date we still
                # extend to the end of that month.
                month_end_window = _month_window(
                    year=start_date.year, month=start_date.month
                )
                end_date = month_end_window["end"]

        grid_year = start_date.year
        grid_month = start_date.month

        release_manager = _build_release_manager(
            db_session=db_session
        )
        events_result = release_manager.get_calendar_events(
            project_id, start_date, end_date
        )
        # The manager returns a CalendarEventsResponse wrapper;
        # accept a bare list too for older callers/stubs.
        if hasattr(events_result, "events"):
            events = events_result.events
        else:
            events = events_result

        calendar_days = _build_calendar_days(
            year=grid_year, month=grid_month, events=events
        )

        if grid_month > 1:
            prev_year = grid_year
            prev_month = grid_month - 1
        else:
            prev_year = grid_year - 1
            prev_month = 12
        if grid_month < 12:
            next_year = grid_year
            next_month = grid_month + 1
        else:
            next_year = grid_year + 1
            next_month = 1

        can_manage = _can_manage(
            project_manager=project_manager,
            project_id=project_id,
            user_id=auth.user_id,
        )

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="projects.calendar_view",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["project"] = project
        context["events"] = events
        context["start_date"] = start_date
        context["end_date"] = end_date
        context["can_manage"] = can_manage
        context["calendar_days"] = calendar_days
        context["year"] = grid_year
        context["month"] = grid_month
        context["month_name"] = calendar_util.month_name[grid_month]
        context["prev_year"] = prev_year
        context["prev_month"] = prev_month
        context["next_year"] = next_year
        context["next_month"] = next_month

        response = _render(
            template_name="projects/calendar/view.html",
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


def handle_release_event_list(request: Request) -> Response:
    """
        ``GET /projects/{project_id}/calendar/events`` --
        paginated release-event list.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        project_id, project_manager, project_or_redirect = (
            _resolve_view_authorized_project(
                request=request, auth=auth
            )
        )
        if isinstance(project_or_redirect, RedirectResponse):
            return project_or_redirect
        project = project_or_redirect

        params = _parse_pagination_params(request=request)
        offset = (params["page"] - 1) * params["per_page"]

        release_manager = _build_release_manager(
            db_session=db_session
        )
        events_result = release_manager.list_release_events(
            project_id, offset=offset, limit=params["per_page"]
        )
        events = events_result.events
        can_manage = _can_manage(
            project_manager=project_manager,
            project_id=project_id,
            user_id=auth.user_id,
        )
        total_pages = _total_pages_from_count(
            total=events_result.total,
            per_page=params["per_page"],
        )

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="projects.release_event_list",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["project"] = project
        context["events"] = events
        context["can_manage"] = can_manage
        context["page"] = params["page"]
        context["per_page"] = params["per_page"]
        context["total_pages"] = total_pages
        context["total"] = events_result.total

        response = _render(
            template_name="projects/calendar/event_list.html",
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


def handle_release_event_detail(request: Request) -> Response:
    """
        ``GET /projects/{project_id}/calendar/events/{event_id}``
        -- release-event detail with phases / branches /
        merge-events / pull-events.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        project_id, project_manager, project_or_redirect = (
            _resolve_view_authorized_project(
                request=request, auth=auth
            )
        )
        if isinstance(project_or_redirect, RedirectResponse):
            return project_or_redirect
        project = project_or_redirect

        event_id = _coerce_int(
            raw=request.path_params.get("event_id", None)
        )
        release_manager = _build_release_manager(
            db_session=db_session
        )
        event_or_redirect = _resolve_owned_event_or_redirect(
            auth=auth,
            project_id=project_id,
            release_manager=release_manager,
            event_id=event_id,
        )
        if isinstance(event_or_redirect, RedirectResponse):
            return event_or_redirect
        event = event_or_redirect

        phases = release_manager.list_phase_events(event_id).phases
        branches = release_manager.list_release_branches(
            event_id
        ).branches
        merge_events = release_manager.list_merge_events(
            release_event_id=event_id
        ).events
        pull_events = release_manager.list_pull_events(
            release_event_id=event_id
        ).events
        can_manage = _can_manage(
            project_manager=project_manager,
            project_id=project_id,
            user_id=auth.user_id,
        )

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="projects.release_event_detail",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["project"] = project
        context["event"] = event
        context["phases"] = phases
        context["branches"] = branches
        context["merge_events"] = merge_events
        context["pull_events"] = pull_events
        context["can_manage"] = can_manage

        response = _render(
            template_name="projects/calendar/event_detail.html",
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


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


_HANDLERS_BY_ENDPOINT: Dict[str, Callable[[Request], Response]] = {
    "projects.calendar_view": handle_calendar_view,
    "projects.release_event_list": handle_release_event_list,
    "projects.release_event_detail": handle_release_event_detail,
}


def register_calendar_routes(*, app: Any) -> None:
    """
        Attach the F5 calendar routes to a webworks app and
        register their endpoint names with the url_for shim.
    """
    for endpoint_name, relative_path, methods in _ROUTE_TABLE:
        full_path = PROJECTS_PATH + relative_path
        _url_for_module.register_endpoint(
            endpoint=endpoint_name, pattern=full_path
        )
        handler = _HANDLERS_BY_ENDPOINT[endpoint_name]
        app.attach_route(full_path, methods=list(methods))(handler)
    return


__all__ = [
    "register_calendar_routes",
    "handle_calendar_view",
    "handle_release_event_list",
    "handle_release_event_detail",
]
