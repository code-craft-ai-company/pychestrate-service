"""
.. module:: webinterface.blueprints.config.routes_audit
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-native consumer-facing UI for /admin/audit-logs
               (the audit log viewer and its export).

.. moduleauthor:: Code Craft AI LLC

The audit-log routes served under the config blueprint:

* ``GET /admin/audit-logs``        -- the audit log, newest first, with
                                      action / actor / target / date
                                      filters and cursor paging.
* ``GET /admin/audit-logs/export`` -- the filtered log as CSV
                                      (``?format=csv``, the default) or
                                      JSON Lines (``?format=jsonl``).

Both read the canonical ``audit_records`` store -- the table the audit
pipeline actually writes (sign-ins and sign-outs, user / role /
password / session administration, secrets, RPA, UI-profile changes,
and every change a signed-in user makes to projects, resources,
variables and legacy secrets through the data-change bridge). The page
used to read the legacy ``audit_logs`` table, which nothing wrote to,
so it was always empty (audit ADM-02).

Query parameters (all optional): ``action`` (an audit kind), ``actor``
(a username), ``target`` (substring of the target reference, e.g.
``projects:12`` or ``user:``), ``since`` / ``until`` (ISO date or
date-time, UTC), ``before`` / ``after`` (sequence-number cursors) and
``per_page``.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import csv
import io
import json

from datetime import datetime, time as _time, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from ccai.webworks.routing.request import Request
from ccai.webworks.routing.response import (
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
    _require_admin_permission_for,
    _wrap_admin_handler_in_shell,
)


_ROUTE_TABLE = (
    ("config.audit_log_list", "/audit-logs", ("GET",)),
    ("config.audit_log_export", "/audit-logs/export", ("GET",)),
)

# Permission each route enforces server-side (see
# ``routes._require_admin_permission_for``). Audit log.
_ROUTE_PERMISSIONS = {
    "config.audit_log_list": "system:audit.read",
    "config.audit_log_export": "system:audit.read",
}

DEFAULT_PER_PAGE: int = 50
MAX_PER_PAGE: int = 200

EXPORT_FORMAT_CSV: str = "csv"
EXPORT_FORMAT_JSONL: str = "jsonl"

EXPORT_COLUMNS: Tuple[str, ...] = (
    "sequence_number",
    "written_at",
    "actor",
    "actor_user_id",
    "action",
    "kind",
    "target_ref",
    "summary",
    "client_address",
    "record_hash",
    "payload",
)

# Readable group names for the action filter, by kind area
# (``audit.<area>.<verb>``).
_AREA_LABELS = {
    "auth": "Sign-in",
    "session": "Sessions",
    "user": "Users",
    "role": "Roles",
    "data": "Projects, resources, variables and legacy secrets",
    "secret": "Secrets",
    "variable": "Variables (API)",
    "project": "Projects (API)",
    "rpa": "RPA",
    "ui_profile": "UI profile",
}


# ---------------------------------------------------------------------------
# Lazy-import seams (test-patchable)
# ---------------------------------------------------------------------------


def _query_page(*, db_session: Any, audit_query: Any) -> Any:
    """
        One page of audit records. Lazy-import seam.

        :param db_session: Open SQLAlchemy session.
        :param audit_query: :class:`audit.audit_query.AuditQuery`.

        :returns: :class:`audit.audit_query.AuditPage`.
    """
    from ccai.pychestrate.webservice.audit.audit_query import (  # noqa: E402
        query_audit_page,
    )
    rtnval = query_audit_page(db_session=db_session, audit_query=audit_query)
    return rtnval


def _list_kinds() -> List[Any]:
    """
        Every registered audit kind. Lazy-import seam.

        :returns: List of :class:`audit.audit_query.AuditKindView`.
    """
    from ccai.pychestrate.webservice.audit.audit_query import (  # noqa: E402
        list_audit_kinds,
    )
    rtnval = list_audit_kinds()
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
        .filter(IdentityUser.login_name == username.strip().lower())
        .first()
    )
    if user_row is None:
        return None
    rtnval = str(user_row.user_id)
    return rtnval


# ---------------------------------------------------------------------------
# Local helpers
# ---------------------------------------------------------------------------


def _parse_iso_datetime_or_none(
        *, raw: Optional[str], end_of_day: bool = False
    ) -> Optional[datetime]:
    """
        Parse an ISO-8601 date (``YYYY-MM-DD``) or date-time
        (``YYYY-MM-DDTHH:MM``) filter value as UTC. A bare date means
        the start of that day, or its end when ``end_of_day`` is set
        (so "until 2026-09-22" includes the whole day). Returns
        ``None`` on missing or bad input.

        :param raw: The query-string value.
        :param end_of_day: Resolve a bare date to its last instant.

        :returns: Aware UTC datetime or None.
    """
    if raw is None or len(raw.strip()) == 0:
        return None
    text = raw.strip()
    try:
        if len(text) == 10:
            day = datetime.fromisoformat(text).date()
            if end_of_day is True:
                rtnval = datetime.combine(day, _time.max)
            else:
                rtnval = datetime.combine(day, _time.min)
        else:
            rtnval = datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return None
    if rtnval.tzinfo is None:
        rtnval = rtnval.replace(tzinfo=timezone.utc)
    return rtnval


def _parse_positive_int_or_none(*, raw: Optional[str]) -> Optional[int]:
    """
        Parse a cursor / size parameter.

        :param raw: The query-string value.

        :returns: A positive int or None.
    """
    if raw is None:
        return None
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return None
    if value < 1:
        return None
    return value


def _read_filters(*, request: Request) -> Dict[str, Any]:
    """
        The page's filter values from the query string, as typed.

        :param request: Incoming webworks request.

        :returns: Dict of ``action``, ``actor``, ``target``, ``since``,
                  ``until``, ``per_page``.
    """
    params = request.query_params

    def _text(name: str) -> str:
        value = params.get(name, "") or ""
        return str(value).strip()

    per_page = _parse_positive_int_or_none(raw=params.get("per_page", None))
    if per_page is None:
        per_page = DEFAULT_PER_PAGE
    if per_page > MAX_PER_PAGE:
        per_page = MAX_PER_PAGE

    rtnval = {
        "action": _text("action"),
        "actor": _text("actor"),
        "target": _text("target"),
        "since": _text("since"),
        "until": _text("until"),
        "per_page": per_page,
    }
    return rtnval


def _filter_query_params(*, filters: Dict[str, Any]) -> Dict[str, Any]:
    """
        The non-empty filters as query parameters, for building the
        paging and export links (so they keep the filters).

        :param filters: From :func:`_read_filters`.

        :returns: Dict of parameters (empty values omitted).
    """
    rtnval: Dict[str, Any] = {}
    for name in ("action", "actor", "target", "since", "until"):
        value = filters.get(name, "")
        if value is not None and len(str(value)) > 0:
            rtnval[name] = value
    if int(filters.get("per_page", DEFAULT_PER_PAGE)) != DEFAULT_PER_PAGE:
        rtnval["per_page"] = filters["per_page"]
    return rtnval


def _build_audit_query(
        *,
        db_session: Any,
        filters: Dict[str, Any],
        known_kinds: List[str],
        before: Optional[int],
        after: Optional[int]
    ) -> Tuple[Optional[Any], List[str]]:
    """
        Turn the filters into an :class:`AuditQuery`, collecting notices
        for filters that cannot match anything.

        :param db_session: Open SQLAlchemy session.
        :param filters: From :func:`_read_filters`.
        :param known_kinds: Registered audit kinds.
        :param before: "Older" cursor.
        :param after: "Newer" cursor.

        :returns: ``(query, notices)``; the query is None when a filter
                  names something that does not exist (the page then
                  shows no records and the notice instead of silently
                  ignoring the filter).
    """
    from ccai.pychestrate.webservice.audit.audit_query import (  # noqa: E402
        AuditQuery,
    )

    notices: List[str] = []
    kinds: Tuple[str, ...] = ()
    if len(filters["action"]) > 0:
        if filters["action"] in known_kinds:
            kinds = (filters["action"],)
        else:
            notices.append('Unknown action "{}".'.format(filters["action"]))

    actor_user_id: Optional[str] = None
    if len(filters["actor"]) > 0:
        actor_user_id = _resolve_user_id_for_username(
            db_session=db_session, username=filters["actor"]
        )
        if actor_user_id is None:
            notices.append(
                'No user has the username "{}".'.format(filters["actor"])
            )

    since = _parse_iso_datetime_or_none(raw=filters["since"])
    if len(filters["since"]) > 0 and since is None:
        notices.append('"{}" is not a date.'.format(filters["since"]))
    until = _parse_iso_datetime_or_none(raw=filters["until"], end_of_day=True)
    if len(filters["until"]) > 0 and until is None:
        notices.append('"{}" is not a date.'.format(filters["until"]))

    if len(notices) > 0:
        return (None, notices)

    target = filters["target"] if len(filters["target"]) > 0 else None
    audit_query = AuditQuery(
        kinds=kinds,
        actor_user_id=actor_user_id,
        target_contains=target,
        since=since,
        until=until,
        before_sequence=before,
        after_sequence=after,
        limit=int(filters["per_page"]),
    )
    rtnval = (audit_query, notices)
    return rtnval


def _action_groups(*, kind_views: List[Any]) -> List[Dict[str, Any]]:
    """
        The action filter's ``<optgroup>`` sections.

        :param kind_views: Registered kinds.

        :returns: List of ``{"label", "actions": [{"kind", "label",
                  "description"}]}``.
    """
    from ccai.pychestrate.webservice.audit.audit_presenter import (  # noqa: E402
        action_for_kind,
    )

    groups: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    for view in kind_views:
        area = view.area
        if area not in groups:
            groups[area] = {
                "label": _AREA_LABELS.get(area, area.replace("_", " ").title()),
                "actions": [],
            }
            order.append(area)
        label = action_for_kind(kind=view.kind)
        if view.kind == "audit.data.created":
            label = "Created (project, resource, variable ...)"
        elif view.kind == "audit.data.updated":
            label = "Updated (project, resource, variable ...)"
        elif view.kind == "audit.data.deleted":
            label = "Deleted (project, resource, variable ...)"
        groups[area]["actions"].append({
            "kind": view.kind,
            "label": label,
            "description": view.description,
        })
    rtnval = [groups[area] for area in order]
    return rtnval


def _describe_records(*, db_session: Any, records: List[Any]) -> List[Any]:
    """
        Readable rows for a batch of records (one login-name lookup).

        :param db_session: Open SQLAlchemy session.
        :param records: :class:`AuditRecord` rows.

        :returns: List of :class:`audit.audit_presenter.AuditRow`.
    """
    from ccai.pychestrate.webservice.audit.audit_presenter import (  # noqa: E402
        describe_audit_record,
        load_login_names,
        user_ids_in_records,
    )

    logins = load_login_names(
        db_session=db_session, user_ids=user_ids_in_records(records=records)
    )
    rtnval = [describe_audit_record(record=record, logins=logins) for record in records]
    return rtnval


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def handle_audit_log_list(request: Request) -> Response:
    """
        ``GET /admin/audit-logs`` -- the audit log, newest first.

        :param request: Incoming webworks request.

        :returns: HTMLResponse rendering ``config/audit/list.html``.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        filters = _read_filters(request=request)
        before = _parse_positive_int_or_none(raw=request.query_params.get("before", None))
        after = _parse_positive_int_or_none(raw=request.query_params.get("after", None))

        kind_views = _list_kinds()
        known_kinds = [view.kind for view in kind_views]
        audit_query, notices = _build_audit_query(
            db_session=db_session,
            filters=filters,
            known_kinds=known_kinds,
            before=before,
            after=after,
        )

        rows: List[Any] = []
        total = 0
        older_url: Optional[str] = None
        newer_url: Optional[str] = None
        link_params = _filter_query_params(filters=filters)
        if audit_query is not None:
            page = _query_page(db_session=db_session, audit_query=audit_query)
            rows = _describe_records(db_session=db_session, records=page.records)
            total = page.total
            if page.has_older is True and page.oldest_sequence is not None:
                older_url = _url_for_module.url_for(
                    "config.audit_log_list", before=page.oldest_sequence, **link_params
                )
            if page.has_newer is True and page.newest_sequence is not None:
                newer_url = _url_for_module.url_for(
                    "config.audit_log_list", after=page.newest_sequence, **link_params
                )

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="config.audit_log_list",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["audit_rows"] = rows
        context["audit_total"] = total
        context["audit_filters"] = filters
        context["audit_notices"] = notices
        context["action_groups"] = _action_groups(kind_views=kind_views)
        context["older_url"] = older_url
        context["newer_url"] = newer_url
        context["newest_url"] = (
            _url_for_module.url_for("config.audit_log_list", **link_params)
            if (before is not None or after is not None) else None
        )
        context["export_csv_url"] = _url_for_module.url_for(
            "config.audit_log_export", format=EXPORT_FORMAT_CSV, **link_params
        )
        context["export_jsonl_url"] = _url_for_module.url_for(
            "config.audit_log_export", format=EXPORT_FORMAT_JSONL, **link_params
        )

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


