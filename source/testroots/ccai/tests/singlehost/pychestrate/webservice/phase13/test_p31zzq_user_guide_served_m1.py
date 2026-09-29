"""
.. module:: test_p31zzq_user_guide_served_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The service serves its own user guide and links to it (DOC-20).

.. moduleauthor:: Code Craft AI LLC

The product linked to no documentation of its own, and the plugin catalog's
addresses named a host nothing publishes. The service is self-hosted, often
behind a firewall, so it now serves the guide it shipped with: ``make
docs-into-service`` installs the built Sphinx site beside the static assets and
the app mounts it at ``/docs``. The account menu shows a "User guide" link only
when the guide is installed, and the plugin catalog's addresses point at the
guide's own catalog pages. These tests hold that the routes serve the files
safely, that the link is offered only when the guide is there, and that every
plugin address names a page a real build produces.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import os
import shutil
import subprocess
import sys
import tempfile

from typing import Any, Dict, List, Optional, Tuple

from playwright.sync_api import Browser

from ccai import testbase

from ccai.pychestrate.webservice import public_endpoint
from ccai.pychestrate.webservice.webinterface.site_shell import shell_document, user_guide_route

from ccai.testshared.factories.browsers.playwright_browser import (
    create_playwright_browser,
)

from ccai.tests.singlehost.pychestrate.webservice.phase13._shell_browser_harness import (
    SHELL_USER_GUIDE_URL,
    open_shell_page,
)
from ccai.tests.singlehost.pychestrate.webservice.phase13._template_harness import strict_environment


testbase.originate.parameter(
    create_playwright_browser,
    identifier="browser",
)


DESKTOP: Dict[str, Any] = {"viewport": {"width": 1440, "height": 900}}


def _guide_dir(*, with_index: bool = True) -> str:
    """A throwaway directory shaped like a built site."""
    root = tempfile.mkdtemp(prefix="pyc-guide-")
    if with_index:
        with open(os.path.join(root, user_guide_route.USER_GUIDE_INDEX_FILE), "w", encoding="utf-8") as handle:
            handle.write("<!doctype html><title>Guide</title><h1>Guide</h1>")
        os.makedirs(os.path.join(root, "_static"))
        with open(os.path.join(root, "_static", "site.css"), "w", encoding="utf-8") as handle:
            handle.write("body{margin:0}")
    return root


def test_the_link_is_offered_only_when_the_guide_is_installed():
    """
    **Feature: the service serves its user guide (DOC-20)**
    **Property: ``user_guide_url`` is "" when there is no built guide and
    "/docs/" when its first page exists; the shell document's value follows the
    install directory and never raises.**
    """
    empty = _guide_dir(with_index=False)
    built = _guide_dir()
    original = user_guide_route.user_guide_root
    try:
        seen = (user_guide_route.user_guide_url(docs_root=empty), user_guide_route.user_guide_url(docs_root=built))
        user_guide_route.user_guide_root = lambda: empty
        absent = shell_document._user_guide_url_for_shell()
        user_guide_route.user_guide_root = lambda: built
        present = shell_document._user_guide_url_for_shell()
    finally:
        user_guide_route.user_guide_root = original
        shutil.rmtree(empty, ignore_errors=True)
        shutil.rmtree(built, ignore_errors=True)

    testbase.assert_equal((seen, absent, present), (("", "/docs/"), "", "/docs/"))
    return


def test_the_guide_is_installed_at_the_checkout_root_outside_the_web_interface_tree():
    """
    **Feature: the service serves its user guide (DOC-20)**
    **Property: ``user_guide_root`` is ``docs-site`` beside ``pyproject.toml``,
    not under the web interface's source tree: the invariant tests scan every
    file under that tree (storage use, colour literals, inline-script nonces)
    and a generated Sphinx site fails them.**
    """
    from ccai.pychestrate.webservice.metadata import SITE_DIRECTORIES

    root = os.path.realpath(user_guide_route.user_guide_root())
    web_interface = os.path.realpath(os.path.join(SITE_DIRECTORIES.DIR_STATIC, os.pardir))
    repo_root = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), *([".."] * 8)))

    testbase.assert_equal(
        (os.path.basename(root), os.path.dirname(root) == os.path.realpath(repo_root), root.startswith(web_interface + os.sep)),
        ("docs-site", True, False),
    )
    return


class _FakeApp:
    """Records the routes attached to it."""

    def __init__(self) -> None:
        self.routes: List[Tuple[str, Tuple[str, ...]]] = []
        self.handlers: Dict[str, Any] = {}

    def attach_route(self, pattern: str, methods: Optional[List[str]] = None) -> Any:
        def _register(handler: Any) -> Any:
            self.routes.append((pattern, tuple(methods or ())))
            self.handlers[pattern] = handler
            return handler
        return _register


class _Request:
    def __init__(self, *, filepath: str = "") -> None:
        self.path_params = {"filepath": filepath}
        self.headers: Dict[str, str] = {}
        self.query_params = {}
        self.cookies: Dict[str, str] = {}
        self.path = "/docs/" + filepath


def test_the_guide_is_mounted_at_docs_and_the_bare_address_goes_to_its_first_page():
    """
    **Feature: the service serves its user guide (DOC-20)**
    **Property: with a built guide, ``/docs`` and ``/docs/`` answer 302 to the
    guide's front page (``/docs/userguide.html``) and the files are served (200, right content type)
    under ``/docs/{filepath}``; a path that climbs out of the directory is
    refused.**
    """
    root = _guide_dir()
    try:
        app = _FakeApp()
        user_guide_route.register_user_guide_routes(app=app, docs_root=root)
        bare = app.handlers["/docs"](_Request())
        slash = app.handlers["/docs/"](_Request())
        file_routes = [pattern for pattern, _methods in app.routes if pattern.startswith("/docs/{")]
        served = app.handlers[file_routes[0]](_Request(filepath="_static/site.css"))
        climbing = app.handlers[file_routes[0]](_Request(filepath="../../etc/passwd"))
    finally:
        shutil.rmtree(root, ignore_errors=True)

    testbase.assert_equal(
        (
            (bare.status_code, bare._headers.get("Location")),
            (slash.status_code, slash._headers.get("Location")),
            len(file_routes),
            served.status_code,
            served._headers.get("Content-Type", "").split(";")[0],
            climbing.status_code,
        ),
        ((302, "/docs/userguide.html"), (302, "/docs/userguide.html"), 1, 200, "text/css", 404),
    )
    return


def test_without_a_built_guide_the_files_are_not_mounted_and_the_address_says_so():
    """
    **Feature: the service serves its user guide (DOC-20)**
    **Property: with no built guide the app still starts (building the guide
    itself boots the app): only the two redirect routes are attached, and
    ``/docs`` answers 404 with a page saying the guide is not installed
    instead of redirecting to a page that is not there.**
    """
    from ccai.pychestrate.webservice.webinterface.site_shell import error_pages

    missing = os.path.join(tempfile.gettempdir(), "pyc-guide-does-not-exist-" + next(tempfile._get_candidate_names()))
    app = _FakeApp()
    calls: List[Dict[str, Any]] = []
    original = error_pages.render_error_response
    error_pages.render_error_response = lambda **kwargs: (calls.append(kwargs) or type("R", (), {"status_code": kwargs["status_code"]})())
    try:
        user_guide_route.register_user_guide_routes(app=app, docs_root=missing)
        answer = app.handlers["/docs"](_Request())
    finally:
        error_pages.render_error_response = original

    testbase.assert_equal(
        (sorted(pattern for pattern, _m in app.routes), answer.status_code, calls[0]["title"]),
        (["/docs", "/docs/"], 404, "The user guide is not installed"),
    )
    return


def test_the_shell_document_carries_the_guides_address_only_when_there_is_one():
    """
    **Feature: the service serves its user guide (DOC-20)**
    **Property: the shell document has a ``user-guide-url`` attribute when the
    server passes an address and none when it passes an empty string.**
    """
    template = strict_environment().get_template("site_shell/shell_document.html")
    base = dict(
        page_title="P", initial_route="/", bundle_names=["pyc-site-shell"], bundle_stylesheets=[], content_html="",
        csrf_token="", user_display_name="", user_login_name="", service_version="", admin_contact="",
    )
    with_guide = template.render(user_guide_url="/docs/", **base)
    without = template.render(user_guide_url="", **base)

    testbase.assert_equal(('user-guide-url="/docs/"' in with_guide, "user-guide-url" in without), (True, False))
    return


def test_the_account_menu_links_to_the_user_guide_first_among_the_help_links(browser: Browser):
    """
    **Feature: the service serves its user guide (DOC-20)**
    **Property: when the shell document names the guide, the account menu has
    a "User guide" link to it, before "API reference" and "Error types".**
    """
    page = open_shell_page(browser, path="/", **DESKTOP)
    try:
        page.click(".pyc-site-shell__account-button")
        page.wait_for_timeout(150)
        panel = page.locator(".pyc-site-shell__account-panel")
        order = page.evaluate(
            "() => Array.from(document.querySelectorAll('.pyc-site-shell__account-panel > *')).map(e => e.textContent.trim().split('\\n')[0].trim())"
        )
        href = panel.get_by_role("link", name="User guide").get_attribute("href")
    finally:
        page.context.close()

    testbase.assert_equal(
        (href, order.index("API tokens") < order.index("User guide") < order.index("API reference") < order.index("Sign out")),
        (SHELL_USER_GUIDE_URL, True),
    )
    return


def test_a_plugin_address_is_made_absolute_only_when_the_service_knows_its_public_address():
    """
    **Feature: the service serves its user guide (DOC-20)**
    **Property: ``public_docs_url`` leaves a relative ``/docs/...`` address as
    it is without a public base URL, prefixes it with one when configured, and
    never touches an address that is already external or empty.**
    """
    original = public_endpoint.resolve_public_base_url
    try:
        public_endpoint.resolve_public_base_url = lambda: None
        plain = public_endpoint.public_docs_url("/docs/extensions/protocols/secrets_backend.html")
        public_endpoint.resolve_public_base_url = lambda: "https://pyc.example.test"
        absolute = public_endpoint.public_docs_url("/docs/extensions/protocols/secrets_backend.html")
        external = public_endpoint.public_docs_url("https://vendor.example.test/docs")
        empty = public_endpoint.public_docs_url("")
    finally:
        public_endpoint.resolve_public_base_url = original

    testbase.assert_equal(
        (plain, absolute, external, empty),
        (
            "/docs/extensions/protocols/secrets_backend.html",
            "https://pyc.example.test/docs/extensions/protocols/secrets_backend.html",
            "https://vendor.example.test/docs",
            "",
        ),
    )
    return


CATALOG_DOCS_URLS_OF_A_FRESH_PROCESS = r"""
import json
from ccai.pychestrate.webservice.extension.docs_ext import load_builtin_declarations
from ccai.pychestrate.webservice.plugin_api.runtime import get_active_catalog
load_builtin_declarations()
catalog = get_active_catalog()
entries = list(catalog.factory_entries) + list(catalog.resource_entries)
print("DOCS_URLS_JSON=" + json.dumps(sorted(entry.metadata.docs_url for entry in entries)))
"""


def test_every_published_plugin_address_names_a_page_a_real_build_produces():
    """
    **Feature: the service serves its user guide (DOC-20)**
    **Property: after a real ``-W`` build of the site, the front page the
    ``/docs`` redirect names exists, every ``docs_url`` in the plugin catalog
    is a ``/docs/...`` path whose file exists in the built site, and no catalog
    page links to the host nothing publishes.**
    """
    repo_root = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), *([".."] * 8)))
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([entry for entry in sys.path if entry])
    listed = subprocess.run(
        [sys.executable, "-c", CATALOG_DOCS_URLS_OF_A_FRESH_PROCESS],
        cwd=repo_root, env=env, capture_output=True, text=True, timeout=300,
    )
    lines = [line for line in listed.stdout.splitlines() if line.startswith("DOCS_URLS_JSON=")]
    testbase.assert_equal((listed.returncode, len(lines)), (0, 1), listed.stderr[-1500:])
    urls = json.loads(lines[0][len("DOCS_URLS_JSON="):])

    output = tempfile.mkdtemp(prefix="pyc-guide-build-")
    try:
        built = subprocess.run(
            [os.path.join(os.path.dirname(sys.executable), "sphinx-build"), "-W", "--keep-going", "-t", "reference", "-b", "html", "userguide", output],
            cwd=repo_root, env=env, capture_output=True, text=True, timeout=600,
        )
        testbase.assert_equal(built.returncode, 0, (built.stdout + built.stderr)[-2000:])
        front_page_built = os.path.isfile(os.path.join(output, user_guide_route.USER_GUIDE_INDEX_FILE))
        missing = [url for url in urls if not os.path.isfile(os.path.join(output, url[len("/docs/"):]))]
        outside = [url for url in urls if not url.startswith("/docs/")]
        old_host = []
        for folder, _dirs, files in os.walk(os.path.join(output, "extensions")):
            for name in files:
                if name.endswith(".html"):
                    with open(os.path.join(folder, name), encoding="utf-8") as handle:
                        if "docs.pychestrate.io" in handle.read():
                            old_host.append(name)
    finally:
        shutil.rmtree(output, ignore_errors=True)

    testbase.assert_equal((front_page_built, len(urls) >= 20, missing, outside, old_host), (True, True, [], [], []))
    return
