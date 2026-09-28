"""
.. module:: webinterface.blueprints.resources.routes_health
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-native consumer-facing UI for /resources/health
               (E4 slice -- health monitoring).

.. moduleauthor:: Code Craft AI LLC

The five health routes served under the resources blueprint:

* ``GET  /resources/health``                              -- dashboard
                                                             grouping
                                                             resources
                                                             by health
                                                             status.
* ``GET  /resources/health/{resource_id}``                -- detail +
                                                             history.
* ``GET  /resources/health/{resource_id}/config``         -- form
                                                             (admin).
* ``POST /resources/health/{resource_id}/config``         -- update
                                                             config
                                                             (admin).
* ``POST /resources/health/{resource_id}/update``         -- update
                                                             status
                                                             (admin).
* ``POST /resources/health/{resource_id}/check``          -- run a
                                                             one-shot
                                                             health
                                                             check
                                                             (admin).
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


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
    _attach_session_to_response,
    _build_default_template_context,
    _parse_form_or_empty,
    _redirect_with_flash,
    _render,
    _require_permission_or_redirect,
    _resolve_authenticated_request,
)
from ccai.pychestrate.webservice.webinterface.blueprints.resources.routes import (
    RESOURCES_MAX_PER_PAGE,
    RESOURCES_PATH,
    _as_sentence,
    _resources_permission_flags,
    _wrap_resources_handler_in_shell,
    _build_page_window,
    _calculate_total_pages,
)


_LOGGER = logging.getLogger("pychestrate.ui.resources.health")


_ROUTE_TABLE = (
    ("resources.health_dashboard", "/health", ("GET",)),
    (
        "resources.health_detail",
        "/health/{resource_id}",
        ("GET",),
    ),
    (
        "resources.health_config",
        "/health/{resource_id}/config",
        ("GET", "POST"),
    ),
    (
        "resources.health_update",
        "/health/{resource_id}/update",
        ("POST",),
    ),
    (
        "resources.health_run_check",
        "/health/{resource_id}/check",
        ("POST",),
    ),
)


_ADMIN_PERMISSION = "system:resources.manage"


# ---------------------------------------------------------------------------
# Lazy-import builder seams
# ---------------------------------------------------------------------------


def _build_resource_manager(*, db_session: Any) -> Any:
    """
        Construct a :class:`ResourceManager`. Lazy-imports.
    """
    from ccai.pychestrate.core.managers.resource_manager import (  # noqa: E402
        ResourceManager,
    )
    rtnval = ResourceManager(db_session)
    return rtnval


def _build_health_monitor(*, db_session: Any) -> Any:
    """
        Construct a :class:`HealthMonitor`. Lazy-imports.
    """
    from ccai.pychestrate.core.managers.health_monitor import (  # noqa: E402
        HealthMonitor,
    )
    rtnval = HealthMonitor(db_session)
    return rtnval


def _resolve_health_status(*, status_str: str) -> Any:
    """
        Resolve a string to the :class:`HealthStatus` enum value.
        Raises ValueError on unknown.
    """
    from ccai.pychestrate.core.orm import (  # noqa: E402
        HealthStatus,
    )
    rtnval = HealthStatus(status_str)
    return rtnval


def _build_health_check_config(
        *,
        resource_id: int,
        probe_url: Optional[str],
        probe_command: Optional[str],
        interval_seconds: int,
        timeout_seconds: int,
        failure_threshold: int,
        success_threshold: int,
        enabled: bool
    ) -> Any:
    """
        Construct a :class:`HealthCheckConfig`. Lazy-imports.
    """
    from ccai.pychestrate.core.managers.health_monitor import (  # noqa: E402
        HealthCheckConfigRequest,
    )
    rtnval = HealthCheckConfigRequest(
        resource_id=resource_id,
        probe_url=probe_url,
        probe_command=probe_command,
        interval_seconds=interval_seconds,
        timeout_seconds=timeout_seconds,
        failure_threshold=failure_threshold,
        success_threshold=success_threshold,
        enabled=enabled,
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


def _group_resources_by_health_status(
        *, resources: List[Any]
    ) -> Dict[str, List[Any]]:
    """
        Bucket resources by ``health_status`` value into the
        four documented status groups. Resources with unknown
        statuses are silently dropped from the dashboard --
        matches the legacy handler.

        :returns: Dict with keys 'online', 'degraded',
                  'maintenance', 'offline' -- always present so
                  the template can index unconditionally.
    """
    rtnval: Dict[str, List[Any]] = {
        "online": [],
        "degraded": [],
        "maintenance": [],
        "offline": [],
    }
    for resource in resources:
        status = getattr(resource, "health_status", None)
        if status is None:
            continue
        status_value = getattr(status, "value", status)
        if isinstance(status_value, str) and status_value in rtnval:
            rtnval[status_value].append(resource)
    return rtnval


def _describe_health_monitor_error(*, exc: Exception) -> Optional[str]:
    """
        Map a typed HealthMonitor error to its deliberate,
        user-facing message. Returns None when ``exc`` is not one
        of the typed errors -- callers then log the exception and
        flash a generic sentence instead of the raw exception
        text. Lazy-imports so this module stays importable when
        the manager package is absent (test runtimes patch the
        manager builders).

        :param exc: The exception raised by a HealthMonitor call.

        :returns: Specific user-facing message, or None.
    """
    try:
        from ccai.pychestrate.core.managers.health_monitor import (  # noqa: E402
            HealthMonitorError,
        )
    except ImportError:
        return None

    if not isinstance(exc, HealthMonitorError):
        return None

    # The manager's text (field names, ids) is for the log; the person
    # gets the copy below.
    _LOGGER.info(
        "Health request refused [%s]: %s", exc.error_code, exc.message
    )
    copy = _HEALTH_ERROR_COPY.get(exc.error_code, None)
    if copy is not None:
        return copy
    # Probe URL problems and the timeout limit are written for people.
    rtnval = _as_sentence(text=exc.message)
    return rtnval


#: Visible labels of the health check form fields, for the error summary.
HEALTH_FIELD_LABELS: Dict[str, str] = {
    "probe_url": "Probe URL",
    "interval_seconds": "Check Interval",
    "timeout_seconds": "Timeout",
    "failure_threshold": "Failure Threshold",
    "success_threshold": "Success Threshold",
}


def _health_field_errors(*, exc: BaseException) -> Dict[str, str]:
    """
        The ``{field: message}`` for a refused health check form, or an
        empty dict when the error is about no single input. The monitor's
        configuration errors name their field (``exc.field``); the message
        is the one people are shown.

        :param exc: The error the monitor raised.

        :returns: One entry, or an empty dict.
    """
    field = getattr(exc, "field", None)
    rtnval: Dict[str, str] = {}
    if isinstance(field, str) is True and field in HEALTH_FIELD_LABELS:
        message = _describe_health_monitor_error(exc=exc)
        if message is not None:
            rtnval = {field: message}
    return rtnval


# User-facing copy for typed HealthMonitor errors, by error code (the
# managers' own messages stay in the log).
_HEALTH_ERROR_COPY: Dict[str, str] = {
    "HEALTH_CHECK_CONFIG_NOT_FOUND": (
        "This resource has no health check yet. Configure one first."
    ),
    "HEALTH_CHANGE_REASON_REQUIRED": (
        "Enter a reason for the status change (at least 3 characters);"
        " it is kept in the audit trail."
    ),
    "INVALID_HEALTH_STATUS": (
        "Choose a health status: online, degraded, maintenance or offline."
    ),
    "RESOURCE_NOT_FOUND": "That resource no longer exists.",
    "INTERVAL_TOO_SHORT": "The check interval must be at least 1 second.",
    "TIMEOUT_TOO_SHORT": "The probe timeout must be at least 1 second.",
    "FAILURE_THRESHOLD_TOO_LOW": "The failure threshold must be at least 1.",
    "SUCCESS_THRESHOLD_TOO_LOW": "The success threshold must be at least 1.",
}


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def handle_health_dashboard(request: Request) -> Response:
    """
        ``GET /resources/health`` -- dashboard.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        resource_manager = _build_resource_manager(db_session=db_session)
        # The stat cards use a dedicated aggregate count query so
        # they stay honest past the grouped-table fetch limit; the
        # per-status tables below are bounded and the template
        # shows a "Showing N of M" note when a group is truncated.
        health_counts = resource_manager.count_resources_by_health_status()
        resources = resource_manager.list_resources(limit=1000).resources
        health_groups = _group_resources_by_health_status(
            resources=resources
        )

        total_count = 0
        for status_count in health_counts.values():
            total_count = total_count + status_count

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="resources.health_dashboard",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context.update(_resources_permission_flags(auth=auth))
        context["health_groups"] = health_groups
        context["health_counts"] = health_counts
        context["total_count"] = total_count

        response = _render(
            template_name="resources/health/dashboard.html",
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


def handle_health_detail(request: Request) -> Response:
    """
        ``GET /resources/health/{resource_id}`` -- detail with
        paginated history.
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
                url=_url_for_module.url_for(
                    "resources.health_dashboard"
                ),
                message="Resource not found.",
                category=flash.CATEGORY_ERROR,
            )
            return response

        resource_manager = _build_resource_manager(db_session=db_session)
        resource = resource_manager.get_resource(resource_id)
        if resource is None:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for(
                    "resources.health_dashboard"
                ),
                message="Resource not found.",
                category=flash.CATEGORY_ERROR,
            )
            return response

        page = _coerce_int_with_default(
            raw=request.query_params.get("page", None), default=1
        )
        if page < 1:
            page = 1
        per_page = _coerce_int_with_default(
            raw=request.query_params.get("per_page", None), default=20
        )
        if per_page < 1:
            per_page = 20
        if per_page > RESOURCES_MAX_PER_PAGE:
            per_page = RESOURCES_MAX_PER_PAGE
        offset = (page - 1) * per_page

        health_monitor = _build_health_monitor(db_session=db_session)
        history = health_monitor.get_health_history(
            resource_id, offset=offset, limit=per_page
        )
        config = health_monitor.get_health_check_config(resource_id)

        total_pages = _calculate_total_pages(
            total=history.total, per_page=per_page
        )
        page_window = _build_page_window(
            page=page, total_pages=total_pages
        )

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="resources.health_detail",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context.update(_resources_permission_flags(auth=auth))
        context["resource"] = resource
        context["history"] = history.transitions
        context["config"] = config
        context["page"] = page
        context["per_page"] = per_page
        context["total_pages"] = total_pages
        context["page_window"] = page_window

        response = _render(
            template_name="resources/health/detail.html",
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


def handle_health_config(request: Request) -> Response:
    """
        ``GET /resources/health/{resource_id}/config`` /
        ``POST /resources/health/{resource_id}/config``
        (admin-gated).
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
                url=_url_for_module.url_for(
                    "resources.health_dashboard"
                ),
                message="Resource not found.",
                category=flash.CATEGORY_ERROR,
            )
            return response

        resource_manager = _build_resource_manager(db_session=db_session)
        resource = resource_manager.get_resource(resource_id)
        if resource is None:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for(
                    "resources.health_dashboard"
                ),
                message="Resource not found.",
                category=flash.CATEGORY_ERROR,
            )
            return response

        health_monitor = _build_health_monitor(db_session=db_session)
        method = request.method.upper()
        errors: Dict[str, str] = {}
        health_form: Optional[Dict[str, Any]] = None
        status_code = 200

        if method == "POST":
            single_form = _parse_form_or_empty(request=request)

            csrf_redirect = auth_guard.enforce_csrf_or_redirect(
                form=single_form,
                session=auth.session,
                fallback_url=_url_for_module.url_for(
                    "resources.health_config",
                    resource_id=resource_id,
                ),
            )
            if csrf_redirect is not None:
                _attach_session_to_response(
                    response=csrf_redirect, session=auth.session
                )
                return csrf_redirect

            probe_url = str(single_form.get("probe_url", "")).strip()
            probe_command = str(
                single_form.get("probe_command", "")
            ).strip()
            interval_seconds = _coerce_int_with_default(
                raw=single_form.get("interval_seconds", None),
                default=60,
            )
            timeout_seconds = _coerce_int_with_default(
                raw=single_form.get("timeout_seconds", None),
                default=10,
            )
            failure_threshold = _coerce_int_with_default(
                raw=single_form.get("failure_threshold", None),
                default=3,
            )
            success_threshold = _coerce_int_with_default(
                raw=single_form.get("success_threshold", None),
                default=1,
            )
            enabled = single_form.get("enabled", "") == "on"
            status_code = 400
            health_form = {
                "probe_url": probe_url,
                "interval_seconds": str(single_form.get("interval_seconds", "")),
                "timeout_seconds": str(single_form.get("timeout_seconds", "")),
                "failure_threshold": str(single_form.get("failure_threshold", "")),
                "success_threshold": str(single_form.get("success_threshold", "")),
                "enabled": enabled,
            }

            try:
                config_request = _build_health_check_config(
                    resource_id=resource_id,
                    probe_url=probe_url if len(probe_url) > 0 else None,
                    probe_command=(
                        probe_command if len(probe_command) > 0 else None
                    ),
                    interval_seconds=interval_seconds,
                    timeout_seconds=timeout_seconds,
                    failure_threshold=failure_threshold,
                    success_threshold=success_threshold,
                    enabled=enabled,
                )
                health_monitor.configure_health_check(
                    config_request, auth.user_id
                )
                response = _redirect_with_flash(
                    session=auth.session,
                    url=_url_for_module.url_for(
                        "resources.health_detail",
                        resource_id=resource_id,
                    ),
                    message="Health check configuration saved.",
                    category=flash.CATEGORY_SUCCESS,
                )
                return response
            except Exception as exc:
                errors = _health_field_errors(exc=exc)
                if len(errors) == 0:
                    message = _describe_health_monitor_error(exc=exc)
                    if message is None:
                        _LOGGER.exception(
                            "Unexpected error saving health check config"
                            " for resource %s",
                            resource_id,
                        )
                        message = (
                            "An unexpected error occurred while saving"
                            " the configuration. The problem has been"
                            " logged."
                        )
                    flash.add_flash(
                        session=auth.session,
                        message=message,
                        category=flash.CATEGORY_ERROR,
                    )

        # GET, or POST that fell through.
        config = health_monitor.get_health_check_config(resource_id)

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="resources.health_config",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context.update(_resources_permission_flags(auth=auth))
        context["resource"] = resource
        context["config"] = config
        context["health_form"] = health_form
        context["errors"] = errors
        context["error_labels"] = HEALTH_FIELD_LABELS
        response = _render(
            template_name="resources/health/config.html",
            context=context,
            status_code=status_code,
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


def handle_health_update(request: Request) -> Response:
    """
        ``POST /resources/health/{resource_id}/update`` --
        manually update health status (admin-gated).
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
                "resources.health_dashboard"
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
                url=_url_for_module.url_for(
                    "resources.health_dashboard"
                ),
                message="Resource not found.",
                category=flash.CATEGORY_ERROR,
            )
            return response

        status_str = str(single_form.get("status", "")).strip()
        reason = str(single_form.get("reason", "")).strip()

        health_monitor = _build_health_monitor(db_session=db_session)
        try:
            status = _resolve_health_status(status_str=status_str)
            health_monitor.update_health_status(
                resource_id, status, reason, auth.user_id
            )
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for(
                    "resources.health_detail", resource_id=resource_id
                ),
                message="Health status updated to {}.".format(
                    status_str
                ),
                category=flash.CATEGORY_SUCCESS,
            )
            return response
        except Exception as exc:
            message = _describe_health_monitor_error(exc=exc)
            if message is None:
                _LOGGER.exception(
                    "Unexpected error updating health status for"
                    " resource %s",
                    resource_id,
                )
                message = (
                    "An unexpected error occurred while updating the"
                    " health status. The problem has been logged."
                )
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for(
                    "resources.health_detail", resource_id=resource_id
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


def handle_health_run_check(request: Request) -> Response:
    """
        ``POST /resources/health/{resource_id}/check`` -- run a
        one-shot health check (admin-gated).
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
                "resources.health_dashboard"
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
                url=_url_for_module.url_for(
                    "resources.health_dashboard"
                ),
                message="Resource not found.",
                category=flash.CATEGORY_ERROR,
            )
            return response

        health_monitor = _build_health_monitor(db_session=db_session)
        try:
            # run_health_check returns a HealthCheckResult -- the
            # outcome is the ``healthy`` flag, and ``error_message``
            # carries the probe failure reason when present.
            result = health_monitor.run_health_check(resource_id)
            if result.healthy is True:
                msg_parts = ["Health check passed."]
                category = flash.CATEGORY_SUCCESS
            else:
                msg_parts = ["Health check failed."]
                if result.error_message is not None:
                    msg_parts.append(
                        "Reason: {}.".format(result.error_message)
                    )
                category = flash.CATEGORY_WARNING
            if result.status_changed is True:
                msg_parts.append(
                    "Status changed from {} to {}.".format(
                        result.old_status, result.new_status
                    )
                )
            message = " ".join(msg_parts)
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for(
                    "resources.health_detail", resource_id=resource_id
                ),
                message=message,
                category=category,
            )
            return response
        except Exception as exc:
            message = _describe_health_monitor_error(exc=exc)
            if message is None:
                _LOGGER.exception(
                    "Unexpected error running health check for"
                    " resource %s",
                    resource_id,
                )
                message = (
                    "An unexpected error occurred while running the"
                    " health check. The problem has been logged."
                )
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for(
                    "resources.health_detail", resource_id=resource_id
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
    "resources.health_dashboard": handle_health_dashboard,
    "resources.health_detail": handle_health_detail,
    "resources.health_config": handle_health_config,
    "resources.health_update": handle_health_update,
    "resources.health_run_check": handle_health_run_check,
}


def register_health_routes(*, app: Any) -> None:
    """
        Attach the health routes to a webworks app and register
        their endpoint names with the url_for shim.
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
    "register_health_routes",
    "handle_health_dashboard",
    "handle_health_detail",
    "handle_health_config",
    "handle_health_update",
    "handle_health_run_check",
]