def _export_row_values(*, row: Any) -> Dict[str, Any]:
    """
        One exported record, keyed by :data:`EXPORT_COLUMNS`.

        :param row: :class:`audit.audit_presenter.AuditRow`.

        :returns: Dict of column values.
    """
    written_at = ""
    if row.written_at is not None:
        written = row.written_at
        if written.tzinfo is None:
            written = written.replace(tzinfo=timezone.utc)
        written_at = written.astimezone(timezone.utc).isoformat()
    rtnval = {
        "sequence_number": row.sequence_number,
        "written_at": written_at,
        "actor": row.actor_label,
        "actor_user_id": row.actor_user_id or "",
        "action": row.action,
        "kind": row.kind,
        "target_ref": row.target_ref or "",
        "summary": row.summary,
        "client_address": row.client_address or "",
        "record_hash": row.record_hash_hex,
        "payload": row.payload,
    }
    return rtnval


def render_audit_export(*, rows: List[Any], export_format: str) -> bytes:
    """
        Serialize readable rows as CSV (payload as a JSON column) or
        JSON Lines.

        :param rows: :class:`audit.audit_presenter.AuditRow` list.
        :param export_format: :data:`EXPORT_FORMAT_CSV` or
                              :data:`EXPORT_FORMAT_JSONL`.

        :returns: The file body.
    """
    if export_format == EXPORT_FORMAT_JSONL:
        lines = []
        for row in rows:
            lines.append(json.dumps(
                _export_row_values(row=row), sort_keys=False, default=str
            ))
        text = "\n".join(lines)
        if len(lines) > 0:
            text = text + "\n"
        rtnval = text.encode("utf-8")
        return rtnval

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(list(EXPORT_COLUMNS))
    for row in rows:
        values = _export_row_values(row=row)
        writer.writerow([
            json.dumps(values[column], sort_keys=True, default=str)
            if column == "payload" else values[column]
            for column in EXPORT_COLUMNS
        ])
    rtnval = buffer.getvalue().encode("utf-8")
    return rtnval


