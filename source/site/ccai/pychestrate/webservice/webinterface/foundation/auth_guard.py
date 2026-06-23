"""
.. module:: webinterface.foundation.auth_guard
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Login + CSRF guards for the consumer web UI.

.. moduleauthor:: Code Craft AI LLC

Webworks routes are plain functions registered via
``app.attach_route(...)`` rather than decorated handlers. This
module supplies login and CSRF gating as composable guards that
return a redirect / problem response when the gate fails:

* :func:`is_authenticated` -- pure predicate over a session
  dict. Checks that both ``'user_id'`` and ``'session_token'``
  are present.

* :func:`require_login_or_redirect` -- handler-side guard. Reads
  the session, returns ``None`` when authenticated, returns a
  webworks :class:`RedirectResponse` to the configured login
  URL otherwise. The handler short-circuits on a non-None
  return.

* :func:`enforce_csrf_or_redirect` -- read the form-encoded
  body, pull the CSRF token, verify against the session's
  expected token. Returns ``None`` on success, returns a
  redirect to the referrer / fallback on failure.

The guards do **not** close over the session-cookie write-back
-- that's the handler's responsibility because some success
paths want to mutate the session (e.g. login itself stores
user_id) and some don't.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Dict, Optional

from ccai.webworks.routing.response import RedirectResponse, Response

from ccai.pychestrate.webservice.webinterface.foundation import (
    csrf as _csrf_helpers,
    flash as _flash_helpers,
)


SESSION_USER_ID_KEY: str = "user_id"
SESSION_TOKEN_KEY: str = "session_token"


def is_authenticated(*, session: Dict[str, Any]) -> bool:
    """
        Return True when the session dict carries both a
        ``user_id`` and a ``session_token``.

        :param session: Session dict (from
                        :func:`cookie_session.read_session_from_request`).

        :returns: Bool.
    """
    user_id = session.get(SESSION_USER_ID_KEY, None)
    session_token = session.get(SESSION_TOKEN_KEY, None)
    if not isinstance(user_id, str) or len(user_id) == 0:
        return False
    if not isinstance(session_token, str) or len(session_token) == 0:
        return False
    return True


def require_login_or_redirect(
        *,
        session: Dict[str, Any],
        login_url: str,
        flash_message: Optional[str] = None,
        flash_category: str = _flash_helpers.CATEGORY_WARNING
    ) -> Optional[Response]:
    """
        Return a redirect response to ``login_url`` when the
        session is unauthenticated; return ``None`` otherwise.
        Optionally queues a flash message on the session before
        redirecting (the caller writes the session cookie on the
        redirect response).

        :param session: Session dict.
        :param login_url: Path to redirect anonymous requests to.
        :param flash_message: Optional message to flash before
                              redirecting (e.g. "Please log in to
                              access this page.").
        :param flash_category: Flash category.

        :returns: :class:`RedirectResponse` (302) when not
                  authenticated, ``None`` otherwise.
    """
    if is_authenticated(session=session) is True:
        return None

    if flash_message is not None and len(flash_message) > 0:
        _flash_helpers.add_flash(
            session=session,
            message=flash_message,
            category=flash_category,
        )

    rtnval = RedirectResponse(url=login_url, status_code=302)
    return rtnval


def enforce_csrf_or_redirect(
        *,
        form: Optional[Dict[str, Any]],
        session: Dict[str, Any],
        fallback_url: str,
        flash_message: Optional[str] = "Invalid request. Please try again.",
        flash_category: str = _flash_helpers.CATEGORY_ERROR
    ) -> Optional[Response]:
    """
        Validate the form-submitted CSRF token against the
        session's expected token. Returns ``None`` on a valid
        token (the handler proceeds); returns a redirect response
        to ``fallback_url`` on failure (callers typically pass
        the referrer so the user lands back on the form).

        :param form: Decoded form dict (from
                     ``request.form()``). ``None`` is treated as
                     "no token" and fails.
        :param session: Session dict.
        :param fallback_url: Where to redirect on failure (the
                             handler typically passes
                             ``request.headers.get("Referer") or
                             "/config/dashboard"`` so the user
                             returns to the page they came from).
        :param flash_message: Optional message to flash on
                              failure.
        :param flash_category: Flash category.

        :returns: :class:`RedirectResponse` (302) on bad token,
                  ``None`` on valid.
    """
    submitted = _csrf_helpers.extract_token_from_form(form=form or {})
    expected = session.get(_csrf_helpers.SESSION_KEY, None)

    if _csrf_helpers.is_token_valid(
        submitted=submitted, expected=expected
    ) is True:
        return None

    if flash_message is not None and len(flash_message) > 0:
        _flash_helpers.add_flash(
            session=session,
            message=flash_message,
            category=flash_category,
        )

    rtnval = RedirectResponse(url=fallback_url, status_code=302)
    return rtnval


__all__ = [
    "SESSION_USER_ID_KEY",
    "SESSION_TOKEN_KEY",
    "is_authenticated",
    "require_login_or_redirect",
    "enforce_csrf_or_redirect",
]
