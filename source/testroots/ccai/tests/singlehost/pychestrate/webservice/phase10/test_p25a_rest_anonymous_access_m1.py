"""
.. module:: test_p25a_rest_anonymous_access_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for deny-by-default anonymous access on the REST
               API: the allowlist policy, the session middleware that
               enforces it, and an inventory of the production app.

.. moduleauthor:: Code Craft AI LLC

Audit finding LD-12: individual REST handlers decided for
themselves whether to require a signed-in principal, and 52 of 217
routes ran without one. The session middleware now refuses every
``/api/v1/*`` request that carries no principal with a 401, unless
the route is on the explicit allowlist in
:mod:`security.auth.anonymous_access`.

Coverage:

* :func:`is_anonymous_request_permitted` -- scope, method matching,
  anchoring, and the allowlisted machine-plane routes.
* :class:`PychestrateSessionMiddleware` -- a refused request gets a
  401 problem document and never reaches the handler; a permitted or
  authenticated request does; the installer applies the allowlist
  policy by default.
* The production inventory -- ``build_wsgi_application_for_production``
  booted in a subprocess (as in ``test_p13ab``) answers an anonymous
  request to every registered ``/api/v1`` route with a 401 unless the
  route is allowlisted, and every allowlist entry still names a real
  route.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from ccai import testbase

from ccai.pychestrate.webservice.middleware_webworks import (
    PychestrateSessionMiddleware,
    install_pychestrate_session_middleware,
)
from ccai.pychestrate.webservice.security.auth.anonymous_access import (
    ANONYMOUS_ROUTE_ALLOWLIST,
    is_anonymous_request_permitted,
)


SAMPLE_ID = "00000000-0000-4000-8000-000000000001"


# ===========================================================================
# Allowlist policy
# ===========================================================================


def test_policy_permits_paths_outside_the_rest_api():
    """
    **Feature: REST anonymous access (LD-12)**
    **Property: paths outside /api/v1/ (the server-rendered UI, which
    redirects to the login page itself) are not governed by the
    policy.**
    """
    testbase.assert_equal(
        is_anonymous_request_permitted("GET", "/admin/dashboard"), True
    )
    return


def test_policy_refuses_a_rest_route_that_is_not_allowlisted():
    """
    **Feature: REST anonymous access (LD-12)**
    **Property: an anonymous request to a REST route that is not on
    the allowlist (the audit log) is refused.**
    """
    testbase.assert_equal(
        is_anonymous_request_permitted("GET", "/api/v1/audit"), False
    )
    return


def test_policy_permits_an_allowlisted_route():
    """
    **Feature: REST anonymous access (LD-12)**
    **Property: enrollment-token redemption, whose credential is the
    one-time token in the body, may be reached without a session.**
    """
    testbase.assert_equal(
        is_anonymous_request_permitted("POST", "/api/v1/enrollment-tokens/redeem"),
        True,
    )
    return


def test_policy_matches_the_method_as_well_as_the_path():
    """
    **Feature: REST anonymous access (LD-12)**
    **Property: an allowlisted path is permitted only for its listed
    method -- GET on the POST-only redeem route is refused.**
    """
    testbase.assert_equal(
        is_anonymous_request_permitted("GET", "/api/v1/enrollment-tokens/redeem"),
        False,
    )
    return


def test_policy_accepts_the_method_in_any_case():
    """
    **Feature: REST anonymous access (LD-12)**
    **Property: method matching is case-insensitive.**
    """
    testbase.assert_equal(
        is_anonymous_request_permitted("post", "/api/v1/enrollment-tokens/redeem"),
        True,
    )
    return


def test_policy_does_not_permit_paths_that_extend_an_allowlisted_route():
    """
    **Feature: REST anonymous access (LD-12)**
    **Property: allowlist patterns are anchored, so a longer path that
    starts with an allowlisted one is refused.**
    """
    testbase.assert_equal(
        is_anonymous_request_permitted("POST", "/api/v1/_metrics/ui/extra"),
        False,
    )
    return


def test_policy_path_parameters_do_not_span_segments():
    """
    **Feature: REST anonymous access (LD-12)**
    **Property: a path parameter in an allowlist pattern matches one
    segment only, so ``/clients/a/b/heartbeat`` is refused.**
    """
    testbase.assert_equal(
        is_anonymous_request_permitted("GET", "/api/v1/clients/a/b/heartbeat"),
        False,
    )
    return


def test_policy_permits_the_pod_heartbeat():
    """
    **Feature: REST anonymous access (LD-12)**
    **Property: the pod machine plane (here the heartbeat) reaches
    its handler, which authenticates the pod by its client
    certificate.**
    """
    testbase.assert_equal(
        is_anonymous_request_permitted(
            "GET", "/api/v1/clients/{}/heartbeat".format(SAMPLE_ID)
        ),
        True,
    )
    return


# ===========================================================================
# Middleware enforcement
# ===========================================================================


class _FakeRequest:
    def __init__(
        self,
        *,
        path: str,
        method: str = "GET",
        cookies: Optional[Dict[str, str]] = None
    ) -> None:
        self.path: str = path
        self.method: str = method
        self.cookies: Dict[str, str] = cookies if cookies is not None else {}
        self.db_session: Any = None
        self.auth_principal: Any = None
        self.actor_user_id: Optional[str] = None
        return


class _FakeSession:
    def __init__(self) -> None:
        self.close_calls: int = 0
        return

    def rollback(self) -> None:
        return

    def close(self) -> None:
        self.close_calls += 1
        return


class _FakePrincipal:
    def __init__(self, *, user_id: str) -> None:
        self.user_id: str = user_id
        return


class _FakeResponse:
    def __init__(self, *, status_code: int) -> None:
        self.status_code: int = status_code
        return


class _PolicyRecorder:
    """
        Anonymous-access policy stand-in that answers a fixed value
        and records every ``(method, path)`` it was asked about.
    """

    def __init__(self, *, permitted: bool) -> None:
        self.permitted: bool = permitted
        self.calls: List[Tuple[str, str]] = []
        return

    def __call__(self, method: str, path: str) -> bool:
        self.calls.append((method, path))
        return self.permitted


def _middleware(
        *,
        policy: Any,
        session: _FakeSession,
        principal: Optional[_FakePrincipal] = None
    ) -> PychestrateSessionMiddleware:
    rtnval = PychestrateSessionMiddleware(
        open_session=lambda: session,
        resolve_actor=lambda db_session, session_id, now: principal,
        cookie_name="pychestrate_session",
        path_prefixes=("/api/v1/",),
        fallback_cookie_resolvers=[],
        clock=lambda: datetime(2026, 9, 22, 12, 0, 0, tzinfo=timezone.utc),
        anonymous_access_policy=policy,
    )
    return rtnval


def test_middleware_answers_401_when_the_policy_refuses_an_anonymous_request():
    """
    **Feature: REST anonymous access (LD-12)**
    **Property: an anonymous request the policy refuses ends with a
    401 and never reaches the handler.**
    """
    handler_calls: List[Any] = []

    def call_next(request: Any) -> _FakeResponse:
        handler_calls.append(request)
        return _FakeResponse(status_code=200)

    middleware = _middleware(
        policy=_PolicyRecorder(permitted=False), session=_FakeSession()
    )
    response = middleware(_FakeRequest(path="/api/v1/audit"), call_next)

    testbase.assert_equal((response.status_code, len(handler_calls)), (401, 0))
    return


def test_middleware_closes_the_session_of_a_refused_request():
    """
    **Feature: REST anonymous access (LD-12)**
    **Property: refusing a request still runs the normal cleanup --
    the per-request database session is closed.**
    """
    session = _FakeSession()
    middleware = _middleware(policy=_PolicyRecorder(permitted=False), session=session)

    middleware(
        _FakeRequest(path="/api/v1/audit"),
        lambda request: _FakeResponse(status_code=200),
    )

    testbase.assert_equal(session.close_calls, 1)
    return


def test_middleware_lets_a_permitted_anonymous_request_reach_the_handler():
    """
    **Feature: REST anonymous access (LD-12)**
    **Property: an anonymous request the policy permits reaches the
    handler, which authenticates it its own way.**
    """
    middleware = _middleware(
        policy=_PolicyRecorder(permitted=True), session=_FakeSession()
    )
    response = middleware(
        _FakeRequest(path="/api/v1/enrollment-tokens/redeem", method="POST"),
        lambda request: _FakeResponse(status_code=201),
    )

    testbase.assert_equal(response.status_code, 201)
    return


def test_middleware_does_not_consult_the_policy_for_an_authenticated_request():
    """
    **Feature: REST anonymous access (LD-12)**
    **Property: a request whose session cookie resolves to a
    principal reaches the handler without the anonymous-access
    policy being asked.**
    """
    policy = _PolicyRecorder(permitted=False)
    middleware = _middleware(
        policy=policy,
        session=_FakeSession(),
        principal=_FakePrincipal(user_id="user-1"),
    )
    response = middleware(
        _FakeRequest(path="/api/v1/audit", cookies={"pychestrate_session": "sess-1"}),
        lambda request: _FakeResponse(status_code=200),
    )

    testbase.assert_equal((response.status_code, policy.calls), (200, []))
    return


def test_middleware_passes_method_and_path_to_the_policy():
    """
    **Feature: REST anonymous access (LD-12)**
    **Property: the policy is asked about the request's upper-case
    method and its path.**
    """
    policy = _PolicyRecorder(permitted=False)
    middleware = _middleware(policy=policy, session=_FakeSession())

    middleware(
        _FakeRequest(path="/api/v1/projects", method="post"),
        lambda request: _FakeResponse(status_code=201),
    )

    testbase.assert_equal(policy.calls, [("POST", "/api/v1/projects")])
    return


class _FakePipeline:
    def __init__(self) -> None:
        self.added: List[Any] = []
        return

    def add(self, middleware: Any, name: Optional[str] = None,
            position: str = "end", priority: int = 50, scope: str = "global") -> None:
        self.added.append(middleware)
        return


class _FakeDispatcher:
    def __init__(self) -> None:
        self.pipeline: _FakePipeline = _FakePipeline()
        return


class _FakeApp:
    def __init__(self) -> None:
        self.dispatcher: _FakeDispatcher = _FakeDispatcher()
        return


def test_installer_applies_the_allowlist_policy_by_default():
    """
    **Feature: REST anonymous access (LD-12)**
    **Property: install_pychestrate_session_middleware, called as
    the production bootstrap calls it (no policy argument), enforces
    is_anonymous_request_permitted.**
    """
    middleware = install_pychestrate_session_middleware(
        app=_FakeApp(),
        path_prefixes=("/api/v1/",),
        open_session=lambda: _FakeSession(),
        resolve_actor=lambda db_session, session_id, now: None,
    )
    testbase.assert_equal(
        middleware._anonymous_access_policy is is_anonymous_request_permitted,
        True,
    )
    return


# ===========================================================================
# Production inventory
# ===========================================================================


def _repo_root() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    rtnval = os.path.normpath(
        os.path.join(here, "..", "..", "..", "..", "..", "..", "..", "..")
    )
    return rtnval


# Runs in a subprocess: record every route the production bootstrap
# registers, then send one anonymous request (no cookies, JSON body
# "{}" for writes) to each /api/v1 route through the WSGI app and
# print the status codes.
_PROBE_SCRIPT_TEMPLATE = textwrap.dedent('''\
    import io
    import json
    import os
    import re
    import sys
    import traceback

    REPO_ROOT = {repo_root!r}
    for component in ("source/site", "source/packages", "source/service"):
        full = os.path.join(REPO_ROOT, component)
        if full not in sys.path:
            sys.path.insert(0, full)

    from ccai.webworks.routing import router as router_module

    RECORDED = []
    original_add_endpoint = router_module.Router.add_endpoint

    def recording_add_endpoint(self, descriptor):
        RECORDED.append((descriptor.path, tuple(descriptor.methods)))
        return original_add_endpoint(self, descriptor)

    router_module.Router.add_endpoint = recording_add_endpoint

    try:
        from app_pychestrate_main import build_wsgi_application_for_production
        wsgi_app = build_wsgi_application_for_production()
        # A fresh database has not finished the setup wizard, so the
        # setup gate would redirect every request to /setup/unlock.
        # Mark setup complete for this process, as the wizard does.
        from ccai.pychestrate.webservice.identity.setup.setup_service import (
            mark_setup_complete_in_process_cache,
        )
        mark_setup_complete_in_process_cache()
    except BaseException:
        print("STAGE: bootstrap-failed")
        traceback.print_exc()
        sys.exit(3)

    def concrete_path(template):
        def substitute(match):
            if match.group(1).endswith(":int"):
                return "1"
            return {sample_id!r}
        return re.sub(r"\\{{([^}}]+)\\}}", substitute, template)

    results = []
    for template, methods in sorted(set(RECORDED)):
        if not template.startswith("/api/v1/"):
            continue
        for method in methods:
            path = concrete_path(template)
            body = b"{{}}" if method in ("POST", "PUT", "PATCH") else b""
            captured = {{}}

            def start_response(status, headers, exc_info=None, captured=captured):
                captured["status"] = status
                return lambda chunk: None

            environ = {{
                "REQUEST_METHOD": method,
                "PATH_INFO": path,
                "QUERY_STRING": "",
                "SERVER_NAME": "probe.invalid",
                "SERVER_PORT": "80",
                "SERVER_PROTOCOL": "HTTP/1.1",
                "SCRIPT_NAME": "",
                "CONTENT_TYPE": "application/json",
                "CONTENT_LENGTH": str(len(body)),
                "HTTP_ACCEPT": "application/json",
                "wsgi.input": io.BytesIO(body),
                "wsgi.errors": sys.stderr,
                "wsgi.url_scheme": "http",
                "wsgi.multithread": False,
                "wsgi.multiprocess": False,
                "wsgi.run_once": False,
                "wsgi.version": (1, 0),
            }}
            try:
                list(wsgi_app(environ, start_response))
                status = int(str(captured.get("status", "-1")).split(" ", 1)[0])
            except BaseException:
                status = -1
            results.append({{"method": method, "template": template, "path": path, "status": status}})

    print("RESULTS: " + json.dumps(results))
    sys.exit(0)
''')


_PROBE_RESULTS: Optional[List[Dict[str, Any]]] = None


def _production_route_probe() -> List[Dict[str, Any]]:
    """
        Boot the production app once (alembic-migrated SQLite, KEK
        file, testing environment) in a subprocess and return the
        anonymous-request result for every ``/api/v1`` route. Cached
        for the module.
    """
    global _PROBE_RESULTS
    if _PROBE_RESULTS is not None:
        return _PROBE_RESULTS

    repo_root = _repo_root()
    workdir = tempfile.mkdtemp(prefix="pych-anon-probe-")
    db_path = os.path.join(workdir, "probe.sqlite")
    kek_path = os.path.join(workdir, "kek.bin")
    with open(kek_path, "wb") as kek_file:
        kek_file.write(b"\x77" * 32)
    # The KEK loader refuses a key file its group or other users can read.
    os.chmod(kek_path, 0o600)

    env = os.environ.copy()
    env["PYCHESTRATE_DATABASE_URL"] = "sqlite:///" + db_path
    env["PYCHESTRATE_RUNTIME_ENVIRONMENT"] = "testing"
    env["PYCHESTRATE_AUTO_CREATE_SCHEMA"] = "false"
    env["PYCHESTRATE_KEK_SOURCE"] = "file"
    env["PYCHESTRATE_KEK_ID"] = "anon-probe-kek"
    env["PYCHESTRATE_KEK_FILE_PATH"] = kek_path
    for name in (
        "PYCHESTRATE_PEPPER_SOURCE", "PYCHESTRATE_PEPPER_FILE_PATH",
        "PYCHESTRATE_PEPPER_ENV_VAR", "PYCHESTRATE_UI_COOKIE_SECRET_SOURCE",
        "PYCHESTRATE_UI_COOKIE_SECRET_FILE_PATH", "PYCHESTRATE_UI_COOKIE_SECRET_ENV_VAR",
    ):
        env.pop(name, None)

    try:
        alembic_script = os.path.join(os.path.dirname(sys.executable), "alembic")
        upgrade = subprocess.run(
            [alembic_script, "upgrade", "head"],
            cwd=repo_root, env=env, capture_output=True, text=True,
        )
        if upgrade.returncode != 0:
            raise AssertionError(
                "alembic upgrade head failed:{}{}{}".format(
                    os.linesep, upgrade.stdout, upgrade.stderr
                )
            )

        script = _PROBE_SCRIPT_TEMPLATE.format(repo_root=repo_root, sample_id=SAMPLE_ID)
        probe = subprocess.run(
            [sys.executable, "-c", script],
            cwd=repo_root, env=env, capture_output=True, text=True, timeout=600,
        )
    finally:
        for leftover in (db_path, kek_path):
            try:
                os.unlink(leftover)
            except OSError:
                pass
        try:
            os.rmdir(workdir)
        except OSError:
            pass

    result_lines = [
        line for line in probe.stdout.splitlines() if line.startswith("RESULTS: ")
    ]
    if probe.returncode != 0 or len(result_lines) != 1:
        raise AssertionError(
            "production route probe failed (exit {}):{}{}{}{}".format(
                probe.returncode, os.linesep, probe.stdout[-4000:],
                os.linesep, probe.stderr[-4000:],
            )
        )
    _PROBE_RESULTS = json.loads(result_lines[0][len("RESULTS: "):])
    return _PROBE_RESULTS


def _is_verb_route(template: str) -> bool:
    """
        Whether the last path segment carries a ``:verb`` suffix. The
        router answers some of these with 405 before any middleware
        or handler runs (the ``:verb`` routing limitation tracked as
        ORC-07), so they are unreachable rather than exposed.
    """
    last_segment = template.rsplit("/", 1)[-1]
    without_parameters = re.sub(r"\{[^}]*\}", "", last_segment)
    rtnval = ":" in without_parameters
    return rtnval


def test_route_probe_covers_the_rest_surface():
    """
    **Feature: REST anonymous access (LD-12)**
    **Property: the production boot registers and the probe reaches
    the REST surface (well over one hundred route/method pairs), so
    the inventory test below cannot pass vacuously.**
    """
    results = _production_route_probe()
    testbase.assert_equal(len(results) > 100, True)
    return


def test_production_app_refuses_anonymous_requests_off_the_allowlist():
    """
    **Feature: REST anonymous access (LD-12)**
    **Property: in the production app, an anonymous request to any
    /api/v1 route that is not on the allowlist is answered with 401.
    (``:verb`` routes the router cannot reach answer 405.)**
    """
    offenders: List[Tuple[str, str, int]] = []
    for result in _production_route_probe():
        if is_anonymous_request_permitted(result["method"], result["path"]) is True:
            continue
        if result["status"] == 401:
            continue
        if result["status"] == 405 and _is_verb_route(result["template"]) is True:
            continue
        offenders.append((result["method"], result["template"], result["status"]))
    testbase.assert_equal(offenders, [])
    return


def test_every_allowlist_entry_names_a_registered_route():
    """
    **Feature: REST anonymous access (LD-12)**
    **Property: each allowlist entry matches at least one route the
    production app registers, so the list carries no stale
    exemptions.**
    """
    results = _production_route_probe()
    stale: List[str] = []
    for entry in ANONYMOUS_ROUTE_ALLOWLIST:
        matched = False
        for result in results:
            if result["method"] == entry.method and entry.pattern.match(result["path"]):
                matched = True
                break
        if matched is False:
            stale.append("{} {}".format(entry.method, entry.pattern.pattern))
    testbase.assert_equal(stale, [])
    return