def handle_audit_log_export(request: Request) -> Response:
    """
        ``GET /admin/audit-logs/export`` -- the filtered audit log as a
        CSV or JSON Lines attachment, newest first (at most
        :data:`audit.audit_query.MAX_EXPORT_RECORDS` records).

        :param request: Incoming webworks request.

        :returns: The attachment, or a redirect back to the page with a
                  notice when a filter cannot match.
    """
    from ccai.pychestrate.webservice.audit.audit_query import (  # noqa: E402
        MAX_EXPORT_RECORDS,
        iter_audit_records,
    )

    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        filters = _read_filters(request=request)
        export_format = str(request.query_params.get("format", EXPORT_FORMAT_CSV) or EXPORT_FORMAT_CSV).lower()
        if export_format not in (EXPORT_FORMAT_CSV, EXPORT_FORMAT_JSONL):
            export_format = EXPORT_FORMAT_CSV

        kind_views = _list_kinds()
        audit_query, notices = _build_audit_query(
            db_session=db_session,
            filters=filters,
            known_kinds=[view.kind for view in kind_views],
            before=None,
            after=None,
        )
        if audit_query is None:
            flash.add_flash(
                session=auth.session,
                message="Nothing exported: {}".format(" ".join(notices)),
                category=flash.CATEGORY_WARNING,
            )
            response = RedirectResponse(
                url=_url_for_module.url_for(
                    "config.audit_log_list", **_filter_query_params(filters=filters)
                ),
                status_code=303,
            )
            _attach_session_to_response(response=response, session=auth.session)
            return response

        rows: List[Any] = []
        chunk: List[Any] = []
        for record in iter_audit_records(
                db_session=db_session,
                audit_query=audit_query,
                max_records=MAX_EXPORT_RECORDS):
            chunk.append(record)
            if len(chunk) >= 500:
                rows.extend(_describe_records(db_session=db_session, records=chunk))
                chunk = []
        if len(chunk) > 0:
            rows.extend(_describe_records(db_session=db_session, records=chunk))

        body = render_audit_export(rows=rows, export_format=export_format)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        if export_format == EXPORT_FORMAT_JSONL:
            content_type = "application/x-ndjson; charset=utf-8"
        else:
            content_type = "text/csv; charset=utf-8"
        headers = {
            "Content-Type": content_type,
            "Content-Disposition": 'attachment; filename="pychestrate-audit-{}.{}"'.format(
                stamp, export_format
            ),
            "Cache-Control": "no-store",
        }
        if len(rows) >= MAX_EXPORT_RECORDS:
            headers["X-Pychestrate-Export-Truncated"] = "true"
        rtnval = Response(status_code=200, headers=headers, body=body)
        return rtnval
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
    "config.audit_log_export": handle_audit_log_export,
}


def register_audit_routes(*, app: Any) -> None:
    """
        Attach the audit-log routes to a webworks app and register
        their endpoint names with the url_for shim.
    """
    for endpoint_name, relative_path, methods in _ROUTE_TABLE:
        full_path = CONFIG_PATH + relative_path
        _url_for_module.register_endpoint(
            endpoint=endpoint_name, pattern=full_path
        )
        handler = _HANDLERS_BY_ENDPOINT[endpoint_name]
        wrapped_handler = _require_admin_permission_for(
            _wrap_admin_handler_in_shell(handler),
            permission=_ROUTE_PERMISSIONS[endpoint_name],
        )
        app.attach_route(full_path, methods=list(methods))(wrapped_handler)
    return


__all__ = [
    "EXPORT_COLUMNS",
    "register_audit_routes",
    "handle_audit_log_list",
    "handle_audit_log_export",
    "render_audit_export",
]
