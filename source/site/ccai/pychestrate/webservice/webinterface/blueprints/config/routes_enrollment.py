"""
.. module:: webinterface.blueprints.config.routes_enrollment
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-native admin UI for /admin/enrollment-tokens
               -- mint / list / revoke client enrollment tokens.

.. moduleauthor:: Code Craft AI LLC

Today client enrollment tokens are mintable / listable / revocable
only via the REST surface at ``/api/v1/enrollment-tokens`` (see
:mod:`clients.restapi.v1.enrollment_routes`). This module adds an
operator-facing admin page so a logged-in admin can manage tokens
from the UI.

Three routes, all under the ``/admin`` prefix and rendered as
shell-wrapped fragments per ``9-site-shell`` PR4 strategy A:

* ``GET  /admin/enrollment-tokens``         -- list every token
                                               (id, project, pod,
                                               status, issue +
                                               expiry timestamps)
                                               plus the mint form.
* ``POST /admin/enrollment-tokens/mint``    -- issue a new token;
                                               the response renders
                                               the page directly
                                               with a one-time
                                               result panel showing
                                               the secret and the
                                               exact
                                               ``pychestrate-client``
                                               enrollment commands
                                               (the secret is never
                                               written into the
                                               flash cookie).
* ``POST /admin/enrollment-tokens/{token_id}/revoke``
                                            -- revoke an active
                                               token.

The handlers call the enrollment service functions
(:func:`issue_enrollment_token` / :func:`list_enrollment_tokens` /
:func:`revoke_enrollment_token`) directly -- the same pattern the
sibling admin blueprints (variables / resources) use to call their
managers, rather than proxying the REST surface from the browser.

Server-side ``system:resources.manage`` permission gating is the
security boundary: every route is registered through
:func:`routes._require_admin_permission_for`, so a viewer without the
permission gets the shared 403 page naming it (it used to redirect to
the dashboard with a flash -- audit ADM-21). The sidebar entry
registered in ``pyc-admin-bundle/index.ts`` gates on the same key for
UX only.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import logging
import shlex

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from ccai.webworks.routing.request import Request
from ccai.webworks.routing.response import Response

from ccai.pychestrate.webservice.webinterface.foundation import (
    auth_guard,
    flash,
    url_for as _url_for_module,
)
from ccai.pychestrate.webservice.webinterface.blueprints.config.routes import (
    CONFIG_PATH,
    _attach_session_to_response,
    _build_default_template_context,
    _parse_form_or_empty,
    _redirect_with_flash,
    _render,
    _require_admin_permission_for,
    _resolve_authenticated_request,
    _wrap_admin_handler_in_shell,
)


_module_logger = logging.getLogger(__name__)


_ROUTE_TABLE = (
    ("config.enrollment_token_list", "/enrollment-tokens", ("GET",)),
    (
        "config.enrollment_token_mint",
        "/enrollment-tokens/mint",
        ("POST",),
    ),
    (
        "config.enrollment_token_revoke",
        "/enrollment-tokens/{token_id}/revoke",
        ("POST",),
    ),
)


# The enrollment surface has no dedicated ``system:clients.enroll``
# permission key in the core permission pack -- token administration
# is part of the operations-admin surface. ``system:resources.manage``
# is the operator-admin permission the sibling resources blueprint
# guards its mutating routes with; the enrollment admin page reuses
# it so a single operator role unlocks both surfaces.
_ADMIN_PERMISSION = "system:resources.manage"

# Permission each route enforces server-side (see
# ``routes._require_admin_permission_for``).
_ROUTE_PERMISSIONS = {
    "config.enrollment_token_list": _ADMIN_PERMISSION,
    "config.enrollment_token_mint": _ADMIN_PERMISSION,
    "config.enrollment_token_revoke": _ADMIN_PERMISSION,
}


# Default token lifetime offered by the mint form when the operator
# leaves the TTL field blank: 24 hours.
_DEFAULT_TTL_SECONDS = 86400

# ``clients_enrollment_tokens.pod_name`` is VARCHAR(128).
_MAX_POD_LABEL_LENGTH = 128

PROJECT_SOURCE_UI: str = "ui"
PROJECT_SOURCE_API: str = "api"


@dataclass(frozen=True)
class ProjectChoice:
    """
        One entry of the mint form's project picker.

        The token's scope is a project's registry UUID. Every project
        has one -- web-UI projects included, through the project bridge
        (:mod:`projects.bridge`).

        :param value: The project UUID the form submits.
        :param label: What the admin sees (project name).
        :param detail: Secondary text (slug or web-UI id).
        :param source: :data:`PROJECT_SOURCE_UI` or
                       :data:`PROJECT_SOURCE_API`.
    """
    value: str
    label: str
    detail: str
    source: str


# ---------------------------------------------------------------------------
# Lazy-import builder seams (test-patchable)
# ---------------------------------------------------------------------------


def _service_list_tokens(*, db_session: Any) -> Any:
    """
        Call :func:`list_enrollment_tokens` against an open db
        session. Lazy-imports the service so unit tests can patch
        this seam without importing the enrollment service module.

        :param db_session: Open SQLAlchemy session.

        :returns: List of :class:`TokenView`.
    """
    from ccai.pychestrate.webservice.clients.enrollment.service import (  # noqa: E402
        list_enrollment_tokens,
    )
    rtnval = list_enrollment_tokens(db_session=db_session)
    return rtnval


def _list_project_choices(*, db_session: Any) -> List[ProjectChoice]:
    """
        Every project a token can be scoped to, under its registry UUID
        (the project a pod enrolled with the token belongs to). Since the
        project bridge (PRJ-06) every web-UI project has a registry
        project; one not linked yet (the startup reconcile has not run) is
        offered under the UUID its registry project will get.
        Test-patchable seam.

        :param db_session: Open SQLAlchemy session.

        :returns: Choices sorted by name.
    """
    from sqlalchemy.exc import OperationalError  # noqa: E402

    from ccai.pychestrate.core.orm import Project as UiProject  # noqa: E402
    from ccai.pychestrate.webservice.projects.legacy_identity import (  # noqa: E402
        derived_project_uuid,
    )
    from ccai.pychestrate.webservice.projects.models import (  # noqa: E402
        Project as RegistryProject,
        ProjectState,
    )

    rtnval: List[ProjectChoice] = []
    linked_ui_ids = set()

    savepoint = db_session.begin_nested()
    try:
        registry_rows = (
            db_session.query(RegistryProject)
            .filter(RegistryProject.state == ProjectState.ACTIVE)
            .all()
        )
        savepoint.commit()
    except OperationalError:
        # The project registry's table is missing or behind the models
        # (a database that has not run the latest migration): offer the
        # web-UI projects rather than failing the whole page.
        savepoint.rollback()
        _module_logger.warning(
            "pychestrate.ui.enrollment.project_registry_unavailable",
            exc_info=True,
        )
        registry_rows = []
    for row in registry_rows:
        display_name = row.display_name if row.display_name is not None else ""
        label = display_name if len(display_name.strip()) > 0 else row.slug
        if row.legacy_proj_id is not None:
            linked_ui_ids.add(int(row.legacy_proj_id))
        rtnval.append(ProjectChoice(
            value=str(row.project_id),
            label=label,
            detail=row.slug,
            source=PROJECT_SOURCE_UI,
        ))

    savepoint = db_session.begin_nested()
    try:
        ui_rows = db_session.query(UiProject.id, UiProject.name).all()
        savepoint.commit()
    except OperationalError:
        # A development database created without the legacy tables.
        savepoint.rollback()
        ui_rows = []
    for project_id, project_name in ui_rows:
        if int(project_id) in linked_ui_ids:
            continue
        rtnval.append(ProjectChoice(
            value=derived_project_uuid(project_id),
            label=str(project_name),
            detail="web UI project #{}".format(project_id),
            source=PROJECT_SOURCE_UI,
        ))

    rtnval.sort(key=lambda choice: (choice.label.lower(), choice.detail))
    return rtnval


def _service_issue_token(
        *,
        db_session: Any,
        project_id: str,
        pod_name: str,
        ttl_seconds: int,
        one_shot: bool,
        issued_by: str
    ) -> Any:
    """
        Call :func:`issue_enrollment_token`. Lazy-imports the
        service.

        :param db_session: Open SQLAlchemy session.
        :param project_id: Scope project UUID.
        :param pod_name: Pod scope label.
        :param ttl_seconds: Token lifetime in seconds.
        :param one_shot: Whether the token is consumed on first
                         redemption.
        :param issued_by: Acting admin user UUID.

        :returns: :class:`IssuedEnrollmentToken`.
    """
    from ccai.pychestrate.webservice.clients.enrollment.service import (  # noqa: E402
        issue_enrollment_token,
    )
    rtnval = issue_enrollment_token(
        db_session=db_session,
        project_id=project_id,
        pod_name=pod_name,
        ttl_seconds=ttl_seconds,
        one_shot=one_shot,
        issued_by=issued_by,
    )
    return rtnval


def _service_revoke_token(
        *, db_session: Any, token_id: str, actor_user_id: str
    ) -> None:
    """
        Call :func:`revoke_enrollment_token`. Lazy-imports the
        service.

        :param db_session: Open SQLAlchemy session.
        :param token_id: Target token UUID.
        :param actor_user_id: Acting admin user UUID.

        :returns: None.
    """
    from ccai.pychestrate.webservice.clients.enrollment.service import (  # noqa: E402
        revoke_enrollment_token,
    )
    revoke_enrollment_token(
        db_session=db_session,
        token_id=token_id,
        actor_user_id=actor_user_id,
    )
    return


# ---------------------------------------------------------------------------
# Local helpers
# ---------------------------------------------------------------------------


def _coerce_ttl_seconds(*, raw: Any) -> int:
    """
        Coerce the mint form's ``ttl_seconds`` field to a positive
        integer, falling back to :data:`_DEFAULT_TTL_SECONDS` when
        the field is blank / non-numeric / non-positive.

        :param raw: Form-submitted ``ttl_seconds`` value.

        :returns: A positive integer TTL in seconds.
    """
    if raw is None:
        return _DEFAULT_TTL_SECONDS
    text = str(raw).strip()
    if len(text) == 0:
        return _DEFAULT_TTL_SECONDS
    try:
        parsed = int(text)
    except (TypeError, ValueError):
        return _DEFAULT_TTL_SECONDS
    if parsed <= 0:
        return _DEFAULT_TTL_SECONDS
    rtnval = parsed
    return rtnval


def _resolve_service_base_url(*, request: Request) -> str:
    """
        Build this service's browser-facing base URL (scheme +
        authority, no trailing slash) from the incoming request,
        for the copy-paste ``pychestrate-client enroll
        --service-url`` command. Prefers the ``Host`` header (it
        carries the authority the browser actually used, including
        any non-default port); falls back to the request's
        host/port fields, then to a placeholder the operator must
        fill in.

        :param request: Incoming webworks request.

        :returns: Base URL string (e.g. ``"https://pyc.example:8443"``).
    """
    scheme = getattr(request, "scheme", None)
    if isinstance(scheme, str) is False or len(scheme) == 0:
        scheme = "http"

    host_header = None
    headers = getattr(request, "headers", None)
    if headers is not None:
        try:
            host_header = headers.get("host", None)
        except Exception:
            host_header = None

    if host_header is not None and len(str(host_header)) > 0:
        rtnval = "{}://{}".format(scheme, host_header)
        return rtnval

    host = getattr(request, "host", None)
    if isinstance(host, str) is True and len(host) > 0:
        port = getattr(request, "port", None)
        if isinstance(port, int) is True and port not in (0, 80, 443):
            rtnval = "{}://{}:{}".format(scheme, host, port)
            return rtnval
        rtnval = "{}://{}".format(scheme, host)
        return rtnval

    rtnval = "{}://<service-host>".format(scheme)
    return rtnval


def _describe_enrollment_failure(*, exc: Exception, action: str) -> str:
    """
        Build the operator-facing flash message for a failed
        enrollment-token operation. :class:`ValueError` messages
        are curated service validation text and surfaced by the
        callers directly; this helper handles everything else by
        logging server-side (with traceback) and returning a
        generic message so raw internal exception text never
        reaches the browser.

        :param exc: The exception raised by the operation.
        :param action: Present-participle action label (e.g.
                       ``"minting"``) used in the message.

        :returns: Flash message string.
    """
    _module_logger.exception(
        "Unexpected %s while %s enrollment token.",
        type(exc).__name__,
        action,
    )
    rtnval = (
        "Error {} token: an unexpected internal error occurred."
        " The details have been logged."
    ).format(action)
    return rtnval


def _canonical_uuid_text(*, raw: Any) -> Optional[str]:
    """
        Canonical lower-case text of a submitted UUID, or None when
        the value is not a UUID.

        :param raw: Submitted value.

        :returns: Canonical UUID string or None.
    """
    import uuid as _uuid  # noqa: E402

    if raw is None:
        return None
    try:
        rtnval = str(_uuid.UUID(str(raw).strip()))
    except (TypeError, ValueError, AttributeError):
        return None
    return rtnval


def _empty_mint_form() -> Dict[str, Any]:
    """
        Initial values of the mint form.

        :returns: Dict with ``project_id``, ``pod_name``,
                  ``ttl_seconds`` and ``one_shot``.
    """
    rtnval = {
        "project_id": "",
        "pod_name": "",
        "ttl_seconds": "",
        "one_shot": True,
    }
    return rtnval


def _validate_mint_form(
        *,
        mint_form: Dict[str, Any],
        choices: List[ProjectChoice]
    ) -> Dict[str, str]:
    """
        Field-level validation of the mint form. The project must be
        one the picker offered (so a made-up UUID or a web-UI integer
        id can no longer reach the token table), and the pod label
        must be present and fit the column.

        :param mint_form: Submitted values (see :func:`_empty_mint_form`).
        :param choices: The picker's choices.

        :returns: ``{field: message}``; empty when the form is valid.
    """
    errors: Dict[str, str] = {}

    submitted_project = str(mint_form.get("project_id", "")).strip()
    known_values = set(choice.value for choice in choices)
    if len(submitted_project) == 0:
        errors["project_id"] = "Choose the project the client will serve."
    else:
        canonical = _canonical_uuid_text(raw=submitted_project)
        if canonical is None or canonical not in known_values:
            errors["project_id"] = (
                "That project does not exist. Choose one from the list."
            )

    pod_label = str(mint_form.get("pod_name", "")).strip()
    if len(pod_label) == 0:
        errors["pod_name"] = "Enter the pod label the client will enroll as."
    elif len(pod_label) > _MAX_POD_LABEL_LENGTH:
        errors["pod_name"] = "The pod label must be {} characters or fewer.".format(
            _MAX_POD_LABEL_LENGTH
        )

    rtnval = errors
    return rtnval


def _project_choice_groups(*, choices: List[ProjectChoice]) -> List[Dict[str, Any]]:
    """
        Split the picker's choices into the ``<optgroup>`` sections the
        template renders: web-UI projects, then REST-registry projects
        (shown with their slug). Empty sections are omitted.

        :param choices: The picker's choices.

        :returns: List of ``{"label", "choices", "show_detail"}`` dicts.
    """
    ui_choices = [c for c in choices if c.source == PROJECT_SOURCE_UI]
    api_choices = [c for c in choices if c.source == PROJECT_SOURCE_API]
    rtnval: List[Dict[str, Any]] = []
    if len(ui_choices) > 0:
        rtnval.append({
            "label": "Projects",
            "choices": ui_choices,
            "show_detail": False,
        })
    if len(api_choices) > 0:
        rtnval.append({
            "label": "Projects created through the API or CLI",
            "choices": api_choices,
            "show_detail": True,
        })
    return rtnval


def _project_labels_by_value(*, choices: List[ProjectChoice]) -> Dict[str, str]:
    """
        Map each choice's UUID to its display label, for showing
        project names (not raw UUIDs) in the token table.

        :param choices: The picker's choices.

        :returns: ``{uuid: label}``.
    """
    rtnval: Dict[str, str] = {}
    for choice in choices:
        rtnval[choice.value] = choice.label
    return rtnval


#: A second mint of the same project and pod inside this many seconds is
#: taken to be a reload or a double click.
DUPLICATE_MINT_WINDOW_SECONDS = 30


def _parse_iso(*, text: Optional[str]) -> Optional[datetime]:
    """An aware UTC datetime from an ISO string, or None when it is empty or malformed."""
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _recently_minted_token(*, db_session: Any, project_id: str, pod_name: str) -> Optional[Any]:
    """
        A still-pending token for this project and pod that was issued
        within :data:`DUPLICATE_MINT_WINDOW_SECONDS`.

        :returns: ``(token id, seconds since it was issued)`` or None.
    """
    now = datetime.now(timezone.utc)
    for token in _service_list_tokens(db_session=db_session):
        if token.pod_name != pod_name or token.status.value != "PENDING":
            continue
        if str(token.project_id) != str(project_id):
            continue
        issued = _parse_iso(text=token.issued_at_iso)
        if issued is None:
            continue
        age = (now - issued).total_seconds()
        if 0 <= age <= DUPLICATE_MINT_WINDOW_SECONDS:
            return (str(token.token_id), int(age))
    return None


def _token_rows(*, tokens: List[Any]) -> List[Dict[str, Any]]:
    """
        The list's rows, newest first, with real datetimes (the list shows
        them in the viewer's zone) instead of the service's ISO strings.
    """
    rows = []
    for token in tokens:
        rows.append({
            "token_id": str(token.token_id),
            "project_id": str(token.project_id),
            "pod_name": token.pod_name,
            "status": token.status,
            "one_shot": token.one_shot,
            "issued_at": _parse_iso(text=token.issued_at_iso),
            "expires_at": _parse_iso(text=token.expires_at_iso),
            "redeemed_at": _parse_iso(text=token.redeemed_at_iso),
            "redeemed_by_client_id": token.redeemed_by_client_id,
        })
    rows.sort(key=lambda row: row["issued_at"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return rows


def _render_token_page(
        *,
        auth: Any,
        db_session: Any,
        status_code: int = 200,
        minted: Optional[Dict[str, Any]] = None,
        errors: Optional[Dict[str, str]] = None,
        mint_form: Optional[Dict[str, Any]] = None
    ) -> Response:
    """
        Render the token page: mint form (with the project picker and
        any field errors / kept values), the one-time result panel
        after a mint, and the token list.

        :param auth: Authenticated request resolution.
        :param db_session: Open SQLAlchemy session.
        :param status_code: HTTP status of the page.
        :param minted: One-time result panel values, or None.
        :param errors: ``{field: message}`` for the mint form.
        :param mint_form: Values to pre-fill the mint form with.

        :returns: The rendered page.
    """
    tokens = _service_list_tokens(db_session=db_session)
    choices = _list_project_choices(db_session=db_session)

    flashes = flash.consume_flashes(session=auth.session)
    context = _build_default_template_context(
        session=auth.session,
        request_endpoint="config.enrollment_token_list",
        flashes=flashes,
        csrf_token=auth.csrf_token,
    )
    context["tokens"] = _token_rows(tokens=tokens)
    context["default_ttl_seconds"] = _DEFAULT_TTL_SECONDS
    context["project_choices"] = choices
    context["project_choice_groups"] = _project_choice_groups(choices=choices)
    context["project_labels"] = _project_labels_by_value(choices=choices)
    context["errors"] = errors if errors is not None else {}
    context["mint_form"] = mint_form if mint_form is not None else _empty_mint_form()
    if minted is not None:
        context["minted"] = minted

    response = _render(
        template_name="config/enrollment/list.html",
        context=context,
        status_code=status_code,
    )
    _attach_session_to_response(response=response, session=auth.session)
    return response


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def handle_enrollment_token_list(request: Request) -> Response:
    """
        ``GET /admin/enrollment-tokens`` -- render the enrollment
        token management page: the full token list plus the mint
        form. Admin-gated on ``system:resources.manage``.

        :param request: Incoming webworks request.

        :returns: HTMLResponse with the token list, or a
                  RedirectResponse on an unauthenticated /
                  unauthorized request.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        response = _render_token_page(auth=auth, db_session=db_session)
        return response
    finally:
        try:
            db_session.close()
        except Exception:
            pass


