"""
.. module:: test_p13b_webui_foundation_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the webworks-side web UI foundation.

.. moduleauthor:: Code Craft AI LLC

The web UI foundation pieces are exercised in isolation here so
the per-blueprint ports (config / projects / resources, landing
in follow-up sessions) can rely on the contract without
regression.

Two surfaces:

* :mod:`webinterface.foundation.templating` -- jinja2 environment
  + render helper + module-level singleton with a test reset
  hook.
* :mod:`webinterface.foundation.static_files` -- static handler
  with path-traversal protection + content-type detection +
  registration helper.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import tempfile

from typing import Any, Callable, Dict, List, Optional, Tuple

import jinja2

from ccai import testbase
from ccai.webworks.routing.response import HTMLResponse, Response

from ccai.pychestrate.webservice.webinterface.foundation import (
    static_files,
    templating,
)


# ---------------------------------------------------------------------------
# Test stubs
# ---------------------------------------------------------------------------


class _FakeRequest:
    def __init__(
        self,
        *,
        path: str,
        path_params: Optional[Dict[str, Any]] = None
    ) -> None:
        self.path: str = path
        self.path_params: Dict[str, Any] = path_params if path_params is not None else {}
        return


class _FakeApp:
    def __init__(self) -> None:
        self.calls: List[Tuple[str, Tuple[str, ...], Callable]] = []
        return

    def attach_route(
        self, path: str, methods: Optional[List[str]] = None
    ) -> Callable:
        resolved_methods = tuple(methods if methods is not None else ["GET"])

        def decorator(func: Callable) -> Callable:
            self.calls.append((path, resolved_methods, func))
            rtnval = func
            return rtnval

        rtnval = decorator
        return rtnval


def _make_template_dir(*, files: Dict[str, str]) -> str:
    """
        Create a tempdir containing the supplied
        ``{relative_path: contents}`` files. Caller is responsible
        for cleanup via shutil.rmtree.
    """
    rtnval = tempfile.mkdtemp(prefix="pychestrate-tmpl-")
    for rel_path, content in files.items():
        full_path = os.path.join(rtnval, rel_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as fh:
            fh.write(content)
    return rtnval


def _cleanup_dir(path: str) -> None:
    import shutil
    if os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)
    return


# ===========================================================================
# Templating
# ===========================================================================


def test_build_jinja_environment_requires_at_least_one_search_path():
    """
    **Feature: web UI foundation T1.1**
    **Property: An empty ``template_search_paths`` list raises
    ValueError -- alembic-style fast fail rather than producing a
    silently-empty loader.**
    """
    raised = False
    try:
        templating.build_jinja_environment(template_search_paths=[])
    except ValueError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_build_jinja_environment_loads_templates_from_first_path():
    """
    **Feature: web UI foundation T1.1**
    **Property: The environment loads templates from the
    configured search paths and renders them with the supplied
    context.**
    """
    tmpdir = _make_template_dir(files={
        "hello.html": "Hello, {{ name }}!"
    })
    try:
        env = templating.build_jinja_environment(
            template_search_paths=[tmpdir]
        )
        rendered = env.get_template("hello.html").render({"name": "world"})
        testbase.assert_equal(rendered, "Hello, world!")
    finally:
        _cleanup_dir(tmpdir)
    return


def test_build_jinja_environment_autoescapes_html_by_default():
    """
    **Feature: web UI foundation T1.1**
    **Property: Autoescape is enabled by default for HTML
    templates so user-supplied content cannot smuggle script
    tags into rendered pages.**
    """
    tmpdir = _make_template_dir(files={
        "page.html": "<p>{{ user_input }}</p>"
    })
    try:
        env = templating.build_jinja_environment(
            template_search_paths=[tmpdir]
        )
        rendered = env.get_template("page.html").render({
            "user_input": "<script>alert(1)</script>"
        })
        # Autoescape converts < and > to entities.
        has_raw_script = "<script>" in rendered
        has_escaped = "&lt;script&gt;" in rendered
        testbase.assert_equal(has_raw_script, False)
        testbase.assert_equal(has_escaped, True)
    finally:
        _cleanup_dir(tmpdir)
    return


def test_build_jinja_environment_choice_loader_first_path_wins_on_collision():
    """
    **Feature: web UI foundation T1.1**
    **Property: When two search paths each contain a template at
    the same relative path, the first-supplied wins -- mirrors
    flask's blueprint precedence.**
    """
    tmpdir_a = _make_template_dir(files={"shared.html": "from-a"})
    tmpdir_b = _make_template_dir(files={"shared.html": "from-b"})
    try:
        env = templating.build_jinja_environment(
            template_search_paths=[tmpdir_a, tmpdir_b]
        )
        rendered = env.get_template("shared.html").render({})
        testbase.assert_equal(rendered.strip(), "from-a")
    finally:
        _cleanup_dir(tmpdir_a)
        _cleanup_dir(tmpdir_b)
    return


def test_render_template_response_returns_html_response_with_documented_content_type():
    """
    **Feature: web UI foundation T1.1**
    **Property: render_template_response returns an HTMLResponse
    with the ``text/html; charset=utf-8`` content type
    HTMLResponse sets, and the rendered body in bytes.**
    """
    tmpdir = _make_template_dir(files={
        "greeting.html": "<h1>Hi {{ name }}</h1>"
    })
    try:
        env = templating.build_jinja_environment(
            template_search_paths=[tmpdir]
        )
        response = templating.render_template_response(
            template_name="greeting.html",
            context={"name": "Alice"},
            environment=env,
        )

        is_html = isinstance(response, HTMLResponse)
        testbase.assert_equal(is_html, True)
        testbase.assert_equal(response.status_code, 200)
        testbase.assert_equal(
            response.headers["Content-Type"], "text/html; charset=utf-8"
        )
        body_text = response.body.decode("utf-8")
        has_alice = "Alice" in body_text
        testbase.assert_equal(has_alice, True)
    finally:
        _cleanup_dir(tmpdir)
    return


def test_render_template_response_propagates_status_code_and_headers():
    """
    **Feature: web UI foundation T1.1**
    **Property: status_code and additional headers pass through
    to the constructed HTMLResponse.**
    """
    tmpdir = _make_template_dir(files={"err.html": "<p>Not found</p>"})
    try:
        env = templating.build_jinja_environment(
            template_search_paths=[tmpdir]
        )
        response = templating.render_template_response(
            template_name="err.html",
            status_code=404,
            headers={"X-Source": "templating-test"},
            environment=env,
        )
        testbase.assert_equal(response.status_code, 404)
        testbase.assert_equal(
            response.headers["X-Source"], "templating-test"
        )
    finally:
        _cleanup_dir(tmpdir)
    return


def test_render_template_response_uses_module_default_when_no_environment_kwarg():
    """
    **Feature: web UI foundation T1.1**
    **Property: When no environment= kwarg is passed, the call
    falls back to the module-level singleton installed via
    set_default_environment.**
    """
    tmpdir = _make_template_dir(files={"x.html": "x"})
    try:
        env = templating.build_jinja_environment(
            template_search_paths=[tmpdir]
        )
        templating.set_default_environment(environment=env)
        response = templating.render_template_response(
            template_name="x.html"
        )
        testbase.assert_equal(response.status_code, 200)
    finally:
        templating.reset_default_environment_for_testing()
        _cleanup_dir(tmpdir)
    return


def test_get_default_environment_raises_when_not_configured():
    """
    **Feature: web UI foundation T1.1**
    **Property: Calling get_default_environment before any
    set_default_environment raises RuntimeError -- catches the
    "forgot to wire" misconfig at first render attempt.**
    """
    templating.reset_default_environment_for_testing()
    raised = False
    try:
        templating.get_default_environment()
    except RuntimeError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_render_template_response_raises_when_template_not_found():
    """
    **Feature: web UI foundation T1.1**
    **Property: An unknown template propagates jinja's
    TemplateNotFound -- handler-level callers decide the user-
    facing error mapping.**
    """
    tmpdir = _make_template_dir(files={"only.html": "x"})
    try:
        env = templating.build_jinja_environment(
            template_search_paths=[tmpdir]
        )
        raised = False
        try:
            templating.render_template_response(
                template_name="missing.html",
                environment=env,
            )
        except jinja2.TemplateNotFound:
            raised = True
        testbase.assert_equal(raised, True)
    finally:
        _cleanup_dir(tmpdir)
    return


def test_discover_blueprint_template_paths_returns_alphabetical_order():
    """
    **Feature: web UI foundation T1.1**
    **Property: The discovery helper walks
    ``<blueprints_root>/<blueprint>/templates`` and returns the
    template paths in alphabetical blueprint order so the loader
    chain is reproducible across runs.**
    """
    blueprints_root = tempfile.mkdtemp(prefix="pychestrate-bp-")
    try:
        # Create three pseudo-blueprints, two with templates dirs
        # and one without.
        for blueprint in ("zeta", "alpha", "beta"):
            os.makedirs(os.path.join(blueprints_root, blueprint))
        for blueprint in ("alpha", "beta"):
            os.makedirs(
                os.path.join(blueprints_root, blueprint, "templates")
            )
        # ``zeta`` has no templates dir so it should not appear.
        paths = templating.discover_blueprint_template_paths(
            blueprints_root=blueprints_root
        )
        names = [os.path.basename(os.path.dirname(p)) for p in paths]
        testbase.assert_equal(names, ["alpha", "beta"])
    finally:
        _cleanup_dir(blueprints_root)
    return


def test_discover_blueprint_template_paths_returns_empty_when_root_missing():
    """
    **Feature: web UI foundation T1.1**
    **Property: A non-existent blueprints_root returns an empty
    list rather than raising. Lets the bootstrap call this
    unconditionally during early-bring-up phases when the
    webinterface tree may not be present.**
    """
    paths = templating.discover_blueprint_template_paths(
        blueprints_root="/nonexistent/path/does/not/exist"
    )
    testbase.assert_equal(paths, [])
    return


# ===========================================================================
# Static files
# ===========================================================================


def test_serve_static_file_returns_200_with_content_type():
    """
    **Feature: web UI foundation T1.1**
    **Property: A request that resolves to an existing file
    returns 200 with file bytes and a guessed Content-Type.**
    """
    tmpdir = tempfile.mkdtemp(prefix="pychestrate-static-")
    try:
        css_path = os.path.join(tmpdir, "main.css")
        with open(css_path, "w", encoding="utf-8") as fh:
            fh.write("body { background: white; }")

        request = _FakeRequest(
            path="/static/main.css",
            path_params={"filepath": "main.css"},
        )
        response = static_files.serve_static_file(
            request=request, static_root=tmpdir
        )
        testbase.assert_equal(response.status_code, 200)
        testbase.assert_equal(
            response.headers["Content-Type"], "text/css"
        )
        body_text = response.body.decode("utf-8")
        testbase.assert_equal("background: white" in body_text, True)
    finally:
        _cleanup_dir(tmpdir)
    return


def test_serve_static_file_falls_back_to_octet_stream_on_unknown_extension():
    """
    **Feature: web UI foundation T1.1**
    **Property: A file with an unknown extension serves with
    application/octet-stream -- safe default browsers do NOT
    auto-render.**
    """
    tmpdir = tempfile.mkdtemp(prefix="pychestrate-static-")
    try:
        with open(os.path.join(tmpdir, "data.unknownext"), "wb") as fh:
            fh.write(b"\x00\x01\x02")

        request = _FakeRequest(
            path="/static/data.unknownext",
            path_params={"filepath": "data.unknownext"},
        )
        response = static_files.serve_static_file(
            request=request, static_root=tmpdir
        )
        testbase.assert_equal(response.status_code, 200)
        testbase.assert_equal(
            response.headers["Content-Type"],
            static_files.DEFAULT_CONTENT_TYPE,
        )
    finally:
        _cleanup_dir(tmpdir)
    return


def test_serve_static_file_returns_404_when_file_missing():
    """
    **Feature: web UI foundation T1.1**
    **Property: A request for a non-existent file under the root
    returns 404 with empty body -- standard webworks shape.**
    """
    tmpdir = tempfile.mkdtemp(prefix="pychestrate-static-")
    try:
        request = _FakeRequest(
            path="/static/missing.css",
            path_params={"filepath": "missing.css"},
        )
        response = static_files.serve_static_file(
            request=request, static_root=tmpdir
        )
        testbase.assert_equal(response.status_code, 404)
        testbase.assert_equal(response.body, b"")
    finally:
        _cleanup_dir(tmpdir)
    return


def test_serve_static_file_refuses_path_traversal():
    """
    **Feature: web UI foundation T1.1**
    **Property: A request whose path resolves outside the
    configured root returns 404 even if the file would otherwise
    exist. The handler MUST NOT serve ``../etc/passwd``-style
    paths.**
    """
    tmpdir = tempfile.mkdtemp(prefix="pychestrate-static-")
    secret_path = os.path.join(tmpdir, "..", "secret-outside.txt")
    real_secret_path = os.path.realpath(secret_path)
    try:
        # Create a file outside the static root.
        with open(real_secret_path, "w", encoding="utf-8") as fh:
            fh.write("operator-secret")

        request = _FakeRequest(
            path="/static/../secret-outside.txt",
            path_params={"filepath": "../secret-outside.txt"},
        )
        response = static_files.serve_static_file(
            request=request, static_root=tmpdir
        )
        testbase.assert_equal(response.status_code, 404)
    finally:
        if os.path.exists(real_secret_path):
            os.remove(real_secret_path)
        _cleanup_dir(tmpdir)
    return


def test_serve_static_file_returns_404_when_filepath_param_missing():
    """
    **Feature: web UI foundation T1.1**
    **Property: A request with no filepath path-param returns
    404 -- defensive for misregistered routes.**
    """
    tmpdir = tempfile.mkdtemp(prefix="pychestrate-static-")
    try:
        request = _FakeRequest(path="/static/")
        response = static_files.serve_static_file(
            request=request, static_root=tmpdir
        )
        testbase.assert_equal(response.status_code, 404)
    finally:
        _cleanup_dir(tmpdir)
    return


def test_register_static_routes_attaches_path_converter_route():
    """
    **Feature: web UI foundation T1.1**
    **Property: register_static_routes attaches a single GET
    route under ``{url_prefix}/{filepath:path}`` -- the ``:path``
    converter matches multi-segment paths so
    ``/static/styles/main.css`` resolves correctly.**
    """
    tmpdir = tempfile.mkdtemp(prefix="pychestrate-static-")
    try:
        app = _FakeApp()
        static_files.register_static_routes(
            app=app, url_prefix="/static", static_root=tmpdir
        )
        testbase.assert_equal(len(app.calls), 1)
        path, methods, _ = app.calls[0]
        testbase.assert_equal(path, "/static/{filepath:path}")
        testbase.assert_equal(methods, ("GET",))
    finally:
        _cleanup_dir(tmpdir)
    return


def test_register_static_routes_refuses_missing_static_root():
    """
    **Feature: web UI foundation T1.1**
    **Property: A non-existent static_root raises ValueError.
    Catches the misconfig at startup rather than on first request
    that 404s.**
    """
    raised = False
    try:
        static_files.register_static_routes(
            app=_FakeApp(),
            url_prefix="/static",
            static_root="/nonexistent/path/does/not/exist",
        )
    except ValueError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_register_static_routes_refuses_empty_url_prefix():
    """
    **Feature: web UI foundation T1.1**
    **Property: An empty url_prefix raises ValueError.**
    """
    tmpdir = tempfile.mkdtemp(prefix="pychestrate-static-")
    try:
        raised = False
        try:
            static_files.register_static_routes(
                app=_FakeApp(),
                url_prefix="",
                static_root=tmpdir,
            )
        except ValueError:
            raised = True
        testbase.assert_equal(raised, True)
    finally:
        _cleanup_dir(tmpdir)
    return


# ---------------------------------------------------------------------------
# Bootstrap source-smoke
# ---------------------------------------------------------------------------


def test_bootstrap_imports_register_static_routes_and_calls_it():
    """
    **Feature: web UI foundation T1.1**
    **Property: app_pychestrate_main.py wires register_static_routes
    into register_service_extensions, pointed at SITE_DIRECTORIES.
    DIR_STATIC. Source-level smoke; full app boot is out of scope.**
    """
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
        "from ccai.pychestrate.webservice.webinterface.foundation.static_files import"
        in text
    )
    has_call = "register_static_routes(" in text
    has_url_prefix = '"/static"' in text
    testbase.assert_equal(has_import, True)
    testbase.assert_equal(has_call, True)
    testbase.assert_equal(has_url_prefix, True)
    return
