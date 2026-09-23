"""
.. module:: webinterface.blueprints.config.routes_password
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Sign-in-free password pages: set a password from an invite
               or reset link, and replace a temporary password before
               signing in (audit ADM-04).

.. moduleauthor:: Code Craft AI LLC

* ``GET|POST /password/set/{token}`` -- the page an invite or reset
  link opens. The user chooses a password (the shared password policy
  applies); the link is then used up, an invited account becomes
  active, and the user signs in with the new password.
* ``GET|POST /password/change-required`` -- where the sign-in form
  sends a user whose administrator set a temporary password. The
  account gets no session until the user proves the temporary password
  and chooses their own; they are then signed in.

Both pages render chromeless (like ``/login``), carry a CSRF token in
the anonymous session cookie, and are sent with ``Cache-Control:
no-store`` and ``Referrer-Policy: no-referrer`` so the link secret does
not leak through caches or the Referer header.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import time

from typing import Any, Callable, Dict, List, Optional

from ccai.webworks.routing.request import Request
from ccai.webworks.routing.response import RedirectResponse, Response

from ccai.pychestrate.webservice.security.auth.password_policy import (
    PasswordPolicyError,
    password_policy_template_context,
)
from ccai.pychestrate.webservice.webinterface.foundation import (
    auth_guard,
    csrf,
    flash,
    url_for as _url_for_module,
)
from ccai.pychestrate.webservice.webinterface.blueprints.config import routes as _config_routes
from ccai.pychestrate.webservice.webinterface.htmlui.next_validator import (
    NextValidator,
)


_ROUTE_TABLE = (
    ("config.password_link", "/password/set/{token}", ("GET", "POST")),
    ("config.password_change_required", "/password/change-required", ("GET", "POST")),
)

#: Cookie-session key holding a pending forced change: the account, its
#: login name, an expiry (epoch seconds) and the post-sign-in target.
SESSION_PENDING_CHANGE_KEY: str = "password_change_pending"

#: How long the sign-in form's hand-off to the change page stays valid.
PENDING_CHANGE_TTL_SECONDS: int = 600

_SENSITIVE_PAGE_HEADERS: Dict[str, str] = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
}


# ---------------------------------------------------------------------------
# Lazy-import seams
# ---------------------------------------------------------------------------


def _password_lifecycle() -> Any:
    """
        The password lifecycle service module. Lazy-import seam.
    """
    from ccai.pychestrate.webservice.security.auth import (  # noqa: E402
        password_lifecycle,
    )
    return password_lifecycle


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _client_ip(*, request: Request) -> str:
    """
        The client address (trusted-proxy aware) used to key the
        sign-in back-off.
    """
    from ccai.pychestrate.webservice.security.auth.client_address import (  # noqa: E402
        resolve_client_address,
    )
    rtnval = resolve_client_address(request=request)
    return rtnval


def _user_agent(*, request: Request) -> str:
    from ccai.pychestrate.webservice.security.auth.client_address import (  # noqa: E402
        request_user_agent,
    )
    rtnval = request_user_agent(request=request)
    return rtnval


def _render_page(
        *,
        template_name: str,
        session: Dict[str, Any],
        context_values: Dict[str, Any],
        status_code: int = 200
    ) -> Response:
    """
        Render a chromeless password page with the policy hint, the
        anonymous session's CSRF token, and the no-store headers.
    """
    flashes = flash.consume_flashes(session=session)
    context = _config_routes._build_default_template_context(
        session=session,
        request_endpoint="config.password_link",
        flashes=flashes,
        csrf_token=_config_routes._ensure_session_csrf_token(session=session),
    )
    context.update(password_policy_template_context())
    context["problems"] = []
    context.update(context_values)
    response = _config_routes._render(
        template_name=template_name, context=context, status_code=status_code
    )
    for name, value in _SENSITIVE_PAGE_HEADERS.items():
        response._headers[name] = value
    _config_routes._attach_session_to_response(response=response, session=session)
    return response


def _describe_problems(*, exc: Exception) -> List[str]:
    """
        The sentences to show for a refused password.
    """
    if isinstance(exc, PasswordPolicyError) is True:
        return list(exc.problems)
    message = getattr(exc, "message", None)
    if message is None:
        message = str(exc)
    rtnval = [str(message)]
    return rtnval


def _sign_in(
        *,
        request: Request,
        session: Dict[str, Any],
        db_session: Any,
        login_name: str,
        password: str
    ) -> bool:
    """
        Open a session for the user who just set their password and
        store it on the cookie session (the same keys the sign-in form
        sets).

        :returns: True when signed in.
    """
    security_manager = _config_routes._build_security_manager(db_session=db_session)
    auth_request = _config_routes._build_auth_request(
        username=login_name,
        password=password,
        client_ip=_client_ip(request=request),
        user_agent=_user_agent(request=request),
    )
    try:
        auth_response = security_manager.authenticate(auth_request)
    except Exception:
        return False
    session[auth_guard.SESSION_USER_ID_KEY] = auth_response.user_id
    session["username"] = auth_response.username
    session[auth_guard.SESSION_TOKEN_KEY] = auth_response.token
    if auth_response.csrf_token is not None and len(auth_response.csrf_token) > 0:
        session[csrf.SESSION_KEY] = auth_response.csrf_token
    return True


# ---------------------------------------------------------------------------
# Forced change hand-off from the sign-in form
# ---------------------------------------------------------------------------


def begin_forced_password_change(
        *,
        session: Dict[str, Any],
        error: Exception,
        next_candidate: Optional[str]
    ) -> Optional[Response]:
    """
        Called by the sign-in handler with a failed ``authenticate``'s
        exception. When the failure is a required password change,
        remember the account on the (signed) cookie session and send
        the browser to the change page; otherwise return None and the
        sign-in form shows its usual error.

        :param session: The anonymous cookie session.
        :param error: The exception ``authenticate`` raised.
        :param next_candidate: The sign-in form's ``next`` target.

        :returns: A redirect, or None.
    """
    from ccai.pychestrate.webservice.webinterface.blueprints.config.auth_adapter import (  # noqa: E402
        PasswordChangeRequiredError,
    )

    if isinstance(error, PasswordChangeRequiredError) is False:
        return None
    validator = NextValidator(fallback_target="/")
    session[SESSION_PENDING_CHANGE_KEY] = {
        "user_id": error.user_id,
        "login_name": error.login_name,
        "expires_at": int(time.time()) + PENDING_CHANGE_TTL_SECONDS,
        "next": validator.resolve_safe_target(candidate=next_candidate, fallback="/"),
    }
    response = RedirectResponse(
        url=_url_for_module.url_for("config.password_change_required"),
        status_code=303,
    )
    _config_routes._attach_session_to_response(response=response, session=session)
    return response


def _pending_change(*, session: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
        The unexpired pending forced change on the cookie session.
    """
    pending = session.get(SESSION_PENDING_CHANGE_KEY, None)
    if isinstance(pending, dict) is False:
        return None
    try:
        expires_at = int(pending.get("expires_at", 0))
    except (TypeError, ValueError):
        return None
    if expires_at <= int(time.time()):
        return None
    if len(str(pending.get("user_id", ""))) == 0:
        return None
    return pending


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def handle_password_link(request: Request) -> Response:
    """
        ``GET|POST /password/set/{token}`` -- set a password from an
        invite or reset link.

        :param request: Incoming webworks request.

        :returns: The form, the invalid-link page, or a redirect to the
                  sign-in page once the password is set.
    """
    lifecycle = _password_lifecycle()
    session = _config_routes._read_session(request=request)
    secret = str(request.path_params.get("token", ""))
    template_name = "config/password_link.html"

    db_session = _config_routes._resolve_db_session()
    try:
        try:
            token_row, user = lifecycle.find_usable_link(db_session=db_session, secret=secret)
        except lifecycle.PasswordLinkInvalidError as exc:
            response = _render_page(
                template_name=template_name,
                session=session,
                context_values={"link_valid": False, "invalid_message": exc.message},
                status_code=404,
            )
            return response

        link_values = {
            "link_valid": True,
            "login_name": user.login_name,
            "purpose": token_row.purpose.value,
            "form_action": request.path,
        }

        if request.method.upper() != "POST":
            response = _render_page(
                template_name=template_name, session=session, context_values=link_values
            )
            return response

        form = _config_routes._parse_form_or_empty(request=request)
        csrf_redirect = auth_guard.enforce_csrf_or_redirect(
            form=form,
            session=session,
            fallback_url=request.path,
            flash_message="This form expired. Please try again.",
        )
        if csrf_redirect is not None:
            _config_routes._attach_session_to_response(response=csrf_redirect, session=session)
            return csrf_redirect

        new_password = str(form.get("password", ""))
        confirm = str(form.get("password_confirm", ""))
        if new_password != confirm:
            values = dict(link_values)
            values["problems"] = ["The passwords do not match."]
            response = _render_page(
                template_name=template_name, session=session,
                context_values=values, status_code=400,
            )
            return response

        try:
            redeemed = lifecycle.redeem_password_link(
                db_session=db_session, secret=secret, new_password=new_password
            )
            db_session.commit()
        except (PasswordPolicyError, lifecycle.PasswordLifecycleError) as exc:
            db_session.rollback()
            if isinstance(exc, lifecycle.PasswordLinkInvalidError) is True:
                response = _render_page(
                    template_name=template_name,
                    session=session,
                    context_values={"link_valid": False, "invalid_message": exc.message},
                    status_code=404,
                )
                return response
            values = dict(link_values)
            values["problems"] = _describe_problems(exc=exc)
            response = _render_page(
                template_name=template_name, session=session,
                context_values=values, status_code=400,
            )
            return response

        flash.add_flash(
            session=session,
            message="Your password is set. Sign in as {} with your new password.".format(
                redeemed.login_name
            ),
            category=flash.CATEGORY_SUCCESS,
        )
        response = RedirectResponse(
            url=_url_for_module.url_for("config.login"), status_code=303
        )
        _config_routes._attach_session_to_response(response=response, session=session)
        return response
    finally:
        try:
            db_session.close()
        except Exception:
            pass