def handle_enrollment_token_mint(request: Request) -> Response:
    """
        ``POST /admin/enrollment-tokens/mint`` -- issue a new
        enrollment token. On success the page renders directly
        (no redirect) with a one-time result panel carrying the
        secret and the exact ``pychestrate-client`` commands; the
        secret is never written into the flash cookie. Failures
        redirect back to the list with an error flash.
        Admin-gated on ``system:resources.manage``.

        :param request: Incoming webworks request.

        :returns: HTMLResponse with the result panel on success,
                  RedirectResponse to the token list on failure.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        single_form = _parse_form_or_empty(request=request)

        csrf_redirect = auth_guard.enforce_csrf_or_redirect(
            form=single_form,
            session=auth.session,
            fallback_url=_url_for_module.url_for(
                "config.enrollment_token_list"
            ),
        )
        if csrf_redirect is not None:
            _attach_session_to_response(
                response=csrf_redirect, session=auth.session
            )
            return csrf_redirect

        project_id = str(single_form.get("project_id", "")).strip()
        pod_name = str(single_form.get("pod_name", "")).strip()
        ttl_raw = single_form.get("ttl_seconds", None)
        ttl_seconds = _coerce_ttl_seconds(raw=ttl_raw)
        one_shot_raw = str(single_form.get("one_shot", "")).strip()
        one_shot = one_shot_raw in ("1", "true", "on", "yes")

        # What the admin typed survives every failure below: the page
        # re-renders with these values and the field-level errors.
        mint_form = {
            "project_id": project_id,
            "pod_name": pod_name,
            "ttl_seconds": str(ttl_raw).strip() if ttl_raw is not None else "",
            "one_shot": one_shot,
        }

        choices = _list_project_choices(db_session=db_session)
        errors = _validate_mint_form(mint_form=mint_form, choices=choices)
        if len(errors) > 0:
            response = _render_token_page(
                auth=auth,
                db_session=db_session,
                status_code=400,
                errors=errors,
                mint_form=mint_form,
            )
            return response

        repeated = _recently_minted_token(
            db_session=db_session,
            project_id=_canonical_uuid_text(raw=project_id),
            pod_name=pod_name,
        )
        if repeated is not None:
            # The result page is a POST response, so reloading it sends the
            # form again. A token for the same project and pod made a
            # moment ago is that (or a double click): say so instead of
            # minting a second one whose secret nobody will see.
            flash.add_flash(
                session=auth.session,
                message=(
                    'A token for pod "{}" was minted {} seconds ago (token {}).'
                    " This looks like a reload or a double click, so no second"
                    " token was made. Its secret was shown once. If you did not"
                    " save it, revoke that token below and mint another."
                ).format(pod_name, repeated[1], repeated[0][:8]),
                category=flash.CATEGORY_WARNING,
            )
            response = _render_token_page(
                auth=auth, db_session=db_session, status_code=409,
                mint_form=mint_form,
            )
            return response

        try:
            issued = _service_issue_token(
                db_session=db_session,
                project_id=_canonical_uuid_text(raw=project_id),
                pod_name=pod_name,
                ttl_seconds=ttl_seconds,
                one_shot=one_shot,
                issued_by=auth.user_id,
            )
        except ValueError as exc:
            db_session.rollback()
            flash.add_flash(
                session=auth.session,
                message="Invalid token request: {}".format(str(exc)),
                category=flash.CATEGORY_ERROR,
            )
            response = _render_token_page(
                auth=auth,
                db_session=db_session,
                status_code=400,
                mint_form=mint_form,
            )
            return response
        except Exception as exc:
            db_session.rollback()
            flash.add_flash(
                session=auth.session,
                message=_describe_enrollment_failure(
                    exc=exc, action="minting"
                ),
                category=flash.CATEGORY_ERROR,
            )
            response = _render_token_page(
                auth=auth,
                db_session=db_session,
                status_code=500,
                mint_form=mint_form,
            )
            return response

        # Render the page directly (no redirect) with a one-time
        # result panel. The secret must not ride in the flash
        # cookie: a redirect would write it into the signed session
        # cookie and squeeze it into a one-line alert, so the POST
        # response itself is the single place the secret appears.
        service_base_url = _resolve_service_base_url(request=request)
        # Each value is quoted for a shell: a pod label with a space or a
        # "!" pasted into a terminal must still be one argument.
        enroll_command = (
            "pychestrate-client enroll --service-url {} --token {}"
            " --name {}"
        ).format(
            shlex.quote(service_base_url), shlex.quote(issued.secret),
            shlex.quote(pod_name),
        )

        minted = {
            "token_id": issued.token_id,
            "pod_name": pod_name,
            "project_label": _project_labels_by_value(choices=choices).get(
                issued.project_id, issued.project_id
            ),
            "secret": issued.secret,
            "enroll_command": enroll_command,
            "run_command": "pychestrate-client run",
            "warnings": list(issued.warnings),
        }
        response = _render_token_page(
            auth=auth, db_session=db_session, minted=minted
        )
        return response
    finally:
        try:
            db_session.close()
        except Exception:
            pass


def handle_enrollment_token_revoke(request: Request) -> Response:
    """
        ``POST /admin/enrollment-tokens/{token_id}/revoke`` --
        revoke an active enrollment token and redirect back to the
        list. Admin-gated on ``system:resources.manage``.

        :param request: Incoming webworks request.

        :returns: RedirectResponse to the token list.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        token_id = str(request.path_params.get("token_id", "")).strip()
        single_form = _parse_form_or_empty(request=request)

        csrf_redirect = auth_guard.enforce_csrf_or_redirect(
            form=single_form,
            session=auth.session,
            fallback_url=_url_for_module.url_for(
                "config.enrollment_token_list"
            ),
        )
        if csrf_redirect is not None:
            _attach_session_to_response(
                response=csrf_redirect, session=auth.session
            )
            return csrf_redirect

        if len(token_id) == 0:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for(
                    "config.enrollment_token_list"
                ),
                message="No token id supplied.",
                category=flash.CATEGORY_ERROR,
            )
            return response

        try:
            _service_revoke_token(
                db_session=db_session,
                token_id=token_id,
                actor_user_id=auth.user_id,
            )
        except ValueError as exc:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for(
                    "config.enrollment_token_list"
                ),
                message="Error revoking token: {}".format(str(exc)),
                category=flash.CATEGORY_ERROR,
            )
            return response
        except Exception as exc:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for(
                    "config.enrollment_token_list"
                ),
                message=_describe_enrollment_failure(
                    exc=exc, action="revoking"
                ),
                category=flash.CATEGORY_ERROR,
            )
            return response

        response = _redirect_with_flash(
            session=auth.session,
            url=_url_for_module.url_for("config.enrollment_token_list"),
            message="Token {} revoked.".format(token_id),
            category=flash.CATEGORY_SUCCESS,
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
    "config.enrollment_token_list": handle_enrollment_token_list,
    "config.enrollment_token_mint": handle_enrollment_token_mint,
    "config.enrollment_token_revoke": handle_enrollment_token_revoke,
}


def register_enrollment_admin_routes(*, app: Any) -> None:
    """
        Attach the enrollment-token admin routes to a webworks app
        and register their endpoint names with the url_for shim.
        Each handler is wrapped so its rendered fragment is injected
        into the site-shell main slot (PR4 strategy A).

        :param app: WebWorks application built by
                    ``establish_webapp_persona``.

        :returns: None.
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
    "register_enrollment_admin_routes",
    "handle_enrollment_token_list",
    "handle_enrollment_token_mint",
    "handle_enrollment_token_revoke",
]
