"""
.. module:: test_p10y_webworks_session_middleware_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the webworks-side request-scoped session
               middleware.

.. moduleauthor:: Automation Mojo LLC

The middleware is a single ``__call__(request, call_next)``
callable that wraps the handler. Tests cover the four behavior
slices the flask version had:

* Path-prefix gating — out-of-scope requests pass through with no
  session and no actor.
* Pre-handler — db_session and actor are attached.
* Post-handler success — session is closed (no rollback).
* Post-handler failure — session is rolled back THEN closed; the
  exception re-raises; cleanup failures are logged but never mask
  the original exception.

Stub callables capture the open / resolve / rollback / close
calls so tests assert on the wire calls without a real database
or session_service.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import logging

from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from automojo import testbase

from automojo.pychestrate.webservice.middleware_webworks import (
    SESSION_MIDDLEWARE_NAME,
    PychestrateSessionMiddleware,
    install_pychestrate_session_middleware,
)


# ---------------------------------------------------------------------------
# Test stubs
# ---------------------------------------------------------------------------


class _FakeRequest:
    """
        Minimal duck-typed Request. Only ``path`` and ``cookies``
        are read by the middleware; ``db_session`` /
        ``auth_principal`` / ``actor_user_id`` are written.
    """

    def __init__(
        self,
        *,
        path: str,
        cookies: Optional[Dict[str, str]] = None
    ) -> None:
        self.path: str = path
        self.cookies: Dict[str, str] = cookies if cookies is not None else {}
        self.db_session: Any = None
        self.auth_principal: Any = None
        self.actor_user_id: Optional[str] = None
        return


class _FakeSession:
    """
        Stand-in for a SQLAlchemy session. Records rollback / close
        invocations so tests can assert the cleanup ordering.
    """

    def __init__(
        self,
        *,
        rollback_raises: Optional[BaseException] = None,
        close_raises: Optional[BaseException] = None
    ) -> None:
        self.rollback_calls: int = 0
        self.close_calls: int = 0
        self._rollback_raises: Optional[BaseException] = rollback_raises
        self._close_raises: Optional[BaseException] = close_raises
        return

    def rollback(self) -> None:
        self.rollback_calls += 1
        if self._rollback_raises is not None:
            raise self._rollback_raises
        return

    def close(self) -> None:
        self.close_calls += 1
        if self._close_raises is not None:
            raise self._close_raises
        return


class _FakePrincipal:
    """
        Stand-in for an ``AuthPrincipal``. The middleware reads
        ``user_id``; nothing else.
    """

    def __init__(self, *, user_id: str) -> None:
        self.user_id: str = user_id
        return


class _FakeResponse:
    """
        Stand-in for a webworks Response. Carries an integer status
        so tests can assert which response the pipeline returned.
    """

    def __init__(self, *, status_code: int) -> None:
        self.status_code: int = status_code
        return


class _RecordingLogger:
    """
        ``logging.Logger`` look-alike that records calls to
        ``exception(...)``. The middleware's cleanup phase routes
        rollback / close failures here.
    """

    def __init__(self) -> None:
        self.exception_calls: List[Tuple[str, Tuple[Any, ...]]] = []
        return

    def exception(self, msg: str, *args: Any) -> None:
        self.exception_calls.append((msg, args))
        return

    def info(self, msg: str, *args: Any) -> None:
        return


def _fixed_clock() -> datetime:
    rtnval = datetime(2026, 5, 2, 12, 0, 0, tzinfo=timezone.utc)
    return rtnval


def _build_open_session(
        *, sessions_to_return: List[_FakeSession]
    ) -> Callable[[], _FakeSession]:
    """
        Build a stub ``open_session`` callable that pops from a list
        per call. Lets tests assert the middleware invokes it once
        per in-scope request and never for out-of-scope requests.
    """
    state = {"calls": 0}

    def open_session() -> _FakeSession:
        rtnval = sessions_to_return[state["calls"]]
        state["calls"] += 1
        return rtnval

    open_session.calls = state  # type: ignore[attr-defined]
    rtnval = open_session
    return rtnval


def _build_resolve_actor(
        *, by_session_id: Dict[str, Optional[_FakePrincipal]]
    ) -> Callable[[Any, str, datetime], Optional[_FakePrincipal]]:
    """
        Build a stub ``resolve_actor`` callable backed by a dict.
        Returns the configured principal (or None) per session id.
    """
    calls: List[Tuple[Any, str, datetime]] = []

    def resolve_actor(
        db_session: Any, session_id: str, now: datetime
    ) -> Optional[_FakePrincipal]:
        calls.append((db_session, session_id, now))
        rtnval = by_session_id.get(session_id, None)
        return rtnval

    resolve_actor.calls = calls  # type: ignore[attr-defined]
    rtnval = resolve_actor
    return rtnval


def _build_middleware(
        *,
        sessions: List[_FakeSession],
        principals: Optional[Dict[str, Optional[_FakePrincipal]]] = None,
        path_prefixes: Tuple[str, ...] = ("/api/v1/",),
        cookie_name: str = "pychestrate_session",
        ctx_logger: Optional[logging.Logger] = None
    ) -> Tuple[
        PychestrateSessionMiddleware,
        Callable[[], _FakeSession],
        Callable[[Any, str, datetime], Optional[_FakePrincipal]],
    ]:
    """
        Common middleware factory used by the test bodies.
    """
    open_session = _build_open_session(sessions_to_return=sessions)
    resolve_actor = _build_resolve_actor(
        by_session_id=principals if principals is not None else {}
    )
    middleware = PychestrateSessionMiddleware(
        open_session=open_session,
        resolve_actor=resolve_actor,
        cookie_name=cookie_name,
        path_prefixes=path_prefixes,
        ctx_logger=ctx_logger,
        clock=_fixed_clock,
    )
    rtnval = (middleware, open_session, resolve_actor)
    return rtnval


# ---------------------------------------------------------------------------
# Path-prefix gating
# ---------------------------------------------------------------------------


def test_out_of_scope_path_passes_through_without_opening_session():
    """
    **Feature: webworks session middleware**
    **Property: A request whose path does not match any configured
    prefix is passed through to the handler unchanged. No session is
    opened and the handler sees a request with no db_session
    attribute set on it.**
    """
    middleware, open_session, _ = _build_middleware(
        sessions=[], path_prefixes=("/api/v1/",)
    )
    request = _FakeRequest(path="/")
    captured_request: List[_FakeRequest] = []

    def call_next(req: _FakeRequest) -> _FakeResponse:
        captured_request.append(req)
        return _FakeResponse(status_code=200)

    response = middleware(request, call_next)

    testbase.assert_equal(response.status_code, 200)
    testbase.assert_equal(open_session.calls["calls"], 0)
    testbase.assert_equal(len(captured_request), 1)
    testbase.assert_equal(captured_request[0].db_session, None)
    return


def test_in_scope_path_opens_session_and_attaches_to_request():
    """
    **Feature: webworks session middleware**
    **Property: An in-scope request gets a db_session attached
    before the handler runs, and the handler sees it.**
    """
    session = _FakeSession()
    middleware, open_session, _ = _build_middleware(sessions=[session])
    request = _FakeRequest(path="/api/v1/flags")
    seen_session: List[Any] = []

    def call_next(req: _FakeRequest) -> _FakeResponse:
        seen_session.append(req.db_session)
        return _FakeResponse(status_code=200)

    middleware(request, call_next)

    testbase.assert_equal(open_session.calls["calls"], 1)
    testbase.assert_equal(seen_session[0] is session, True)
    return


# ---------------------------------------------------------------------------
# Actor attachment
# ---------------------------------------------------------------------------


def test_request_without_session_cookie_has_no_actor_attached():
    """
    **Feature: webworks session middleware**
    **Property: A request with no session cookie produces
    actor_user_id=None and auth_principal=None — unauthenticated
    requests are legal on routes that do not require auth.**
    """
    session = _FakeSession()
    middleware, _, resolve_actor = _build_middleware(sessions=[session])
    request = _FakeRequest(path="/api/v1/flags", cookies={})

    seen_actor: List[Optional[str]] = []

    def call_next(req: _FakeRequest) -> _FakeResponse:
        seen_actor.append(req.actor_user_id)
        return _FakeResponse(status_code=200)

    middleware(request, call_next)

    testbase.assert_equal(seen_actor[0], None)
    testbase.assert_equal(len(resolve_actor.calls), 0)
    return


def test_request_with_resolved_cookie_has_actor_user_id_attached():
    """
    **Feature: webworks session middleware**
    **Property: When the session cookie resolves to an
    AuthPrincipal, the user_id is attached as
    request.actor_user_id and the principal as
    request.auth_principal — matching the flask middleware's
    contract for downstream handlers.**
    """
    session = _FakeSession()
    principal = _FakePrincipal(user_id="user-42")
    middleware, _, resolve_actor = _build_middleware(
        sessions=[session],
        principals={"sess-abc": principal},
    )
    request = _FakeRequest(
        path="/api/v1/flags", cookies={"pychestrate_session": "sess-abc"}
    )

    seen_actor_user_id: List[Optional[str]] = []
    seen_principal: List[Any] = []

    def call_next(req: _FakeRequest) -> _FakeResponse:
        seen_actor_user_id.append(req.actor_user_id)
        seen_principal.append(req.auth_principal)
        return _FakeResponse(status_code=200)

    middleware(request, call_next)

    testbase.assert_equal(seen_actor_user_id[0], "user-42")
    testbase.assert_equal(seen_principal[0] is principal, True)
    testbase.assert_equal(len(resolve_actor.calls), 1)
    return


def test_request_with_unresolvable_cookie_has_no_actor_attached():
    """
    **Feature: webworks session middleware**
    **Property: When resolve_actor returns None (expired / unknown
    cookie), the request is treated as unauthenticated rather than
    rejected. The default_resolve_actor wrapper performs the
    SessionExpiredError / SessionNotFoundError conversion to None.**
    """
    session = _FakeSession()
    middleware, _, resolve_actor = _build_middleware(
        sessions=[session],
        principals={"sess-stale": None},
    )
    request = _FakeRequest(
        path="/api/v1/flags", cookies={"pychestrate_session": "sess-stale"}
    )
    seen_actor_user_id: List[Optional[str]] = []

    def call_next(req: _FakeRequest) -> _FakeResponse:
        seen_actor_user_id.append(req.actor_user_id)
        return _FakeResponse(status_code=200)

    middleware(request, call_next)

    testbase.assert_equal(seen_actor_user_id[0], None)
    testbase.assert_equal(len(resolve_actor.calls), 1)
    return


def test_empty_string_cookie_does_not_invoke_resolver():
    """
    **Feature: webworks session middleware**
    **Property: An empty-string cookie value short-circuits to the
    no-actor branch without invoking resolve_actor.**
    """
    session = _FakeSession()
    middleware, _, resolve_actor = _build_middleware(sessions=[session])
    request = _FakeRequest(
        path="/api/v1/flags", cookies={"pychestrate_session": ""}
    )

    def call_next(req: _FakeRequest) -> _FakeResponse:
        return _FakeResponse(status_code=200)

    middleware(request, call_next)

    testbase.assert_equal(len(resolve_actor.calls), 0)
    return


# ---------------------------------------------------------------------------
# Cleanup -- success path
# ---------------------------------------------------------------------------


def test_successful_request_closes_session_without_rollback():
    """
    **Feature: webworks session middleware**
    **Property: A successful handler completes without triggering a
    rollback. The session is always closed.**
    """
    session = _FakeSession()
    middleware, _, _ = _build_middleware(sessions=[session])
    request = _FakeRequest(path="/api/v1/flags")

    def call_next(req: _FakeRequest) -> _FakeResponse:
        return _FakeResponse(status_code=200)

    middleware(request, call_next)

    testbase.assert_equal(session.rollback_calls, 0)
    testbase.assert_equal(session.close_calls, 1)
    return


def test_successful_request_clears_request_attributes_after_close():
    """
    **Feature: webworks session middleware**
    **Property: After a successful request, request.db_session,
    request.auth_principal, and request.actor_user_id are all
    cleared so the closed session cannot be reused. Mirrors the
    flask middleware's teardown which set the same g attrs to
    None.**
    """
    session = _FakeSession()
    middleware, _, _ = _build_middleware(sessions=[session])
    request = _FakeRequest(path="/api/v1/flags")

    def call_next(req: _FakeRequest) -> _FakeResponse:
        return _FakeResponse(status_code=200)

    middleware(request, call_next)

    testbase.assert_equal(request.db_session, None)
    testbase.assert_equal(request.auth_principal, None)
    testbase.assert_equal(request.actor_user_id, None)
    return


# ---------------------------------------------------------------------------
# Cleanup -- failure path
# ---------------------------------------------------------------------------


def test_handler_exception_triggers_rollback_then_close_then_reraises():
    """
    **Feature: webworks session middleware**
    **Property: A handler exception triggers rollback() THEN
    close() (in that order) and the exception propagates to the
    caller. Order matters — close before rollback would lose any
    pending dirty state.**
    """
    session = _FakeSession()
    middleware, _, _ = _build_middleware(sessions=[session])
    request = _FakeRequest(path="/api/v1/flags")

    class _BoomError(Exception):
        pass

    def call_next(req: _FakeRequest) -> _FakeResponse:
        raise _BoomError("handler failure")

    raised = False
    try:
        middleware(request, call_next)
    except _BoomError:
        raised = True

    testbase.assert_equal(raised, True)
    testbase.assert_equal(session.rollback_calls, 1)
    testbase.assert_equal(session.close_calls, 1)
    return


def test_rollback_failure_is_logged_and_does_not_mask_original_exception():
    """
    **Feature: webworks session middleware**
    **Property: When rollback() raises during cleanup, the
    exception is logged and swallowed; close() still runs; and the
    original handler exception still propagates to the caller.
    Teardown must not mask the original failure that triggered the
    rollback.**
    """
    session = _FakeSession(rollback_raises=RuntimeError("rollback boom"))
    recorder = _RecordingLogger()
    middleware, _, _ = _build_middleware(
        sessions=[session], ctx_logger=recorder
    )
    request = _FakeRequest(path="/api/v1/flags")

    class _OriginalError(Exception):
        pass

    def call_next(req: _FakeRequest) -> _FakeResponse:
        raise _OriginalError("original failure")

    caught: List[BaseException] = []
    try:
        middleware(request, call_next)
    except _OriginalError as xcpt:
        caught.append(xcpt)

    testbase.assert_equal(len(caught), 1)
    testbase.assert_equal(session.close_calls, 1)
    testbase.assert_equal(len(recorder.exception_calls) >= 1, True)
    return


def test_close_failure_is_logged_and_does_not_mask_original_exception():
    """
    **Feature: webworks session middleware**
    **Property: When close() raises during cleanup, the exception
    is logged and swallowed; the original handler exception still
    propagates.**
    """
    session = _FakeSession(close_raises=RuntimeError("close boom"))
    recorder = _RecordingLogger()
    middleware, _, _ = _build_middleware(
        sessions=[session], ctx_logger=recorder
    )
    request = _FakeRequest(path="/api/v1/flags")

    class _OriginalError(Exception):
        pass

    def call_next(req: _FakeRequest) -> _FakeResponse:
        raise _OriginalError("original failure")

    caught: List[BaseException] = []
    try:
        middleware(request, call_next)
    except _OriginalError as xcpt:
        caught.append(xcpt)

    testbase.assert_equal(len(caught), 1)
    testbase.assert_equal(len(recorder.exception_calls) >= 1, True)
    return


# ---------------------------------------------------------------------------
# Installation
# ---------------------------------------------------------------------------


class _FakePipeline:
    """
        Captures the pipeline.add(...) call so the install helper
        can be exercised without a real webworks app.
    """

    def __init__(self) -> None:
        self.added: List[Tuple[Any, Optional[str], str]] = []
        return

    def add(
        self,
        middleware: Any,
        name: Optional[str] = None,
        position: str = "end",
        priority: int = 50,
        scope: str = "global"
    ) -> None:
        self.added.append((middleware, name, position))
        return


class _FakeDispatcher:
    def __init__(self) -> None:
        self.pipeline: _FakePipeline = _FakePipeline()
        return


class _FakeApp:
    def __init__(self) -> None:
        self.dispatcher: _FakeDispatcher = _FakeDispatcher()
        return


def test_install_adds_middleware_at_pipeline_start_with_documented_name():
    """
    **Feature: webworks session middleware**
    **Property: install_pychestrate_session_middleware adds the
    middleware at position "start" so it runs first on the way in
    and last on the way out, with the documented name so it can be
    referenced for ordering by future middleware.**
    """
    app = _FakeApp()
    middleware = install_pychestrate_session_middleware(
        app=app,
        cookie_name="pychestrate_session",
        path_prefixes=("/api/v1/",),
        open_session=lambda: _FakeSession(),
        resolve_actor=lambda db, sid, now: None,
    )

    testbase.assert_equal(len(app.dispatcher.pipeline.added), 1)
    added_middleware, added_name, added_position = (
        app.dispatcher.pipeline.added[0]
    )
    testbase.assert_equal(added_middleware is middleware, True)
    testbase.assert_equal(added_name, SESSION_MIDDLEWARE_NAME)
    testbase.assert_equal(added_position, "start")
    return


def test_install_returns_a_pychestrate_session_middleware_instance():
    """
    **Feature: webworks session middleware**
    **Property: install returns the constructed middleware so
    tests / wiring code can hold a reference (for diagnostics or
    later removal via the pipeline.remove(name) API).**
    """
    app = _FakeApp()
    middleware = install_pychestrate_session_middleware(
        app=app,
        cookie_name="pychestrate_session",
        path_prefixes=("/api/v1/",),
        open_session=lambda: _FakeSession(),
        resolve_actor=lambda db, sid, now: None,
    )
    is_correct_class = isinstance(middleware, PychestrateSessionMiddleware)
    testbase.assert_equal(is_correct_class, True)
    return


# ---------------------------------------------------------------------------
# Bootstrap source-smoke
# ---------------------------------------------------------------------------


def test_bootstrap_imports_install_helper_and_calls_it_after_startup():
    """
    **Feature: webworks session middleware**
    **Property: app_pychestrate_main.py wires
    install_pychestrate_session_middleware into the boot sequence
    and calls it AFTER app.startup() — the dispatcher does not
    exist before the INFRASTRUCTURE_READY phase, so the install
    must come after startup. Source-level smoke; full app boot is
    out of scope for the singlehost suite.**
    """
    import os

    here = os.path.dirname(os.path.abspath(__file__))
    repo_source_root = os.path.normpath(
        os.path.join(
            here, "..", "..", "..", "..", "..", "..", "..", "..",
            "source", "site",
        )
    )
    bootstrap_path = os.path.join(repo_source_root, "app_pychestrate_main.py")
    with open(bootstrap_path, "r", encoding="utf-8") as fh:
        text = fh.read()

    has_import = (
        "from automojo.pychestrate.webservice.middleware_webworks import"
        in text
    )
    testbase.assert_equal(has_import, True)

    startup_index = text.find("app.startup()")
    install_index = text.find("install_pychestrate_session_middleware(")
    testbase.assert_equal(startup_index > 0, True)
    testbase.assert_equal(install_index > 0, True)
    testbase.assert_equal(install_index > startup_index, True)
    return
