"""
.. module:: webinterface.blueprints.config.routes_audit
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-native consumer-facing UI for /config/audit-logs
               (D4 slice -- audit log viewer).

.. moduleauthor:: Code Craft AI LLC

The audit-log viewer route served under the config blueprint:

* ``GET /config/audit-logs`` -- paginated audit log viewer with
                                ``?event_type=`` / ``?username=``
                                (resolved to a user id
                                server-side) / ``?user_id=`` /
                                ``?start_date=`` /
                                ``?end_date=`` filters. Date
                                strings are ISO-8601 (the
                                template's ``<input
                                type="datetime-local">``
                                produces this shape).

The handler dispatches to :class:`AuditLogger.query_logs` which
returns an :class:`AuditLogListResponse(entries, total, offset,
limit)`. The legacy template iterated the response object
directly; the port hands the template the entries list under the
existing ``logs`` context name so the template iteration shape
matches.
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
    flash,
    url_for as _url_for_module,
)
from ccai.pychestrate.webservice.webinterface.blueprints.config.routes import (
    CONFIG_PATH,
    _attach_session_to_response,
    _build_default_template_context,
    _render,
    _resolve_authenticated_request,
    _wrap_admin_handler_in_shell,
)


_ROUTE_TABLE = (
    ("config.audit_log_list", "/audit-logs", ("GET",)),
)


# ---------------------------------------------------------------------------
# Lazy-import builder seams
# ---------------------------------------------------------------------------


def _build_audit_logger(*, db_session: Any) -> Any:
    """
        Construct an :class:`AuditLogger`. Lazy-import.
    """
    from ccai.pychestrate.core.managers.audit_logger import (  # noqa: E402
        AuditLogger,
    )
    rtnval = AuditLogger(db_session)
    return rtnval


def _build_audit_log_query(
        *,
        event_types: Optional[List[Any]],
        user_id: Optional[str],
        start_date: Optional[datetime],
        end_date: Optional[datetime],
        offset: int,
        limit: int
    ) -> Any:
    """
        Construct an :class:`AuditLogQuery`. Lazy-import.
    """
    from ccai.pychestrate.core.managers.audit_logger import (  # noqa: E402
        AuditLogQuery,
    )
    rtnval = AuditLogQuery(
        event_types=event_types,
        user_id=user_id,
        start_date=start_date,
        end_date=end_date,
        offset=offset,
        limit=limit,
    )
    return rtnval


def _resolve_audit_event_type_or_none(
        *, event_type_str: Optional[str]
    ) -> Optional[List[Any]]:
    """
        Convert a single event-type string into the
        ``[AuditEventType]`` list shape ``AuditLogQuery``
        expects, or ``None`` when the filter is unset / value
        unknown.
    """
    if event_type_str is None or len(event_type_str) == 0:
        return None
    try:
        from ccai.pychestrate.core.orm import AuditEventType  # noqa: E402
        rtnval = [AuditEventType(event_type_str)]
        return rtnval
    except (ValueError, ImportError):
        return None


def _resolve_all_audit_event_types() -> List[str]:
    """
        Return every :class:`AuditEventType` value as a string
        (for the filter <select> dropdown).
    """
    try:
        from ccai.pychestrate.core.orm import AuditEventType  # noqa: E402
    except ImportError:
        return []
    rtnval: List[str] = []
    for member in AuditEventType:
        rtnval.append(member.value)
    return rtnval


def _resolve_user_id_for_username(
        *, db_session: Any, username: str
    ) -> Optional[str]:
    """
        Resolve a login name to its user id via the modern
        ``identity_users`` table so the audit page can filter by
        the usernames it displays. Lazy-imports; test-patchable.

        :param db_session: Open SQLAlchemy session.
        :param username: Login name to resolve.

        :returns: The user-id string, or ``None`` when no user has
                  that login name.
    """
    from ccai.pychestrate.webservice.identity.users.models import (  # noqa: E402
        IdentityUser,
    )

    user_row = (
        db_session.query(IdentityUser)
        .filter(IdentityUser.login_name == username)
        .first()
    )
    if user_row is None:
        return None
    rtnval = str(user_row.user_id)
    return rtnval


# ---------------------------------------------------------------------------
# Local helpers
# ---------------------------------------------------------------------------


def _parse_pagination_params(
        *, request: Request,
        default_per_page: int = 50
    ) -> Dict[str, Any]:
    raw_page = request.query_params.get("page", "1") or "1"
    try:
        page = int(raw_page)
    except (TypeError, ValueError):
        page = 1
    if page < 1:
        page = 1

    raw_per_page = (
        request.query_params.get("per_page", str(default_per_page))
        or str(default_per_page)
    )
    try:
        per_page = int(raw_per_page)
    except (TypeError, ValueError):
        per_page = default_per_page
    if per_page < 1:
        per_page = default_per_page

    rtnval = {"page": page, "per_page": per_page}
    return rtnval


def _parse_iso_datetime_or_none(*, raw: Optional[str]) -> Optional[datetime]:
    """
        Parse an ISO-8601 ``YYYY-MM-DDTHH:MM`` (or full ISO)
        string into a datetime. Returns ``None`` on bad input
        rather than raising -- matches the legacy handler's
        try/except ValueError -> pass behavior.
    """
    if raw is None or len(raw) == 0:
        return None
    try:
        rtnval = datetime.fromisoformat(raw)
        return rtnval
    except (TypeError, ValueError):
        return None


def _audit_log_response_to_entries(*, response: Any) -> List[Any]:
    """
        Pull the entries list out of an :class:`AuditLogListResponse`,
        tolerating both the dataclass shape and a bare list (test
        fakes may return either).
    """
    if response is None:
        return []
    entries = getattr(response, "entries", None)
    if entries is not None:
        return entries
    if isinstance(response, list):
        return response
    return []


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def handle_audit_log_list(request: Request) -> Response:
    """
        ``GET /config/audit-logs`` -- paginated audit log viewer.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        params = _parse_pagination_params(request=request)
        offset = (params["page"] - 1) * params["per_page"]

        selected_event_type = (
            request.query_params.get("event_type", None) or None
        )
        filter_user_id = (
            request.query_params.get("user_id", None) or None
        )
        filter_username = (
            request.query_params.get("username", None) or None
        )
        start_date_str = (
            request.query_params.get("start_date", None) or None
        )
        end_date_str = (
            request.query_params.get("end_date", None) or None
        )

        # The filter form takes a username (the table shows
        # usernames); resolve it to the user id the audit table
        # stores. A raw ?user_id= keeps working for saved links.
        username_unmatched = False
        if filter_username is not None:
            resolved_user_id = _resolve_user_id_for_username(
                db_session=db_session, username=filter_username
            )
            if resolved_user_id is None:
                username_unmatched = True
            else:
                filter_user_id = resolved_user_id

        start_date = _parse_iso_datetime_or_none(raw=start_date_str)
        end_date = _parse_iso_datetime_or_none(raw=end_date_str)

        event_types = _resolve_audit_event_type_or_none(
            event_type_str=selected_event_type
        )

        if username_unmatched is True:
            # No user has that login name -- render an empty page
            # (with a notice) rather than silently showing
            # unfiltered results.
            entries = []
            total = 0
        else:
            query = _build_audit_log_query(
                event_types=event_types,
                user_id=filter_user_id,
                start_date=start_date,
                end_date=end_date,
                offset=offset,
                limit=params["per_page"],
            )

            audit_logger = _build_audit_logger(db_session=db_session)
            result = audit_logger.query_logs(query)
            entries = _audit_log_response_to_entries(response=result)
            total = getattr(result, "total", None)
            if total is None:
                total = len(entries)

        total_pages = (total + params["per_page"] - 1) // params["per_page"]
        all_event_types = _resolve_all_audit_event_types()

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="config.audit_log_list",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["logs"] = entries
        context["all_event_types"] = all_event_types
        context["selected_event_type"] = selected_event_type
        context["filter_user_id"] = filter_user_id
        context["filter_username"] = filter_username
        context["username_unmatched"] = username_unmatched
        context["start_date"] = start_date_str
        context["end_date"] = end_date_str
        context["page"] = params["page"]
        context["per_page"] = params["per_page"]
        context["total"] = total
        context["total_pages"] = total_pages

        response = _render(
            template_name="config/audit/list.html",
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
    "config.audit_log_list": handle_audit_log_list,
}


def register_audit_routes(*, app: Any) -> None:
    """
        Attach the audit-log viewer route to a webworks app and
        register its endpoint name with the url_for shim.
    """
    for endpoint_name, relative_path, methods in _ROUTE_TABLE:
        full_path = CONFIG_PATH + relative_path
        _url_for_module.register_endpoint(
            endpoint=endpoint_name, pattern=full_path
        )
        handler = _HANDLERS_BY_ENDPOINT[endpoint_name]
        wrapped_handler = _wrap_admin_handler_in_shell(handler)
        app.attach_route(full_path, methods=list(methods))(wrapped_handler)
    return


__all__ = [
    "register_audit_routes",
    "handle_audit_log_list",
]
