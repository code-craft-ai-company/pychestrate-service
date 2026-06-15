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
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime
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
    _parse_form_multi,
    _parse_form_or_empty,
    _redirect_with_flash,
    _render,
    _resolve_authenticated_request,
)
from ccai.pychestrate.webservice.webinterface.blueprints.resources.routes import (
    RESOURCES_PATH,
)


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


def _approximate_total_pages(
        *, page: int, per_page: int, returned_count: int
    ) -> int:
    if returned_count < per_page:
        if page == 1:
            return 1
        return page
    return page + 1


def _find_reservation_by_id(
        *, allocation_manager: Any, reservation_id: int
    ) -> Optional[Any]:
    """
        Mirror the legacy "list 1000 reservations and search
        by id" pattern. The manager has no direct
        ``get_reservation``; this helper wraps the lookup so
        every callsite uses the same shape.

        :param allocation_manager: AllocationManager instance.
        :param reservation_id: Target id.

        :returns: The reservation row or None.
    """
    reservations = allocation_manager.list_reservations(
        limit=1000
    ).reservations
    for r in reservations:
        if getattr(r, "id", None) == reservation_id:
            return r
    return None


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

        reservations = allocation_manager.list_reservations(
            resource_id=resource_id,
            start_after=start_after,
            end_before=end_before,
            offset=offset,
            limit=params["per_page"],
        ).reservations
        resources = resource_manager.list_resources(limit=100).resources

        total_pages = _approximate_total_pages(
            page=params["page"],
            per_page=params["per_page"],
            returned_count=len(reservations),
        )

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="resources.reservation_list",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["reservations"] = reservations
        context["resources"] = resources
        context["page"] = params["page"]
        context["per_page"] = params["per_page"]
        context["total_pages"] = total_pages
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
        status_code: int = 200
    ) -> HTMLResponse:
    """
        Helper for both GET and POST-error re-render paths.
    """
    resources = resource_manager.list_resources(limit=100).resources
    flashes = flash.consume_flashes(session=auth.session)
    context = _build_default_template_context(
        session=auth.session,
        request_endpoint="resources.reservation_create",
        flashes=flashes,
        csrf_token=auth.csrf_token,
    )
    context["resources"] = resources
    context["form_data"] = form_data
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

        if method == "GET":
            response = _render_reservation_create_form(
                auth=auth,
                resource_manager=resource_manager,
                form_data=None,
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

        start_time = _parse_iso_datetime_or_none(raw=start_time_str)
        end_time = _parse_iso_datetime_or_none(raw=end_time_str)

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
                    "resources.reservation_list"
                ),
                message=(
                    "Reservation created successfully. ID: {}".format(
                        reservation.id
                    )
                ),
                category=flash.CATEGORY_SUCCESS,
            )
            return response
        except Exception as exc:
            flash.add_flash(
                session=auth.session,
                message="Error creating reservation: {}".format(
                    str(exc)
                ),
                category=flash.CATEGORY_ERROR,
            )

        response = _render_reservation_create_form(
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

        if method == "POST":
            single_form = _parse_form_or_empty(request=request)

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

            start_time_str = str(single_form.get("start_time", ""))
            end_time_str = str(single_form.get("end_time", ""))
            start_time = _parse_iso_datetime_or_none(
                raw=start_time_str
            )
            end_time = _parse_iso_datetime_or_none(raw=end_time_str)

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
                flash.add_flash(
                    session=auth.session,
                    message="Error updating reservation: {}".format(
                        str(exc)
                    ),
                    category=flash.CATEGORY_ERROR,
                )

        # GET, or POST that fell through.
        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="resources.reservation_edit",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["reservation"] = reservation
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
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for(
                    "resources.reservation_list"
                ),
                message="Error cancelling reservation: {}".format(
                    str(exc)
                ),
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
        app.attach_route(full_path, methods=list(methods))(handler)
    return


__all__ = [
    "register_reservations_routes",
    "handle_reservation_list",
    "handle_reservation_create",
    "handle_reservation_detail",
    "handle_reservation_edit",
    "handle_reservation_cancel",
]
