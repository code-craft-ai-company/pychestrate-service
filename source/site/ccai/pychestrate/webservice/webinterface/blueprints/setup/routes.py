"""
.. module:: webinterface.blueprints.setup.routes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Routes for the first-run setup wizard.

.. moduleauthor:: Code Craft AI LLC

Two pages, four handlers:

* ``GET /setup/unlock``  -- :func:`handle_unlock_form`
* ``POST /setup/unlock`` -- :func:`handle_unlock_submit`
* ``GET /setup/admin``   -- :func:`handle_admin_form`
* ``POST /setup/admin``  -- :func:`handle_admin_submit`

Unlock-session cookie
---------------------

After a successful unlock POST, the response sets a short-lived
HMAC-signed cookie ``pychestrate_setup_unlocked`` carrying
``{"exp": <unix-ts-10-min-from-now>}``. The HMAC key is the
``InitialSetup.token_hash`` row -- a server-side secret that
exists exactly while the wizard is pending and that is deleted
along with the row's normal lifecycle (the on-disk token file is
unlinked at ``mark_complete``). The admin handlers verify this
cookie before accepting the form post.

Post-completion behavior
------------------------

Every handler short-circuits to a 404 when the wizard is already
complete. The gate middleware is a no-op past completion, so a
direct hit on ``/setup/admin`` would otherwise reach this code --
returning 404 keeps the wizard one-way at the dispatcher layer.

Limitations (alpha-acceptable)
------------------------------

* No rate limiting on the unlock POST. Setup happens on a freshly
  deployed box, on an internal network, behind nginx; an online
  brute-force window of a few hours is acceptable for the alpha.
  If we ever expose a fresh deploy publicly we'll want to gate
  this behind a leaky-bucket limiter.
* No CSRF on the setup pages. The wizard runs once, on an empty
  database, before any authenticated session exists. There is no
  cross-site state to forge against.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import hashlib
import hmac
import json
import logging
import os
import re
import time

from typing import List, Any, Dict, Optional, Tuple
from urllib.parse import parse_qs

from ccai.webworks.routing.request import Request
from ccai.webworks.routing.response import (
    HTMLResponse,
    RedirectResponse,
    Response,
)

from ccai.errors.exceptions import ConfigurationError

from ccai.pychestrate.webservice.identity.setup.exceptions import (
    SetupAlreadyCompleteError,
    SetupNotInitializedError,
)
from ccai.pychestrate.webservice.identity.setup.setup_manager import (
    InitialSetupManager,
)
from ccai.pychestrate.webservice.identity.setup.setup_service import (
    ENV_RUNTIME_DIR,
    create_initial_admin,
    mark_setup_complete_in_process_cache,
)
from ccai.pychestrate.webservice.metadata import SITE_SHARED_GLOBALS
from ccai.pychestrate.webservice.webinterface.foundation import (
    templating,
)


_module_logger = logging.getLogger(__name__)


SETUP_PATH: str = "/setup"


# Unlock-session cookie. Mode is HMAC-signed payload (no encryption
# -- the payload is just an expiry stamp; nothing private).
UNLOCK_COOKIE_NAME: str = "pychestrate_setup_unlocked"
UNLOCK_COOKIE_TTL_SECONDS: int = 600
UNLOCK_COOKIE_PATH: str = SETUP_PATH


# Form validation. Mirrors UserManager's USERNAME_PATTERN (3-64
# chars, alphanum + underscore + hyphen, must start with alphanum)
# and a simplified RFC-5322 email regex.
LOGIN_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{2,63}$")
EMAIL_PATTERN = re.compile(
    r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
)
MIN_PASSWORD_LENGTH: int = 12


# Endpoint registrations -- (endpoint_name, relative_path, methods).
_ROUTE_TABLE: Tuple[Tuple[str, str, Tuple[str, ...]], ...] = (
    ("setup.unlock_form", "/unlock", ("GET",)),
    ("setup.unlock_submit", "/unlock", ("POST",)),
    ("setup.admin_form", "/admin", ("GET",)),
    ("setup.admin_submit", "/admin", ("POST",)),
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_session_factory():
    """
        Resolve the shared session factory at call time, not import
        time, so the bootstrap can install it after this module is
        imported.

        :returns: Session factory callable.
        :raises: ConfigurationError when the factory is unset.
    """
    factory = SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY
    if factory is None:
        raise ConfigurationError(
            "DATABASE_SESSION_FACTORY is unset; the runtime bootstrap"
            " did not run before the setup blueprint received a request"
        )
    rtnval = factory
    return rtnval


def _resolve_runtime_dir() -> str:
    """
        Read :data:`ENV_RUNTIME_DIR` at call time. Falls back to a
        harmless placeholder when unset (the manager constructor
        demands a non-empty value but the read paths used here do
        not create files).

        :returns: Runtime directory path.
    """
    raw = os.environ.get(ENV_RUNTIME_DIR, None)
    if raw is None or len(raw) == 0:
        return "/tmp"
    rtnval = raw
    return rtnval


def _open_manager(*, db_session) -> InitialSetupManager:
    """
        Construct an :class:`InitialSetupManager` bound to a
        caller-supplied session.

        :param db_session: Open SQLAlchemy session.

        :returns: Manager instance.
    """
    rtnval = InitialSetupManager(
        db_session=db_session, runtime_dir=_resolve_runtime_dir()
    )
    return rtnval


def _is_already_complete() -> bool:
    """
        Cheap "is the wizard already finished?" predicate. Opens
        a short-lived session, returns True iff the row's
        ``completed_at`` is set. False when the row does not exist
        yet (the bootstrap has not run).

        :returns: True iff setup is finished.
    """
    factory = _resolve_session_factory()
    db_session = factory()
    try:
        manager = _open_manager(db_session=db_session)
        rtnval = manager.is_complete()
    finally:
        db_session.close()
    return rtnval


def _build_404_response() -> Response:
    """
        Build a 404 Response for setup routes hit after completion.

        :returns: HTMLResponse with a 404 body.
    """
    from ccai.pychestrate.webservice.webinterface.foundation.templating import (  # noqa: E402
        render_template_response,
    )
    from ccai.pychestrate.webservice.webinterface.site_shell.error_pages import (  # noqa: E402
        CHROMELESS_ERROR_TEMPLATE,
    )
    try:
        rtnval = render_template_response(
            template_name=CHROMELESS_ERROR_TEMPLATE,
            context={
                "status_code": 404,
                "title": "Setup is already complete",
                "message": (
                    "The first-run setup wizard has been completed and"
                    " its pages are no longer available. Sign in to"
                    " continue."
                ),
            },
            status_code=404,
        )
    except Exception:
        # No templating environment (very early boot): fall back to a
        # minimal but well-formed document.
        body = (
            "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
            "<title>Not Found</title></head><body>"
            "<h1>404 Not Found</h1>"
            "<p>The setup wizard has already been completed.</p>"
            "</body></html>"
        )
        rtnval = HTMLResponse(content=body, status_code=404)
    return rtnval


def _parse_form_or_empty(*, request: Request) -> Dict[str, str]:
    """
        Parse the request body as form-encoded data via webworks'
        ``Request.form()`` method, which is the canonical entry
        point. Returns an empty dict on decode failure or
        non-form body so handler validation logic can branch on
        missing fields rather than catching exceptions.

        :param request: Webworks request.

        :returns: Dict of form fields. Empty on parse failure.
    """
    try:
        parsed = request.form()
    except Exception:
        return {}
    if isinstance(parsed, dict) is False:
        return {}
    rtnval: Dict[str, str] = {}
    for key, value in parsed.items():
        # webworks' Request.form() collapses multi-value keys to
        # the first value -- the wizard has no multi-valued forms
        # so a flat str-to-str dict is correct.
        rtnval[str(key)] = str(value)
    return rtnval


# ---------------------------------------------------------------------------
# Unlock-session cookie helpers
# ---------------------------------------------------------------------------


def _hmac_key_for_unlock(*, manager: InitialSetupManager) -> bytes:
    """
        HMAC key for the unlock-session cookie. Bound to the
        token_hash on the singleton row -- a server-side secret
        that exists exactly while setup is pending. After
        completion the cookie cannot be replayed against a fresh
        deploy.

        :param manager: Configured manager.

        :returns: Key bytes.
        :raises: SetupNotInitializedError when the row is missing.
    """
    row = manager.get_state()
    if row is None:
        raise SetupNotInitializedError(
            "system_initial_setup row is missing; bootstrap did not run"
        )
    rtnval = bytes(row.token_hash)
    return rtnval


def _build_unlock_cookie_value(*, manager: InitialSetupManager) -> str:
    """
        Mint a fresh HMAC-signed unlock-session cookie value with
        an expiry 10 minutes in the future. Format:

            <base64url(payload_json)>.<hex(hmac_sha256)>

        The payload is just the expiry stamp; the cookie carries
        no authority other than "this browser unlocked recently".

        :param manager: Configured manager.

        :returns: Cookie value string.
    """
    import base64

    expires_at = int(time.time()) + UNLOCK_COOKIE_TTL_SECONDS
    payload = {"exp": expires_at}
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode(
        "utf-8"
    )
    payload_b64 = base64.urlsafe_b64encode(payload_bytes).rstrip(b"=")

    key = _hmac_key_for_unlock(manager=manager)
    sig = hmac.new(key, payload_b64, hashlib.sha256).hexdigest()

    rtnval = "{}.{}".format(payload_b64.decode("ascii"), sig)
    return rtnval


def _verify_unlock_cookie_value(
        *, value: str, manager: InitialSetupManager
    ) -> bool:
    """
        Verify an unlock-session cookie. Returns True iff the HMAC
        matches the current row's token_hash AND the payload's
        ``exp`` is in the future.

        :param value: Cookie value (or ``None``).
        :param manager: Configured manager.

        :returns: True on valid + unexpired.
    """
    if value is None or len(value) == 0:
        return False

    parts = value.split(".", 1)
    if len(parts) != 2:
        return False

    payload_b64, supplied_sig = parts
    if len(payload_b64) == 0 or len(supplied_sig) == 0:
        return False

    try:
        key = _hmac_key_for_unlock(manager=manager)
    except SetupNotInitializedError:
        return False

    expected_sig = hmac.new(
        key, payload_b64.encode("ascii"), hashlib.sha256
    ).hexdigest()
    if hmac.compare_digest(expected_sig, supplied_sig) is False:
        return False

    import base64

    try:
        # Re-pad for base64 decode.
        padded = payload_b64 + ("=" * ((4 - len(payload_b64) % 4) % 4))
        payload_bytes = base64.urlsafe_b64decode(padded.encode("ascii"))
        payload = json.loads(payload_bytes.decode("utf-8"))
    except (ValueError, json.JSONDecodeError):
        return False

    expires_at = payload.get("exp", None)
    if isinstance(expires_at, (int, float)) is False:
        return False
    if expires_at <= int(time.time()):
        return False

    return True


def _attach_unlock_cookie(
        *, response: Response, manager: InitialSetupManager
    ) -> None:
    """
        Set the unlock-session cookie on a response. ``HttpOnly``,
        ``SameSite=Strict``, ``Path=/setup``. Not ``Secure`` (the
        alpha may run plaintext behind nginx; production deploys
        with TLS would set ``Secure`` via reverse-proxy header
        rewriting).

        :param response: Webworks response to attach to.
        :param manager: Configured manager.

        :returns: None.
    """
    cookie_value = _build_unlock_cookie_value(manager=manager)
    response.set_cookie(
        name=UNLOCK_COOKIE_NAME,
        value=cookie_value,
        max_age=UNLOCK_COOKIE_TTL_SECONDS,
        path=UNLOCK_COOKIE_PATH,
        httponly=True,
        samesite="strict",
    )
    return


def _clear_unlock_cookie(*, response: Response) -> None:
    """
        Drop the unlock-session cookie. Used after admin creation
        succeeds so a back-button-to-/setup/admin POST does not
        replay.

        :param response: Webworks response.

        :returns: None.
    """
    response.set_cookie(
        name=UNLOCK_COOKIE_NAME,
        value="",
        max_age=0,
        path=UNLOCK_COOKIE_PATH,
        httponly=True,
        samesite="strict",
    )
    return


def _read_unlock_cookie(*, request: Request) -> Optional[str]:
    """
        Read the unlock-session cookie value from a request.

        :param request: Webworks request.

        :returns: Cookie value or ``None``.
    """
    try:
        rtnval = request.cookies.get(UNLOCK_COOKIE_NAME, None)
    except Exception:
        return None
    return rtnval


# ---------------------------------------------------------------------------
# Form validation
# ---------------------------------------------------------------------------


def _validate_admin_form(
        *, login_name: str, email: str, password: str,
        password_confirm: str, display_name: str
    ) -> Optional[str]:
    """
        Return the first user-facing validation error message, or
        ``None`` when the form is valid.

        :param login_name: Submitted login.
        :param email: Submitted email.
        :param password: Submitted password.
        :param password_confirm: Re-typed password.
        :param display_name: Submitted display name.

        :returns: Error message string or ``None``.
    """
    problems = _collect_admin_form_errors(
        login_name=login_name,
        email=email,
        password=password,
        password_confirm=password_confirm,
        display_name=display_name,
    )
    if len(problems) == 0:
        return None
    rtnval = " ".join(problems)
    return rtnval


def _collect_admin_form_errors(
        *, login_name: str, email: str, password: str,
        password_confirm: str, display_name: str
    ) -> List[str]:
    """
        Return every user-facing validation problem with the
        first-admin form, so one submission reports all of them.

        :returns: List of messages (empty when the form is valid).
    """
    field_errors = _collect_admin_field_errors(
        login_name=login_name,
        email=email,
        password=password,
        password_confirm=password_confirm,
        display_name=display_name,
    )
    rtnval = list(field_errors.values())
    return rtnval


def _collect_admin_field_errors(
        *, login_name: str, email: str, password: str,
        password_confirm: str, display_name: str
    ) -> Dict[str, str]:
    """
        Return every validation problem with the first-admin form,
        keyed by the name of the field it belongs to and in the
        form's field order, so the page can show each message under
        its field and focus the first one.

        :returns: Field name to message (empty when the form is valid).
    """
    rtnval: Dict[str, str] = {}
    if LOGIN_NAME_PATTERN.match(login_name) is None:
        rtnval["login_name"] = (
            "Login must be 3-64 characters, alphanumeric with"
            " optional underscore or hyphen, starting with a letter"
            " or digit."
        )
    if EMAIL_PATTERN.match(email) is None:
        rtnval["email"] = "Email address looks invalid."
    if len(display_name) == 0:
        rtnval["display_name"] = "Display name is required."
    if len(password) < MIN_PASSWORD_LENGTH:
        rtnval["password"] = "Password must be at least {} characters.".format(
            MIN_PASSWORD_LENGTH
        )
    if password != password_confirm:
        rtnval["password_confirm"] = "Password and confirmation do not match."
    return rtnval
# ---------------------------------------------------------------------------
# Handlers -- /setup/unlock
# ---------------------------------------------------------------------------


def handle_unlock_form(request: Request) -> Response:
    """
        ``GET /setup/unlock`` -- render the token-paste page.

        :param request: Webworks request.

        :returns: HTMLResponse with the unlock template.
    """
    if _is_already_complete() is True:
        return _build_404_response()

    factory = _resolve_session_factory()
    db_session = factory()
    try:
        manager = _open_manager(db_session=db_session)
        token_path = manager.token_path
    finally:
        db_session.close()

    context = {
        "token_path": token_path,
        "error": None,
    }
    rtnval = templating.render_template_response(
        template_name="setup/unlock.html",
        context=context,
    )
    return rtnval


def handle_unlock_submit(request: Request) -> Response:
    """
        ``POST /setup/unlock`` -- verify the pasted token, set the
        unlock-session cookie, redirect to ``/setup/admin``.

        :param request: Webworks request.

        :returns: RedirectResponse on success, HTMLResponse on
                  failure.
    """
    if _is_already_complete() is True:
        return _build_404_response()

    form = _parse_form_or_empty(request=request)
    submitted_token = str(form.get("token", "")).strip()

    factory = _resolve_session_factory()
    db_session = factory()
    try:
        manager = _open_manager(db_session=db_session)
        token_path = manager.token_path

        if len(submitted_token) == 0:
            context = {
                "token_path": token_path,
                "error": "Token is required.",
            }
            rtnval = templating.render_template_response(
                template_name="setup/unlock.html",
                context=context,
                status_code=400,
            )
            return rtnval

        try:
            ok = manager.verify_token(plaintext=submitted_token)
        except SetupNotInitializedError:
            _module_logger.error(
                "pychestrate.setup.unlock_submit no_row -- bootstrap"
                " did not run"
            )
            ok = False
        except SetupAlreadyCompleteError:
            return _build_404_response()

        if ok is False:
            _module_logger.warning(
                "pychestrate.setup.unlock_submit.failed token_path=%s",
                token_path,
            )
            context = {
                "token_path": token_path,
                "error": "Invalid token. Re-read the token from the"
                         " path shown above and try again.",
            }
            rtnval = templating.render_template_response(
                template_name="setup/unlock.html",
                context=context,
                status_code=401,
            )
            return rtnval

        _module_logger.info(
            "pychestrate.setup.unlock_submit.success"
        )
        response = RedirectResponse(
            url="{}/admin".format(SETUP_PATH), status_code=303
        )
        _attach_unlock_cookie(response=response, manager=manager)
        return response
    finally:
        db_session.close()


# ---------------------------------------------------------------------------
# Handlers -- /setup/admin
# ---------------------------------------------------------------------------


def handle_admin_form(request: Request) -> Response:
    """
        ``GET /setup/admin`` -- render the admin-creation form.
        Requires a valid unlock-session cookie; otherwise redirects
        back to ``/setup/unlock``.

        :param request: Webworks request.

        :returns: HTMLResponse or RedirectResponse.
    """
    if _is_already_complete() is True:
        return _build_404_response()

    factory = _resolve_session_factory()
    db_session = factory()
    try:
        manager = _open_manager(db_session=db_session)
        cookie_value = _read_unlock_cookie(request=request)
        if _verify_unlock_cookie_value(
                value=cookie_value, manager=manager
            ) is False:
            rtnval = RedirectResponse(
                url="{}/unlock".format(SETUP_PATH), status_code=303
            )
            return rtnval
    finally:
        db_session.close()

    context = {
        "form_values": {
            "login_name": "",
            "email": "",
            "display_name": "",
        },
        "min_password_length": MIN_PASSWORD_LENGTH,
        "error": None,
        "errors": [],
        "field_errors": {},
        "first_invalid": None,
    }
    rtnval = templating.render_template_response(
        template_name="setup/admin.html",
        context=context,
    )
    return rtnval


def handle_admin_submit(request: Request) -> Response:
    """
        ``POST /setup/admin`` -- validate, create the admin, mark
        setup complete, drop the unlock cookie, redirect to
        ``/login``.

        :param request: Webworks request.

        :returns: RedirectResponse on success, HTMLResponse on
                  failure.
    """
    try:
        return _handle_admin_submit_inner(request=request)
    except BaseException:
        import traceback
        _module_logger.error(
            "pychestrate.setup.admin_submit.crashed exc=%s",
            traceback.format_exc(),
        )
        raise


def _handle_admin_submit_inner(*, request: Request) -> Response:
    if _is_already_complete() is True:
        return _build_404_response()

    form = _parse_form_or_empty(request=request)
    login_name = str(form.get("login_name", "")).strip()
    email = str(form.get("email", "")).strip()
    display_name = str(form.get("display_name", "")).strip()
    password = str(form.get("password", ""))
    password_confirm = str(form.get("password_confirm", ""))

    factory = _resolve_session_factory()
    db_session = factory()
    try:
        manager = _open_manager(db_session=db_session)

        cookie_value = _read_unlock_cookie(request=request)
        if _verify_unlock_cookie_value(
                value=cookie_value, manager=manager
            ) is False:
            rtnval = RedirectResponse(
                url="{}/unlock".format(SETUP_PATH), status_code=303
            )
            return rtnval

        field_errors = _collect_admin_field_errors(
            login_name=login_name,
            email=email,
            password=password,
            password_confirm=password_confirm,
            display_name=display_name,
        )
        validation_errors = list(field_errors.values())
        validation_error = " ".join(validation_errors) if len(validation_errors) > 0 else None
        if validation_error is not None:
            context = {
                "form_values": {
                    "login_name": login_name,
                    "email": email,
                    "display_name": display_name,
                },
                "min_password_length": MIN_PASSWORD_LENGTH,
                "error": validation_error,
                "errors": validation_errors,
                "field_errors": field_errors,
                "first_invalid": next(iter(field_errors)),
            }
            rtnval = templating.render_template_response(
                template_name="setup/admin.html",
                context=context,
                status_code=400,
            )
            return rtnval

        try:
            admin_user_id_str = create_initial_admin(
                session_factory=factory,
                login_name=login_name,
                primary_email=email,
                password=password,
                display_name=display_name,
            )
        except ConfigurationError as exc:
            _module_logger.warning(
                "pychestrate.setup.admin_submit.create_failed reason=%s",
                str(exc),
            )
            context = {
                "form_values": {
                    "login_name": login_name,
                    "email": email,
                    "display_name": display_name,
                },
                "min_password_length": MIN_PASSWORD_LENGTH,
                "error": (
                    "Could not create the admin account. The login or"
                    " email may already be in use."
                ),
                "field_errors": {},
                "first_invalid": "login_name",
            }
            rtnval = templating.render_template_response(
                template_name="setup/admin.html",
                context=context,
                status_code=400,
            )
            return rtnval

        # Re-open a session for the completion stamp + manager
        # operations -- ``create_initial_admin`` opened + closed
        # its own session via the factory.
        completion_session = factory()
        try:
            completion_manager = _open_manager(
                db_session=completion_session
            )
            import uuid as _uuid

            admin_uuid = _uuid.UUID(admin_user_id_str)
            completion_manager.mark_complete(
                completed_by_user_id=admin_uuid
            )
            completion_session.commit()
        except BaseException:
            completion_session.rollback()
            raise
        finally:
            completion_session.close()

        mark_setup_complete_in_process_cache()
        _module_logger.info(
            "pychestrate.setup.admin_submit.success user_id=%s",
            admin_user_id_str,
        )

        response = RedirectResponse(url="/login", status_code=303)
        # Tell the new administrator the account exists (audit U-6):
        # queue an info flash on a fresh UI session cookie so the
        # sign-in page can show it.
        try:
            from ccai.pychestrate.webservice.webinterface.foundation import flash as _flash  # noqa: E402
            from ccai.pychestrate.webservice.webinterface.blueprints.config.routes import (  # noqa: E402
                _attach_session_to_response,
            )
            fresh_session = {}
            _flash.add_flash(
                session=fresh_session,
                message="Administrator account created. Sign in to continue.",
                category=_flash.CATEGORY_SUCCESS,
            )
            _attach_session_to_response(response=response, session=fresh_session)
        except Exception:
            pass
        _clear_unlock_cookie(response=response)
        return response
    finally:
        db_session.close()


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


_HANDLERS_BY_ENDPOINT: Dict[str, Any] = {
    "setup.unlock_form": handle_unlock_form,
    "setup.unlock_submit": handle_unlock_submit,
    "setup.admin_form": handle_admin_form,
    "setup.admin_submit": handle_admin_submit,
}


def register_setup_routes(*, app: Any) -> None:
    """
        Attach the setup wizard routes to a webworks application.
        Must be called from ``register_service_extensions`` BEFORE
        ``app.startup()``.

        :param app: WebWorks application.

        :returns: None.
    """
    for endpoint_name, relative_path, methods in _ROUTE_TABLE:
        full_path = SETUP_PATH + relative_path
        handler = _HANDLERS_BY_ENDPOINT[endpoint_name]
        app.attach_route(full_path, methods=list(methods))(handler)

    _module_logger.info(
        "pychestrate.setup.routes_registered count=%d",
        len(_ROUTE_TABLE),
    )
    return


__all__ = [
    "MIN_PASSWORD_LENGTH",
    "SETUP_PATH",
    "UNLOCK_COOKIE_NAME",
    "UNLOCK_COOKIE_TTL_SECONDS",
    "handle_admin_form",
    "handle_admin_submit",
    "handle_unlock_form",
    "handle_unlock_submit",
    "register_setup_routes",
]