def handle_password_change_required(request: Request) -> Response:
    """
        ``GET|POST /password/change-required`` -- replace a temporary
        password before signing in.

        :param request: Incoming webworks request.

        :returns: The form, or a redirect (to the target after a
                  successful change, to sign-in when nothing is
                  pending).
    """
    lifecycle = _password_lifecycle()
    session = _config_routes._read_session(request=request)
    template_name = "config/password_change_required.html"

    pending = _pending_change(session=session)
    if pending is None:
        session.pop(SESSION_PENDING_CHANGE_KEY, None)
        flash.add_flash(
            session=session,
            message="Sign in again to change your password.",
            category=flash.CATEGORY_INFO,
        )
        response = RedirectResponse(
            url=_url_for_module.url_for("config.login"), status_code=303
        )
        _config_routes._attach_session_to_response(response=response, session=session)
        return response

    page_values = {"login_name": pending.get("login_name", "")}

    if request.method.upper() != "POST":
        response = _render_page(
            template_name=template_name, session=session, context_values=page_values
        )
        return response

    form = _config_routes._parse_form_or_empty(request=request)
    csrf_redirect = auth_guard.enforce_csrf_or_redirect(
        form=form,
        session=session,
        fallback_url=_url_for_module.url_for("config.password_change_required"),
        flash_message="This form expired. Please try again.",
    )
    if csrf_redirect is not None:
        _config_routes._attach_session_to_response(response=csrf_redirect, session=session)
        return csrf_redirect

    current_password = str(form.get("current_password", ""))
    new_password = str(form.get("password", ""))
    confirm = str(form.get("password_confirm", ""))
    if new_password != confirm:
        values = dict(page_values)
        values["problems"] = ["The new passwords do not match."]
        response = _render_page(
            template_name=template_name, session=session,
            context_values=values, status_code=400,
        )
        return response

    db_session = _config_routes._resolve_db_session()
    try:
        try:
            lifecycle.change_own_password(
                db_session=db_session,
                user_id=pending["user_id"],
                current_password=current_password,
                new_password=new_password,
                keep_session_id=None,
                forced=True,
                source_ip=_client_ip(request=request),
            )
            db_session.commit()
        except (PasswordPolicyError, lifecycle.PasswordLifecycleError) as exc:
            db_session.rollback()
            values = dict(page_values)
            values["problems"] = _describe_problems(exc=exc)
            response = _render_page(
                template_name=template_name, session=session,
                context_values=values, status_code=400,
            )
            return response

        session.pop(SESSION_PENDING_CHANGE_KEY, None)
        signed_in = _sign_in(
            request=request,
            session=session,
            db_session=db_session,
            login_name=str(pending.get("login_name", "")),
            password=new_password,
        )
        if signed_in is False:
            flash.add_flash(
                session=session,
                message="Your password is changed. Sign in with your new password.",
                category=flash.CATEGORY_SUCCESS,
            )
            response = RedirectResponse(
                url=_url_for_module.url_for("config.login"), status_code=303
            )
            _config_routes._attach_session_to_response(response=response, session=session)
            return response

        response = RedirectResponse(url=str(pending.get("next", "/")) or "/", status_code=303)
        _config_routes._attach_session_to_response(response=response, session=session)
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
    "config.password_link": handle_password_link,
    "config.password_change_required": handle_password_change_required,
}


def register_password_routes(*, app: Any) -> None:
    """
        Attach the password pages to a webworks app. They need no
        sign-in (the link secret, or the sign-in form's hand-off, is
        the credential) and render chromeless.

        :param app: WebWorks application.

        :returns: None.
    """
    for endpoint_name, full_path, methods in _ROUTE_TABLE:
        _url_for_module.register_endpoint(endpoint=endpoint_name, pattern=full_path)
        handler = _HANDLERS_BY_ENDPOINT[endpoint_name]
        app.attach_route(full_path, methods=list(methods))(handler)
    return


__all__ = [
    "PENDING_CHANGE_TTL_SECONDS",
    "SESSION_PENDING_CHANGE_KEY",
    "begin_forced_password_change",
    "handle_password_change_required",
    "handle_password_link",
    "register_password_routes",
]
