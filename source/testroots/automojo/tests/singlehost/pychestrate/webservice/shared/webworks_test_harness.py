"""
.. module:: webworks_test_harness
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Shared fakes / builders for webworks handler-level
               tests across the pychestrate webservice tree.

.. moduleauthor:: Automation Mojo LLC

Why this module exists
----------------------

The phase10 / phase12 webworks-route tests each carry roughly
the same boilerplate:

* a ``_FakeApp`` whose ``attach_route`` captures
  ``(path, methods, handler)`` triples so the test can assert the
  documented route matrix.
* a ``_FakeRequest`` providing whichever subset of
  ``method`` / ``path`` / ``path_params`` / ``query_params`` /
  ``cookies`` / ``headers`` / ``body`` / ``json`` / ``form`` /
  ``db_session`` the handler under test happens to touch.
* a small bag of session / CSRF / flash mocks the auth-guard
  layer reads from.
* a ``_StubJinjaEnvironment`` + ``_StubTemplate`` pair so the
  test can assert which template name was looked up and which
  context dict the handler passed in -- without rendering HTML.

Each test file used to redeclare 80-500 lines of these classes,
which made new feature PRs (release templates, #277) feel
prohibitively expensive: copy ~500 lines or ship unit-only
tests.

What's here
-----------

* :func:`make_fake_app` -- returns a :class:`FakeApp` whose
  ``attach_route(path, methods=...)`` decorator captures the
  registration. The recorded triples are accessible via
  ``app.calls`` and the typed helpers on :class:`FakeApp`.
* :func:`make_fake_request` -- builds a duck-typed
  ``Request``-shaped object that the webworks handlers accept.
  By default we construct a real
  :class:`automojo.webworks.routing.request.Request` (which
  already provides ``path`` / ``method`` / ``headers`` /
  ``query_params`` / ``cookies`` / ``body`` / ``json`` /
  ``form`` / ``path_params``) and tack on the handler-side
  attributes the routes reach for (``db_session``,
  ``security_manager``).
* :func:`make_fake_session` -- a dict shaped the way
  :mod:`webinterface.foundation.auth_guard` expects:
  ``user_id`` + ``session_token`` + ``csrf_token`` + ``perms``.
* :func:`make_fake_security_manager` -- a configurable stub for
  the security-manager surface the REST routes read.
* :func:`capture_renders` -- a context manager that swaps in a
  stub Jinja env so ``env.get_template(name).render(ctx)`` calls
  are captured by name + context.

When you need behaviour the harness does not provide, build the
mock locally in the test file -- the harness is intentionally
narrow. The :file:`README.md` in this directory has more
guidance on when to extend versus when to inline.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import contextlib
import os

from typing import (
    Any,
    Callable,
    Dict,
    Iterator,
    List,
    Optional,
    Tuple,
)
from urllib.parse import urlencode

from automojo.webworks.routing.request import Request


# ---------------------------------------------------------------------------
# Constants -- mirror webinterface.foundation.auth_guard / csrf so the
# session shape stays in sync with what handlers actually read.
# ---------------------------------------------------------------------------


SESSION_USER_ID_KEY: str = "user_id"
SESSION_TOKEN_KEY: str = "session_token"
SESSION_CSRF_KEY: str = "csrf_token"
SESSION_PERMS_KEY: str = "perms"


# ---------------------------------------------------------------------------
# FakeApp
# ---------------------------------------------------------------------------


RouteCall = Tuple[str, Tuple[str, ...], Callable[..., Any]]


class FakeApp:
    """
        Captures ``attach_route`` calls so tests can assert the
        registered route matrix without spinning up a real
        webworks app.

        Usage::

            app = make_fake_app()
            register_my_routes(app=app)
            assert app.route_pairs() == {("/x", ("GET",))}
    """

    def __init__(self) -> None:
        self.calls: List[RouteCall] = []
        return

    def attach_route(
            self,
            path: str,
            methods: Optional[List[str]] = None
        ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """
            Decorator-factory mirroring the real webworks
            ``App.attach_route``. The decorated function is
            captured along with the path + resolved methods tuple
            and is returned unchanged so the registrar's import
            graph still works.

            :param path: The route path template (e.g.
                         ``"/api/v1/auth/logout"``).
            :param methods: Optional list of HTTP methods; defaults
                            to ``["GET"]`` when omitted.

            :returns: A decorator that records the registration.
        """
        resolved_methods = tuple(
            methods if methods is not None else ["GET"]
        )

        def decorator(
                func: Callable[..., Any]
            ) -> Callable[..., Any]:
            self.calls.append((path, resolved_methods, func))
            rtnval = func
            return rtnval

        rtnval = decorator
        return rtnval

    def route_pairs(self) -> List[Tuple[str, Tuple[str, ...]]]:
        """
            All recorded ``(path, methods)`` pairs in registration
            order.

            :returns: List of ``(path, methods_tuple)`` pairs.
        """
        rtnval = [(path, methods) for path, methods, _ in self.calls]
        return rtnval

    def find_handler(
            self,
            *,
            path: str,
            method: str
        ) -> Optional[Callable[..., Any]]:
        """
            Locate the captured handler for the given
            ``(path, method)`` pair.

            :param path: Route path to look up.
            :param method: HTTP method to look up.

            :returns: The recorded handler, or ``None`` when no
                      registration matches.
        """
        method_uc = method.upper()
        for recorded_path, methods, handler in self.calls:
            if recorded_path != path:
                continue
            if method_uc not in methods:
                continue
            rtnval = handler
            return rtnval
        return None


def make_fake_app() -> FakeApp:
    """
        Build a fresh :class:`FakeApp`.

        :returns: An empty :class:`FakeApp` instance.
    """
    rtnval = FakeApp()
    return rtnval


# ---------------------------------------------------------------------------
# FakeRequest
# ---------------------------------------------------------------------------


_FORM_CONTENT_TYPE: str = "application/x-www-form-urlencoded"
_JSON_CONTENT_TYPE: str = "application/json"
_UI_COOKIE_NAME: str = "pychestrate_ui_session"


def _encode_form(form: Dict[str, Any]) -> bytes:
    """
        URL-encode a form dict for the request body.

        :param form: Mapping of field-name to value.

        :returns: URL-encoded body bytes.
    """
    encoded = urlencode(form, doseq=True)
    rtnval = encoded.encode("utf-8")
    return rtnval


def _encode_json(payload: Any) -> bytes:
    """
        UTF-8 encode a JSON payload for the request body.

        :param payload: The Python object to serialize.

        :returns: JSON-encoded body bytes.
    """
    import json as _json

    body_text = _json.dumps(payload)
    rtnval = body_text.encode("utf-8")
    return rtnval


def _encode_query(query_params: Dict[str, Any]) -> bytes:
    """
        URL-encode a query-params dict.

        :param query_params: Mapping of key to value (or list of
                             values).

        :returns: Encoded query-string bytes (no leading ``?``).
    """
    encoded = urlencode(query_params, doseq=True)
    rtnval = encoded.encode("utf-8")
    return rtnval


def make_fake_request(
        *,
        method: str = "GET",
        path: str = "/",
        query_params: Optional[Dict[str, Any]] = None,
        form: Optional[Dict[str, Any]] = None,
        json: Any = None,
        headers: Optional[Dict[str, str]] = None,
        cookies: Optional[Dict[str, str]] = None,
        path_params: Optional[Dict[str, Any]] = None,
        db_session: Any = None,
        security_manager: Any = None,
        session_cookie_value: Optional[str] = None,
        body: Optional[bytes] = None
    ) -> Request:
    """
        Build a webworks :class:`Request` plus the handler-side
        attributes pychestrate routes reach for.

        Body precedence: an explicit ``body=`` wins; otherwise a
        ``json`` payload is encoded (with the JSON content-type
        applied), otherwise a ``form`` dict is URL-encoded (with
        the form content-type applied), otherwise the body is
        empty bytes.

        :param method: HTTP method (defaults to ``"GET"``).
        :param path: Request path (defaults to ``"/"``).
        :param query_params: Optional query-parameter mapping;
                             encoded into the request's query
                             string.
        :param form: Optional form-body mapping; when supplied,
                     the Content-Type is set to
                     ``application/x-www-form-urlencoded``.
        :param json: Optional JSON-encodable body payload; when
                     supplied, the Content-Type is set to
                     ``application/json``.
        :param headers: Optional extra headers; merged on top of
                        any defaults applied by the body shape.
        :param cookies: Optional cookie mapping; serialised into a
                        ``Cookie`` header so
                        :meth:`Request.cookies` reads them.
        :param path_params: Optional path-parameter mapping the
                            dispatcher would normally inject.
        :param db_session: Optional value to attach as
                           ``request.db_session`` -- the
                           per-request SQLAlchemy session most
                           handlers expect.
        :param security_manager: Optional value to attach as
                                 ``request.security_manager``.
        :param session_cookie_value: Optional shorthand for
                                     supplying the UI session
                                     cookie value (added to
                                     ``cookies`` under the
                                     documented cookie name).
        :param body: Optional raw body bytes; when given,
                     bypasses ``json`` / ``form`` encoding.

        :returns: A configured :class:`Request` instance.
    """
    effective_headers: Dict[str, str] = {}
    if headers is not None:
        for key, value in headers.items():
            effective_headers[key] = value

    if body is not None:
        effective_body = body
    elif json is not None:
        effective_body = _encode_json(payload=json)
        effective_headers.setdefault("Content-Type", _JSON_CONTENT_TYPE)
    elif form is not None:
        effective_body = _encode_form(form=form)
        effective_headers.setdefault("Content-Type", _FORM_CONTENT_TYPE)
    else:
        effective_body = b""

    if query_params is not None:
        query_string_bytes = _encode_query(query_params=query_params)
    else:
        query_string_bytes = b""

    effective_cookies: Dict[str, str] = {}
    if cookies is not None:
        for key, value in cookies.items():
            effective_cookies[key] = value
    if session_cookie_value is not None:
        effective_cookies[_UI_COOKIE_NAME] = session_cookie_value

    if len(effective_cookies) > 0:
        cookie_parts: List[str] = []
        for key, value in effective_cookies.items():
            cookie_parts.append("{}={}".format(key, value))
        effective_headers.setdefault("Cookie", "; ".join(cookie_parts))

    request = Request(
        method=method,
        path=path,
        query_string=query_string_bytes,
        headers=effective_headers,
        body=effective_body,
    )
    if path_params is not None:
        request.path_params = dict(path_params)

    # Pychestrate handlers read ``db_session`` and
    # ``security_manager`` off the request as plain attributes
    # (populated upstream by the per-request middleware). The
    # ``Request`` class does not expose setters for these, but it
    # does not block attribute assignment either.
    request.db_session = db_session
    request.security_manager = security_manager

    rtnval = request
    return rtnval


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


def make_fake_session(
        *,
        user_id: str = "u-test",
        session_token: str = "tok-test",
        csrf_token: str = "csrf-test",
        perms: Optional[List[str]] = None,
        extra: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
    """
        Build a session dict shaped the way the foundation
        ``auth_guard`` + ``csrf`` modules expect.

        The keys here intentionally match the constants defined in
        :mod:`webinterface.foundation.auth_guard` (``user_id``,
        ``session_token``) and :mod:`webinterface.foundation.csrf`
        (``csrf_token``) so handlers walked through
        :func:`auth_guard.is_authenticated` see an authenticated
        principal.

        :param user_id: The user identifier to advertise.
        :param session_token: The opaque session token; any
                              non-empty string passes the guard.
        :param csrf_token: The expected CSRF token for the
                           session.
        :param perms: Optional list of permission strings; an
                      empty list is used when not supplied.
        :param extra: Optional extra mapping merged on top.

        :returns: A session dict suitable for both the cookie
                  serialiser and the auth_guard checks.
    """
    perms_list: List[str] = list(perms) if perms is not None else []

    rtnval: Dict[str, Any] = {
        SESSION_USER_ID_KEY: user_id,
        SESSION_TOKEN_KEY: session_token,
        SESSION_CSRF_KEY: csrf_token,
        SESSION_PERMS_KEY: perms_list,
    }
    if extra is not None:
        for key, value in extra.items():
            rtnval[key] = value
    return rtnval


# ---------------------------------------------------------------------------
# Security manager
# ---------------------------------------------------------------------------


class FakeSessionInfo:
    """
        Stand-in for the typed ``SessionInfo`` the real security
        manager hands back from ``validate_token``. Only the
        fields handlers actually read are surfaced.
    """

    def __init__(
            self,
            *,
            user_id: str,
            username: str = "tester",
            csrf_token: str = "csrf-test"
        ) -> None:
        self.user_id: str = user_id
        self.username: str = username
        self.csrf_token: str = csrf_token
        return


class FakeSecurityManager:
    """
        Configurable stub for the security-manager surface the
        REST routes read.

        Defaults to "every token is valid for the configured
        user, every permission check returns True". Override
        ``validate_token_response`` for the missing-session case
        and assign a callable to ``permission_predicate`` to
        return per-permission decisions.
    """

    def __init__(
            self,
            *,
            db_session: Any = None,
            user_id: str = "u-test",
            csrf_token: str = "csrf-test",
            permission_predicate: Optional[
                Callable[[str, str], bool]
            ] = None
        ) -> None:
        self.db_session: Any = db_session
        self.validate_token_response: Optional[FakeSessionInfo] = (
            FakeSessionInfo(
                user_id=user_id, csrf_token=csrf_token
            )
        )
        self.permission_predicate: Optional[
            Callable[[str, str], bool]
        ] = permission_predicate
        self.validate_token_calls: List[str] = []
        self.check_permission_calls: List[Tuple[str, str]] = []
        return

    def validate_token(self, token: str) -> Optional[FakeSessionInfo]:
        """
            Record the call and return the configured response.

            :param token: The opaque session token.

            :returns: A :class:`FakeSessionInfo` or ``None`` when
                      the test has cleared
                      ``validate_token_response``.
        """
        self.validate_token_calls.append(token)
        rtnval = self.validate_token_response
        return rtnval

    def check_permission(
            self,
            user_id: str,
            permission: str
        ) -> bool:
        """
            Record the call and run the configured predicate.

            :param user_id: The user being checked.
            :param permission: The permission being checked.

            :returns: ``True`` by default; otherwise the result of
                      ``permission_predicate(user_id, permission)``.
        """
        self.check_permission_calls.append((user_id, permission))
        if self.permission_predicate is None:
            return True
        rtnval = self.permission_predicate(user_id, permission)
        return rtnval


def make_fake_security_manager(
        *,
        db_session: Any = None,
        user_id: str = "u-test",
        csrf_token: str = "csrf-test",
        permission_predicate: Optional[
            Callable[[str, str], bool]
        ] = None
    ) -> FakeSecurityManager:
    """
        Build a :class:`FakeSecurityManager` with the supplied
        defaults.

        :param db_session: Optional db_session the manager
                           pretends to own.
        :param user_id: User id baked into the default
                        ``validate_token`` response.
        :param csrf_token: CSRF token baked into the default
                           ``validate_token`` response.
        :param permission_predicate: Optional
                                     ``(user_id, permission) ->
                                     bool`` callback. Defaults to
                                     "always True".

        :returns: A :class:`FakeSecurityManager` instance.
    """
    rtnval = FakeSecurityManager(
        db_session=db_session,
        user_id=user_id,
        csrf_token=csrf_token,
        permission_predicate=permission_predicate,
    )
    return rtnval


# ---------------------------------------------------------------------------
# Render capture
# ---------------------------------------------------------------------------


class RenderCall:
    """
        One ``env.get_template(name).render(ctx)`` invocation, as
        captured by :func:`capture_renders`.
    """

    def __init__(
            self,
            *,
            template_name: str,
            context: Dict[str, Any]
        ) -> None:
        self.template_name: str = template_name
        self.context: Dict[str, Any] = context
        return


class _StubTemplate:
    """
        Stub returned from :meth:`_StubJinjaEnvironment.get_template`.
        Captures the render call on the parent recorder.
    """

    def __init__(
            self,
            *,
            name: str,
            recorder: "RenderRecorder"
        ) -> None:
        self._name: str = name
        self._recorder: "RenderRecorder" = recorder
        return

    def render(self, ctx: Dict[str, Any]) -> str:
        """
            Capture the render call and return a deterministic
            sentinel string so the handler still produces a
            non-empty body.

            :param ctx: The template-context dict.

            :returns: A sentinel ``"RENDERED:<name>"`` string.
        """
        self._recorder.calls.append(
            RenderCall(template_name=self._name, context=dict(ctx))
        )
        rtnval = "RENDERED:{}".format(self._name)
        return rtnval


class _StubJinjaEnvironment:
    """
        Drop-in for a :class:`jinja2.Environment`. The only method
        the templating helper invokes is ``get_template``; the
        ``globals`` dict is present because the foundation
        templating module mutates it on construction.
    """

    def __init__(self, *, recorder: "RenderRecorder") -> None:
        self._recorder: "RenderRecorder" = recorder
        self.globals: Dict[str, Any] = {}
        return

    def get_template(self, name: str) -> _StubTemplate:
        """
            Look up a template by name.

            :param name: Template name (matches whatever the
                         handler passed).

            :returns: A :class:`_StubTemplate` that records its
                      render call.
        """
        rtnval = _StubTemplate(name=name, recorder=self._recorder)
        return rtnval


class RenderRecorder:
    """
        Accumulator object yielded by :func:`capture_renders`.

        Tests assert against :attr:`calls` after invoking the
        handler under test.
    """

    def __init__(self) -> None:
        self.calls: List[RenderCall] = []
        self.environment: _StubJinjaEnvironment = _StubJinjaEnvironment(
            recorder=self
        )
        return

    def template_names(self) -> List[str]:
        """
            All captured template names in render order.

            :returns: List of template-name strings.
        """
        rtnval = [call.template_name for call in self.calls]
        return rtnval

    def last_context(self) -> Dict[str, Any]:
        """
            Context dict from the most recent render.

            :returns: The captured context mapping.

            :raises: IndexError when no render has been captured.
        """
        if len(self.calls) == 0:
            err_msg_lines = [
                "RenderRecorder.last_context called with no "
                "captured renders.",
            ]
            err_msg = os.linesep.join(err_msg_lines)
            raise IndexError(err_msg)
        rtnval = self.calls[-1].context
        return rtnval


@contextlib.contextmanager
def capture_renders(
        *,
        templating_module: Any
    ) -> Iterator[RenderRecorder]:
    """
        Swap a stub Jinja env into the supplied templating module
        for the duration of the ``with`` block.

        The pychestrate webinterface foundation uses a module-level
        Jinja env singleton accessed via
        ``templating.get_jinja_environment()``. This helper
        temporarily patches that accessor so any handler invoked
        inside the ``with`` block routes its
        ``env.get_template(name).render(ctx)`` calls through the
        :class:`RenderRecorder` rather than producing real HTML.

        :param templating_module: The
                                  ``webinterface.foundation.templating``
                                  module (passed in so tests do
                                  not double-import it).

        :returns: A :class:`RenderRecorder` exposing the captured
                  ``calls``.
    """
    recorder = RenderRecorder()

    original_getter = getattr(
        templating_module, "get_jinja_environment", None
    )

    def _stub_getter() -> _StubJinjaEnvironment:
        rtnval = recorder.environment
        return rtnval

    setattr(
        templating_module, "get_jinja_environment", _stub_getter
    )
    try:
        yield recorder
    finally:
        if original_getter is None:
            delattr(templating_module, "get_jinja_environment")
        else:
            setattr(
                templating_module,
                "get_jinja_environment",
                original_getter,
            )
    return
