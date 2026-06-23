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
                                               the secret is shown
                                               exactly once via a
                                               flash message.
* ``POST /admin/enrollment-tokens/{token_id}/revoke``
                                            -- revoke an active
                                               token.

The handlers call the enrollment service functions
(:func:`issue_enrollment_token` / :func:`list_enrollment_tokens` /
:func:`revoke_enrollment_token`) directly -- the same pattern the
sibling admin blueprints (variables / resources) use to call their
managers, rather than proxying the REST surface from the browser.

Server-side ``system:resources.manage`` permission gating is the
security boundary; the sidebar entry registered in
``pyc-admin-bundle/index.ts`` gates on the same key for UX only.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Callable, Dict

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
    _require_permission_or_redirect,
    _resolve_authenticated_request,
    _wrap_admin_handler_in_shell,
)


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


# Default token lifetime offered by the mint form when the operator
# leaves the TTL field blank: 24 hours.
_DEFAULT_TTL_SECONDS = 86400


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
        deny_response = _require_permission_or_redirect(
            auth=auth,
            permission=_ADMIN_PERMISSION,
            deny_redirect_url=_url_for_module.url_for(
                "config.dashboard"
            ),
        )
        if deny_response is not None:
            return deny_response

        tokens = _service_list_tokens(db_session=db_session)

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="config.enrollment_token_list",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["tokens"] = tokens
        context["default_ttl_seconds"] = _DEFAULT_TTL_SECONDS

        response = _render(
            template_name="config/enrollment/list.html",
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


def handle_enrollment_token_mint(request: Request) -> Response:
    """
        ``POST /admin/enrollment-tokens/mint`` -- issue a new
        enrollment token and redirect back to the list. The minted
        secret is surfaced exactly once via a success flash.
        Admin-gated on ``system:resources.manage``.

        :param request: Incoming webworks request.

        :returns: RedirectResponse to the token list.
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
                "config.dashboard"
            ),
        )
        if deny_response is not None:
            return deny_response

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
        ttl_seconds = _coerce_ttl_seconds(
            raw=single_form.get("ttl_seconds", None)
        )
        one_shot_raw = str(single_form.get("one_shot", "")).strip()
        one_shot = one_shot_raw in ("1", "true", "on", "yes")

        if len(project_id) == 0 or len(pod_name) == 0:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for(
                    "config.enrollment_token_list"
                ),
                message="Project ID and pod name are both required.",
                category=flash.CATEGORY_ERROR,
            )
            return response

        try:
            issued = _service_issue_token(
                db_session=db_session,
                project_id=project_id,
                pod_name=pod_name,
                ttl_seconds=ttl_seconds,
                one_shot=one_shot,
                issued_by=auth.user_id,
            )
        except ValueError as exc:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for(
                    "config.enrollment_token_list"
                ),
                message="Invalid token request: {}".format(str(exc)),
                category=flash.CATEGORY_ERROR,
            )
            return response
        except Exception as exc:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for(
                    "config.enrollment_token_list"
                ),
                message="Error minting token: {}".format(str(exc)),
                category=flash.CATEGORY_ERROR,
            )
            return response

        success_lines = [
            "Token {} minted for pod '{}'.".format(
                issued.token_id, pod_name
            ),
            "Secret (shown once): {}".format(issued.secret),
        ]
        response = _redirect_with_flash(
            session=auth.session,
            url=_url_for_module.url_for(
                "config.enrollment_token_list"
            ),
            message=" ".join(success_lines),
            category=flash.CATEGORY_SUCCESS,
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
        deny_response = _require_permission_or_redirect(
            auth=auth,
            permission=_ADMIN_PERMISSION,
            deny_redirect_url=_url_for_module.url_for(
                "config.dashboard"
            ),
        )
        if deny_response is not None:
            return deny_response

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
        except Exception as exc:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for(
                    "config.enrollment_token_list"
                ),
                message="Error revoking token: {}".format(str(exc)),
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
        wrapped_handler = _wrap_admin_handler_in_shell(handler)
        app.attach_route(full_path, methods=list(methods))(wrapped_handler)
    return


__all__ = [
    "register_enrollment_admin_routes",
    "handle_enrollment_token_list",
    "handle_enrollment_token_mint",
    "handle_enrollment_token_revoke",
]
