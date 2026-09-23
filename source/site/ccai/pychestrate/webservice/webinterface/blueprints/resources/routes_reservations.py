"""
.. module:: webinterface.blueprints.resources.routes_reservations
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-native consumer-facing UI for /resources/reservations
               (E3 slice -- reservation management).

.. moduleauthor:: Code Craft AI LLC

The five reservation routes served under the resources
blueprint:

* ``GET  /resources/reservations``                          -- list
                                                               with
                                                               resource +
                                                               start/end
                                                               filters.
* ``GET  /resources/reservations/create``                   -- form.
* ``POST /resources/reservations/create``                   -- create.
* ``GET  /resources/reservations/{reservation_id}``         -- detail.
* ``GET  /resources/reservations/{reservation_id}/edit``    -- form.
* ``POST /resources/reservations/{reservation_id}/edit``    -- update.
* ``POST /resources/reservations/{reservation_id}/cancel``  -- cancel.

The legacy detail / edit handlers fetch the target reservation
via ``list_reservations(limit=1000)`` and find-by-id (since the
manager exposes no direct ``get_reservation``). Ported faithfully
via :func:`_find_reservation_by_id`.

Reservation times are typed in the viewer's time zone. The create
and edit forms carry a hidden ``tz`` field that the page's script
fills with the browser's IANA zone (and, on the edit form, converts
the UTC pre-fill into that zone); the handlers read the
``datetime-local`` values in that zone and hand the manager aware
UTC datetimes. Without script the field stays empty and the form
is filled in, and read as, UTC. The zone in effect is shown beside
the inputs.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import logging
import re

from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional
from zoneinfo import ZoneInfo

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
    _parse_form_multi,
    _parse_form_or_empty,
    _redirect_with_flash,
    _render,
    _resolve_authenticated_request,
)
from ccai.pychestrate.webservice.webinterface.blueprints.resources.routes import (
    RESOURCES_PATH,
    _resources_permission_flags,
    _wrap_resources_handler_in_shell,
    _build_page_window,
    _calculate_total_pages,
    _describe_allocation_error,
)


_LOGGER = logging.getLogger("pychestrate.ui.resources.reservations")


# Upper bound for the resource-selector source list. When more
# resources exist than this, the templates render a visible
# "Showing first N of M" note plus pool/type filters so any
# resource stays reachable.
_RESOURCE_SELECTOR_LIMIT = 1000


# The zone a reservation form is read in when the page's script did
# not report the browser's zone.
_DEFAULT_ZONE_NAME = "UTC"

# Shape of an IANA zone name ("America/Los_Angeles", "Etc/GMT+8");
# anything else the browser posts is refused before it reaches
# ``ZoneInfo``.
_ZONE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_+\-]+(/[A-Za-z0-9_+\-]+){0,3}$")
_MAX_ZONE_NAME_LENGTH = 64


_ROUTE_TABLE = (
    ("resources.reservation_list", "/reservations", ("GET",)),
    (
        "resources.reservation_create",
        "/reservations/create",
        ("GET", "POST"),
    ),
    (
        "resources.reservation_detail",
        "/reservations/{reservation_id}",
        ("GET",),
    ),
    (
        "resources.reservation_edit",
        "/reservations/{reservation_id}/edit",
        ("GET", "POST"),
    ),
    (
        "resources.reservation_cancel",
        "/reservations/{reservation_id}/cancel",
        ("POST",),
    ),
)


# ---------------------------------------------------------------------------
# Lazy-import builder seams (defined locally; see E2 lesson note)
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


def _resolve_allocation_mode(*, mode_str: str) -> Any:
    """
        Resolve a ``mode`` form value to the
        :class:`AllocationMode` enum value. Raises ValueError on
        unknown.
    """
    from ccai.pychestrate.core.orm import (  # noqa: E402
        AllocationMode,
    )
    rtnval = AllocationMode(mode_str)
    return rtnval


def _build_reservation_request(
        *,
        resource_id: int,
        job_id: Optional[str],
        start_time: datetime,
        end_time: datetime,
        mode: Any,
        reason: str
    ) -> Any:
    """
        Construct a :class:`ReservationRequest`. Lazy-imports.
    """
    from ccai.pychestrate.core.managers.allocation_manager import (  # noqa: E402
        ReservationRequest,
    )
    rtnval = ReservationRequest(
        resource_id=resource_id,
        job_id=job_id,
        start_time=start_time,
        end_time=end_time,
        mode=mode,
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


def _parse_iso_datetime_or_none(*, raw: Optional[str]) -> Optional[datetime]:
    if raw is None or len(raw) == 0:
        return None
    try:
        rtnval = datetime.fromisoformat(raw)
        return rtnval
    except (TypeError, ValueError):
        return None


def _resolve_viewer_zone(*, zone_name: Optional[str]) -> Optional[Any]:
    """
        Resolve the time zone a reservation form was filled in. The
        page's script posts the browser's IANA zone in the hidden
        ``tz`` field; an empty value means the script did not run and
        the form was filled in UTC (which is what it said).

        :param zone_name: The posted ``tz`` value.

        :returns: A ``tzinfo`` for the zone, or None when the name is
                  not a zone this server knows (the caller refuses the
                  submission rather than guess).
    """
    name = str(zone_name or "").strip()
    if len(name) == 0 or name == _DEFAULT_ZONE_NAME:
        return timezone.utc
    if len(name) > _MAX_ZONE_NAME_LENGTH or _ZONE_NAME_PATTERN.match(name) is None:
        return None
    try:
        rtnval = ZoneInfo(name)
    except (KeyError, ValueError, OSError):
        # ZoneInfoNotFoundError is a KeyError.
        return None
    return rtnval


def _viewer_zone_name(*, zone_name: Optional[str]) -> str:
    """
        The zone name to show beside the inputs (and to echo in the
        hidden ``tz`` field) when a submitted form is shown again.

        :param zone_name: The posted ``tz`` value.

        :returns: The posted name when it resolves, otherwise ``UTC``.
    """
    name = str(zone_name or "").strip()
    if len(name) == 0 or _resolve_viewer_zone(zone_name=name) is None:
        return _DEFAULT_ZONE_NAME
    return name


def _parse_form_datetime(*, raw: Optional[str], zone: Any) -> Optional[datetime]:
    """
        Read a ``datetime-local`` value (``YYYY-MM-DDTHH:MM``) typed in
        ``zone`` and return that instant as an aware UTC datetime. A
        value that already carries an offset keeps it.

        :param raw: The submitted value.
        :param zone: The ``tzinfo`` the value was typed in.

        :returns: Aware UTC datetime, or None for an empty or malformed
                  value.
    """
    text = str(raw or "").strip()
    if len(text) == 0:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=zone)
    rtnval = parsed.astimezone(timezone.utc)
    return rtnval


def _unknown_zone_message(*, zone_name: Optional[str]) -> str:
    rtnval = (
        "Your browser reported the time zone \"{}\", which this server does"
        " not recognise. Enter the start and end times in UTC and submit"
        " again.".format(str(zone_name or "").strip()[:_MAX_ZONE_NAME_LENGTH])
    )
    return rtnval


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


def _find_reservation_by_id(
        *, allocation_manager: Any, reservation_id: int
    ) -> Optional[Any]:
    """
        Look up one reservation by id through the manager's
        direct getter. (An earlier version listed the first 1,000
        reservations and scanned them, which made every
        reservation past the first thousand unreachable from its
        own detail link.)

        :param allocation_manager: AllocationManager instance.
        :param reservation_id: Target id.

        :returns: The reservation response or None.
    """
    try:
        rtnval = allocation_manager.get_reservation(reservation_id)
    except Exception:
        rtnval = None
    return rtnval


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def handle_reservation_list(request: Request) -> Response:
    """
        ``GET /resources/reservations``.
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
        start_after_str = (
            request.query_params.get("start_after", "") or ""
        )
        end_before_str = (
            request.query_params.get("end_before", "") or ""
        )

        start_after = _parse_iso_datetime_or_none(raw=start_after_str)
        end_before = _parse_iso_datetime_or_none(raw=end_before_str)

        allocation_manager = _build_allocation_manager(
            db_session=db_session
        )
        resource_manager = _build_resource_manager(db_session=db_session)

        reservations_response = allocation_manager.list_reservations(
            resource_id=resource_id,
            start_after=start_after,
            end_before=end_before,
            offset=offset,
            limit=params["per_page"],
        )
        reservations = reservations_response.reservations
        resources_response = resource_manager.list_resources(
            limit=_RESOURCE_SELECTOR_LIMIT
        )
        resources = resources_response.resources

        total_pages = _calculate_total_pages(
            total=reservations_response.total,
            per_page=params["per_page"],
        )
        page_window = _build_page_window(
            page=params["page"], total_pages=total_pages
        )
        filters_active = (
            resource_id is not None
            or start_after is not None
            or end_before is not None
        )

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="resources.reservation_list",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context.update(_resources_permission_flags(auth=auth))
        context["reservations"] = reservations
        context["resources"] = resources
        context["resource_total"] = resources_response.total
        context["page"] = params["page"]
        context["per_page"] = params["per_page"]
        context["total_pages"] = total_pages
        context["page_window"] = page_window
        context["filters_active"] = filters_active
        context["selected_resource_id"] = resource_id
        context["start_after"] = start_after_str
        context["end_before"] = end_before_str

        response = _render(
            template_name="resources/reservations/list.html",
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


def _render_reservation_create_form(
        *,
        auth: Any,
        resource_manager: Any,
        form_data: Optional[MultiFormView],
        selector_pool_id: Optional[int] = None,
        selector_resource_type: Optional[str] = None,
        viewer_timezone: str = "",
        status_code: int = 200
    ) -> HTMLResponse:
    """
        Helper for both GET and POST-error re-render paths. The
        resource selector honors optional pool / type filters and
        reports the true total so the template can show a
        "Showing first N of M" note when the list is truncated --
        every resource stays reachable by refining the filters.

        ``viewer_timezone`` is the zone the form's times are in: empty
        on a fresh form (the page's script fills in the browser's
        zone), or the zone a re-rendered submission was typed in.
    """
    selector_kwargs: Dict[str, Any] = {
        "limit": _RESOURCE_SELECTOR_LIMIT,
    }
    if selector_pool_id is not None:
        selector_kwargs["pool_id"] = selector_pool_id
    if selector_resource_type is not None:
        selector_kwargs["resource_type"] = selector_resource_type

    resources_response = resource_manager.list_resources(
        **selector_kwargs
    )
    resources = resources_response.resources
    pools = resource_manager.list_pools(auth.user_id).pools

    flashes = flash.consume_flashes(session=auth.session)
    context = _build_default_template_context(
        session=auth.session,
        request_endpoint="resources.reservation_create",
        flashes=flashes,
        csrf_token=auth.csrf_token,
    )
    context.update(_resources_permission_flags(auth=auth))
    context["resources"] = resources
    context["resource_total"] = resources_response.total
    context["pools"] = pools
    context["selector_pool_id"] = selector_pool_id
    context["selector_resource_type"] = selector_resource_type
    context["form_data"] = form_data
    context["viewer_timezone"] = viewer_timezone
    response = _render(
        template_name="resources/reservations/create.html",
        context=context,
        status_code=status_code,
    )
    _attach_session_to_response(
        response=response, session=auth.session
    )
    return response


def handle_reservation_create(request: Request) -> Response:
    """
        ``GET /resources/reservations/create`` /
        ``POST /resources/reservations/create``.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        method = request.method.upper()
        allocation_manager = _build_allocation_manager(
            db_session=db_session
        )
        resource_manager = _build_resource_manager(db_session=db_session)

        # Optional resource-selector filters carried on the query
        # string (the form posts back to the same URL so they
        # survive a POST-error re-render).
        selector_pool_id = _coerce_int(
            raw=request.query_params.get("pool_id", None)
        )
        selector_resource_type = (
            request.query_params.get("resource_type", None) or None
        )

        if method == "GET":
            # The resource-list filter is a separate GET form that
            # carries only pool_id / resource_type; the reservation
            # draft is never read from (or put into) the URL. A
            # ``resource_id`` link parameter still pre-selects a
            # resource.
            form_view: Optional[MultiFormView] = None
            preselect = _coerce_int(
                raw=request.query_params.get("resource_id", None)
            )
            if preselect is not None:
                form_view = MultiFormView(data={"resource_id": [str(preselect)]})
            response = _render_reservation_create_form(
                auth=auth,
                resource_manager=resource_manager,
                form_data=form_view,
                selector_pool_id=selector_pool_id,
                selector_resource_type=selector_resource_type,
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
                "resources.reservation_create"
            ),
        )
        if csrf_redirect is not None:
            _attach_session_to_response(
                response=csrf_redirect, session=auth.session
            )
            return csrf_redirect

        resource_id = _coerce_int(
            raw=single_form.get("resource_id", None)
        )
        job_id = str(single_form.get("job_id", "")).strip()
        start_time_str = str(single_form.get("start_time", ""))
        end_time_str = str(single_form.get("end_time", ""))
        mode_str = str(single_form.get("mode", "exclusive"))
        reason = str(single_form.get("reason", "")).strip()
        zone_name = str(single_form.get("tz", "") or "")
        viewer_timezone = _viewer_zone_name(zone_name=zone_name)

        zone = _resolve_viewer_zone(zone_name=zone_name)
        if zone is None:
            flash.add_flash(
                session=auth.session,
                message=_unknown_zone_message(zone_name=zone_name),
                category=flash.CATEGORY_ERROR,
            )
            response = _render_reservation_create_form(
                auth=auth,
                resource_manager=resource_manager,
                form_data=form_view,
                selector_pool_id=selector_pool_id,
                selector_resource_type=selector_resource_type,
                viewer_timezone=viewer_timezone,
                status_code=400,
            )
            return response

        # The datetime-local values were typed in the viewer's zone;
        # the manager gets the same instants as aware UTC.
        start_time = _parse_form_datetime(raw=start_time_str, zone=zone)
        end_time = _parse_form_datetime(raw=end_time_str, zone=zone)

        if start_time is None or end_time is None:
            flash.add_flash(
                session=auth.session,
                message="Start time and end time are required.",
                category=flash.CATEGORY_ERROR,
            )
            response = _render_reservation_create_form(
                auth=auth,
                resource_manager=resource_manager,
                form_data=form_view,
                selector_pool_id=selector_pool_id,
                selector_resource_type=selector_resource_type,
                viewer_timezone=viewer_timezone,
                status_code=400,
            )
            return response

        if resource_id is None:
            flash.add_flash(
                session=auth.session,
                message="A resource must be selected.",
                category=flash.CATEGORY_ERROR,
            )
            response = _render_reservation_create_form(
                auth=auth,
                resource_manager=resource_manager,
                form_data=form_view,
                selector_pool_id=selector_pool_id,
                selector_resource_type=selector_resource_type,
                viewer_timezone=viewer_timezone,
                status_code=400,
            )
            return response

        try:
            mode = _resolve_allocation_mode(mode_str=mode_str)
            reservation_request = _build_reservation_request(
                resource_id=resource_id,
                job_id=job_id if len(job_id) > 0 else None,
                start_time=start_time,
                end_time=end_time,
                mode=mode,
                reason=reason,
            )
            reservation = allocation_manager.create_reservation(
                reservation_request, auth.user_id
            )
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for(
                    "resources.reservation_detail",
                    reservation_id=reservation.id,
                ),
                message="Reservation created.",
                category=flash.CATEGORY_SUCCESS,
            )
            return response
        except Exception as exc:
            message = _describe_allocation_error(exc=exc)
            if message is None:
                _LOGGER.exception(
                    "Unexpected error creating reservation"
                )
                message = (
                    "An unexpected error occurred while creating the"
                    " reservation. The problem has been logged."
                )
            flash.add_flash(
                session=auth.session,
                message=message,
                category=flash.CATEGORY_ERROR,
            )

        response = _render_reservation_create_form(
            auth=auth,
            resource_manager=resource_manager,
            form_data=form_view,
            selector_pool_id=selector_pool_id,
            selector_resource_type=selector_resource_type,
            viewer_timezone=viewer_timezone,
            status_code=400,
        )
        return response
    finally:
        try:
            db_session.close()
        except Exception:
            pass


def handle_reservation_detail(request: Request) -> Response:
    """
        ``GET /resources/reservations/{reservation_id}``.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        reservation_id = _coerce_int(
            raw=request.path_params.get("reservation_id", None)
        )
        if reservation_id is None:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for(
                    "resources.reservation_list"
                ),
                message="Reservation not found.",
                category=flash.CATEGORY_ERROR,
            )
            return response

        allocation_manager = _build_allocation_manager(
            db_session=db_session
        )
        reservation = _find_reservation_by_id(
            allocation_manager=allocation_manager,
            reservation_id=reservation_id,
        )
        if reservation is None:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for(
                    "resources.reservation_list"
                ),
                message="Reservation not found.",
                category=flash.CATEGORY_ERROR,
            )
            return response

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="resources.reservation_detail",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context.update(_resources_permission_flags(auth=auth))
        context["reservation"] = reservation
        response = _render(
            template_name="resources/reservations/detail.html",
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


def handle_reservation_edit(request: Request) -> Response:
    """
        ``GET /resources/reservations/{reservation_id}/edit`` /
        ``POST /resources/reservations/{reservation_id}/edit``.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        reservation_id = _coerce_int(
            raw=request.path_params.get("reservation_id", None)
        )
        if reservation_id is None:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for(
                    "resources.reservation_list"
                ),
                message="Reservation not found.",
                category=flash.CATEGORY_ERROR,
            )
            return response

        allocation_manager = _build_allocation_manager(
            db_session=db_session
        )
        reservation = _find_reservation_by_id(
            allocation_manager=allocation_manager,
            reservation_id=reservation_id,
        )
        if reservation is None:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for(
                    "resources.reservation_list"
                ),
                message="Reservation not found.",
                category=flash.CATEGORY_ERROR,
            )
            return response

        method = request.method.upper()
        form_view: Optional[MultiFormView] = None
        # A fresh form is pre-filled in UTC and says so; the page's
        # script moves it into the browser's zone.
        viewer_timezone = ""

        if method == "POST":
            single_form = _parse_form_or_empty(request=request)
            multi_form = _parse_form_multi(request=request)
            form_view = MultiFormView(data=multi_form)

            csrf_redirect = auth_guard.enforce_csrf_or_redirect(
                form=single_form,
                session=auth.session,
                fallback_url=_url_for_module.url_for(
                    "resources.reservation_edit",
                    reservation_id=reservation_id,
                ),
            )
            if csrf_redirect is not None:
                _attach_session_to_response(
                    response=csrf_redirect, session=auth.session
                )
                return csrf_redirect

            zone_name = str(single_form.get("tz", "") or "")
            viewer_timezone = _viewer_zone_name(zone_name=zone_name)
            zone = _resolve_viewer_zone(zone_name=zone_name)
            start_time: Optional[datetime] = None
            end_time: Optional[datetime] = None
            if zone is not None:
                # Typed in the viewer's zone; the manager gets UTC.
                start_time = _parse_form_datetime(
                    raw=single_form.get("start_time", ""), zone=zone
                )
                end_time = _parse_form_datetime(
                    raw=single_form.get("end_time", ""), zone=zone
                )

            if zone is None:
                flash.add_flash(
                    session=auth.session,
                    message=_unknown_zone_message(zone_name=zone_name),
                    category=flash.CATEGORY_ERROR,
                )
            elif start_time is None or end_time is None:
                flash.add_flash(
                    session=auth.session,
                    message="Start time and end time are required.",
                    category=flash.CATEGORY_ERROR,
                )
            else:
                try:
                    allocation_manager.modify_reservation(
                        reservation_id,
                        start_time=start_time,
                        end_time=end_time,
                        user_id=auth.user_id,
                    )
                    response = _redirect_with_flash(
                        session=auth.session,
                        url=_url_for_module.url_for(
                            "resources.reservation_detail",
                            reservation_id=reservation_id,
                        ),
                        message="Reservation updated successfully.",
                        category=flash.CATEGORY_SUCCESS,
                    )
                    return response
                except Exception as exc:
                    message = _describe_allocation_error(exc=exc)
                    if message is None:
                        _LOGGER.exception(
                            "Unexpected error updating reservation %s",
                            reservation_id,
                        )
                        message = (
                            "An unexpected error occurred while updating"
                            " the reservation. The problem has been"
                            " logged."
                        )
                    flash.add_flash(
                        session=auth.session,
                        message=message,
                        category=flash.CATEGORY_ERROR,
                    )

        # GET, or POST that fell through -- re-render with the
        # submitted values (``form_data``) when a POST failed so
        # typed input is never reverted to the stored window.
        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="resources.reservation_edit",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context.update(_resources_permission_flags(auth=auth))
        context["reservation"] = reservation
        context["form_data"] = form_view
        context["viewer_timezone"] = viewer_timezone
        response = _render(
            template_name="resources/reservations/edit.html",
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


def handle_reservation_cancel(request: Request) -> Response:
    """
        ``POST /resources/reservations/{reservation_id}/cancel``.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        reservation_id = _coerce_int(
            raw=request.path_params.get("reservation_id", None)
        )
        single_form = _parse_form_or_empty(request=request)

        csrf_redirect = auth_guard.enforce_csrf_or_redirect(
            form=single_form,
            session=auth.session,
            fallback_url=_url_for_module.url_for(
                "resources.reservation_list"
            ),
        )
        if csrf_redirect is not None:
            _attach_session_to_response(
                response=csrf_redirect, session=auth.session
            )
            return csrf_redirect

        if reservation_id is None:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for(
                    "resources.reservation_list"
                ),
                message="Reservation not found.",
                category=flash.CATEGORY_ERROR,
            )
            return response

        allocation_manager = _build_allocation_manager(
            db_session=db_session
        )
        try:
            allocation_manager.cancel_reservation(
                reservation_id, auth.user_id
            )
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for(
                    "resources.reservation_list"
                ),
                message="Reservation cancelled successfully.",
                category=flash.CATEGORY_SUCCESS,
            )
            return response
        except Exception as exc:
            message = _describe_allocation_error(exc=exc)
            if message is None:
                _LOGGER.exception(
                    "Unexpected error cancelling reservation %s",
                    reservation_id,
                )
                message = (
                    "An unexpected error occurred while cancelling"
                    " the reservation. The problem has been logged."
                )
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for(
                    "resources.reservation_list"
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
    "resources.reservation_list": handle_reservation_list,
    "resources.reservation_create": handle_reservation_create,
    "resources.reservation_detail": handle_reservation_detail,
    "resources.reservation_edit": handle_reservation_edit,
    "resources.reservation_cancel": handle_reservation_cancel,
}


def register_reservations_routes(*, app: Any) -> None:
    """
        Attach the reservation routes to a webworks app and
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
    "register_reservations_routes",
    "handle_reservation_list",
    "handle_reservation_create",
    "handle_reservation_detail",
    "handle_reservation_edit",
    "handle_reservation_cancel",
]
