"""
.. module:: tests.singlehost.pychestrate.webservice.phase13._shell_browser_harness
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Serve the real site-shell document, static tree and
               component library to Chromium without a server.

.. moduleauthor:: Code Craft AI LLC

The site-shell and component-library regressions are browser
behavior: landmarks in the composed (shadow-piercing) tree, what a
combobox is named, whether a pager offers page 2, what a 390px
header shows. These helpers let a phase-13 test drive the served
artifacts in headless Chromium with no running pychestrate
instance:

* Every request to :data:`FAKE_ORIGIN` is fulfilled in-process by a
  Playwright route handler.
* ``/static/*`` and ``/mj/*`` are read from the same directories the
  bootstrap mounts (the site static tree and the installed
  codecraftai-webworks ``static/`` directory).
* Any other non-API path returns the shell document rendered from
  ``site_shell/shell_document.html`` through the phase-13 strict
  jinja environment.
* ``/api/v1/me/permissions`` and ``/api/v1/me/navigation`` answer as
  for an administrator; tests add their own API stubs for the
  feature bundles they load.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import mimetypes
import os
import urllib.parse

from typing import Any, Callable, Dict, List, Optional

from ccai.pychestrate.webservice.metadata import SITE_DIRECTORIES
from ccai.pychestrate.webservice.webinterface.site_shell.nav_manifest import (
    NAV_ENTRIES,
    NAV_GROUPS,
    build_navigation_manifest,
)
from ccai.pychestrate.webservice.webinterface.site_shell.shell_document import (
    SHELL_TEMPLATE_NAME,
)

from ccai.tests.singlehost.pychestrate.webservice.phase13._template_harness import (
    strict_environment,
)


FAKE_ORIGIN: str = "http://pychestrate.test"

#: Path that answers an empty document (fixture pages replace it).
FIXTURE_PATH: str = "/__fixture__"

#: Milliseconds to wait for the shell / bundles to settle.
READY_TIMEOUT_MS: int = 15_000

#: Display name the rendered shell document carries.
SHELL_USER_DISPLAY_NAME: str = "Ada Admin"
SHELL_USER_LOGIN_NAME: str = "admin"

#: The release the test shell document reports (the account menu shows it).
SHELL_SERVICE_VERSION: str = "9.9.9-test"

#: Where the test shell document says the user guide is (the account menu links to it).
SHELL_USER_GUIDE_URL: str = "/docs/"

#: Dict of API path -> JSON-serializable body (or callable(query) -> body).
ApiStubs = Dict[str, Any]


_MIME_OVERRIDES: Dict[str, str] = {
    ".js": "text/javascript",
    ".mjs": "text/javascript",
    ".css": "text/css",
    ".svg": "image/svg+xml",
    ".json": "application/json",
}


def webworks_static_root() -> str:
    """
        The installed codecraftai-webworks ``static/`` directory, the
        one the bootstrap mounts at ``/mj``.

        :returns: Absolute path.
    """
    import ccai.webworks as webworks_package  # noqa: E402
    rtnval = os.path.join(os.path.dirname(webworks_package.__file__), "static")
    return rtnval


def all_navigation_permissions() -> List[str]:
    """
        Every permission key the navigation manifest references, i.e.
        what an administrator effectively holds for navigation.

        :returns: Sorted list of permission keys.
    """
    keys = set()
    for group in NAV_GROUPS:
        keys.update(group.required_permissions)
    for entry in NAV_ENTRIES:
        keys.update(entry.required_permissions)
    rtnval = sorted(keys)
    return rtnval


def bundle_stylesheets_for(bundle_names: List[str]) -> List[str]:
    """
        The bundles that ship a ``<bundle>/<bundle>.css`` (mirrors
        ``shell_document._bundle_stylesheets_for``).

        :param bundle_names: Bundle names.

        :returns: Bundle names with a stylesheet on disk.
    """
    rtnval: List[str] = []
    for bundle_name in bundle_names:
        candidate = os.path.join(
            SITE_DIRECTORIES.DIR_STATIC, "javascript", bundle_name, bundle_name + ".css"
        )
        if os.path.isfile(candidate):
            rtnval.append(bundle_name)
    return rtnval


def render_shell_html(*, path: str, bundle_names: List[str]) -> str:
    """
        Render the site-shell document the way
        ``render_shell_document`` does for ``path``.

        :param path: Request path the document is rendered for.
        :param bundle_names: Bundles to import (``pyc-site-shell``
                             first).

        :returns: HTML text.
    """
    environment = strict_environment()
    template = environment.get_template(SHELL_TEMPLATE_NAME)
    context = {
        "page_title": "Pychestrate",
        "initial_route": path,
        "bundle_names": list(bundle_names),
        "bundle_stylesheets": bundle_stylesheets_for(bundle_names),
        "content_html": "",
        "csrf_token": "test-csrf-token",
        "user_display_name": SHELL_USER_DISPLAY_NAME,
        "user_login_name": SHELL_USER_LOGIN_NAME,
        "service_version": SHELL_SERVICE_VERSION,
        "user_guide_url": SHELL_USER_GUIDE_URL,
    }
    rtnval = template.render(**context)
    return rtnval


def _file_response(*, root: str, relative_path: str) -> Optional[Dict[str, Any]]:
    """
        Read ``relative_path`` under ``root`` for a route fulfilment.

        :returns: ``{"status", "headers", "body"}`` or ``None`` when the
                  file does not exist or escapes the root.
    """
    resolved_root = os.path.realpath(root)
    candidate = os.path.realpath(os.path.join(root, relative_path))
    if candidate.startswith(resolved_root + os.sep) is False:
        return None
    if os.path.isfile(candidate) is False:
        return None
    with open(candidate, "rb") as fh:
        body = fh.read()
    extension = os.path.splitext(candidate)[1].lower()
    content_type = _MIME_OVERRIDES.get(extension, None)
    if content_type is None:
        guessed, _ = mimetypes.guess_type(candidate)
        content_type = guessed if guessed is not None else "application/octet-stream"
    rtnval = {"status": 200, "headers": {"Content-Type": content_type}, "body": body}
    return rtnval


def _json_response(body: Any) -> Dict[str, Any]:
    rtnval = {
        "status": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body).encode("utf-8"),
    }
    return rtnval


def install_site_routes(
        context: Any,
        *,
        bundle_names: List[str],
        api_stubs: Optional[ApiStubs] = None,
        blocked_paths: Optional[List[str]] = None
    ) -> None:
    """
        Route every request to :data:`FAKE_ORIGIN` for a browser
        context: static files, ``/mj`` files, the shell document, and
        stubbed API answers.

        :param context: Playwright ``BrowserContext``.
        :param bundle_names: Bundles the shell document imports.
        :param api_stubs: Extra ``/api/...`` path -> body stubs. A
                          callable value is called with the parsed
                          query dict. Unknown API paths answer
                          ``{"items": [], "meta": {"total": 0}}``.
        :param blocked_paths: Paths whose requests are aborted (to
                              observe the page before a script runs).

        :returns: None.
    """
    stubs: ApiStubs = {
        "/api/v1/me/permissions": {"permissions": all_navigation_permissions()},
        "/api/v1/me/navigation": build_navigation_manifest(
            held_permissions=all_navigation_permissions()
        ),
    }
    if api_stubs is not None:
        stubs.update(api_stubs)
    blocked = set(blocked_paths if blocked_paths is not None else [])
    static_root = SITE_DIRECTORIES.DIR_STATIC
    mj_root = webworks_static_root()

    def handler(route: Any) -> None:
        parsed = urllib.parse.urlparse(route.request.url)
        path = parsed.path
        if path in blocked:
            route.abort()
            return
        response: Optional[Dict[str, Any]] = None
        if path.startswith("/static/"):
            response = _file_response(root=static_root, relative_path=path[len("/static/"):])
        elif path.startswith("/mj/"):
            response = _file_response(root=mj_root, relative_path=path[len("/mj/"):])
        elif path.startswith("/api/"):
            stub = stubs.get(path, None)
            if callable(stub) is True:
                query = dict(urllib.parse.parse_qsl(parsed.query))
                response = _json_response(stub(query))
            elif stub is not None:
                response = _json_response(stub)
            elif route.request.method != "GET":
                response = {"status": 204, "headers": {}, "body": b""}
            else:
                response = _json_response({"items": [], "meta": {"total": 0, "page": 1, "per_page": 25}})
        elif path == "/favicon.ico":
            response = {"status": 404, "headers": {}, "body": b""}
        elif path == FIXTURE_PATH:
            response = {
                "status": 200,
                "headers": {"Content-Type": "text/html; charset=utf-8"},
                "body": b"<!DOCTYPE html><title>fixture</title>",
            }
        else:
            html = render_shell_html(path=path, bundle_names=bundle_names)
            response = {
                "status": 200,
                "headers": {"Content-Type": "text/html; charset=utf-8"},
                "body": html.encode("utf-8"),
            }
        if response is None:
            route.fulfill(status=404, body=b"")
            return
        route.fulfill(status=response["status"], headers=response["headers"], body=response["body"])
        return

    context.route(FAKE_ORIGIN + "/**", handler)
    return


def open_shell_page(
        browser: Any,
        *,
        path: str = "/",
        bundle_names: Optional[List[str]] = None,
        api_stubs: Optional[ApiStubs] = None,
        blocked_paths: Optional[List[str]] = None,
        wait_for_ready: bool = True,
        **context_options: Any
    ) -> Any:
    """
        Open ``path`` on the fake origin in a fresh browser context and
        (by default) wait until ``<pyc-site-shell>`` reports ready.

        :param browser: Playwright ``Browser``.
        :param path: Path to open.
        :param bundle_names: Bundles the shell document imports
                             (default: only ``pyc-site-shell``).
        :param api_stubs: Extra API stubs (see
                          :func:`install_site_routes`).
        :param blocked_paths: Paths whose requests are aborted.
        :param wait_for_ready: Wait for the shell ready flag.
        :param context_options: ``browser.new_context`` options
                                (``viewport``, ``color_scheme``,
                                ``has_touch`` ...).

        :returns: The Playwright ``Page``; close ``page.context`` when
                  done.
    """
    names = bundle_names if bundle_names is not None else ["pyc-site-shell"]
    context = browser.new_context(**context_options)
    install_site_routes(
        context,
        bundle_names=names,
        api_stubs=api_stubs,
        blocked_paths=blocked_paths,
    )
    page = context.new_page()
    page.set_default_timeout(READY_TIMEOUT_MS)
    page.goto(FAKE_ORIGIN + path)
    if wait_for_ready is True:
        page.wait_for_function(
            "() => { const shell = document.querySelector('pyc-site-shell'); "
            "return shell !== null && shell.isReady === true; }"
        )
    return page


def open_fixture_page(browser: Any, *, body_html: str, **context_options: Any) -> Any:
    """
        Open a bare document on the fake origin that loads the served
        component library (``pyc-mj-lib``) and the ``/mj`` design
        tokens, holding ``body_html``.

        :param browser: Playwright ``Browser``.
        :param body_html: Markup for the document body.
        :param context_options: ``browser.new_context`` options.

        :returns: The Playwright ``Page``; close ``page.context`` when
                  done.
    """
    context = browser.new_context(**context_options)
    install_site_routes(context, bundle_names=["pyc-site-shell"])
    page = context.new_page()
    page.set_default_timeout(READY_TIMEOUT_MS)
    page.goto(FAKE_ORIGIN + FIXTURE_PATH)
    document = (
        "<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<link rel=\"stylesheet\" href=\"/mj/styles/tokens.css\">"
        "<link rel=\"stylesheet\" href=\"/mj/styles/base.css\">"
        "<script type=\"module\" src=\"/static/javascript/pyc-mj-lib/index.js\"></script>"
        "</head><body>" + body_html + "</body></html>"
    )
    page.set_content(document)
    page.wait_for_function("() => customElements.get('mj-select') !== undefined")
    return page


#: JS: raw ``mj.<component>.<key>`` catalog keys visible anywhere in
#: the composed tree (rendered text or aria-label / title).
RAW_CATALOG_KEYS_JS: str = r"""
() => {
  const pattern = /\bmj\.[a-zA-Z]+\.[a-zA-Z]+/;
  const found = [];
  const rendered = (el) => typeof el.checkVisibility === 'function' ? el.checkVisibility() : el.getClientRects().length > 0;
  const scanText = (root) => {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    let node = walker.nextNode();
    while (node !== null) {
      const parent = node.parentElement;
      if (parent !== null && pattern.test(node.textContent) && rendered(parent)) {
        found.push(node.textContent.trim().slice(0, 60));
      }
      node = walker.nextNode();
    }
  };
  const walk = (root) => {
    scanText(root);
    for (const el of root.querySelectorAll('*')) {
      for (const attr of ['aria-label', 'title']) {
        const value = el.getAttribute(attr);
        if (value !== null && pattern.test(value)) {
          found.push(attr + '=' + value);
        }
      }
      if (el.shadowRoot) {
        walk(el.shadowRoot);
      }
    }
  };
  walk(document.body);
  return found;
}
"""


#: JS: the element that really has focus (through open shadow roots),
#: described as ``{"id", "cls", "text", "inSidebar"}``.
DEEP_FOCUS_JS: str = r"""
() => {
  let active = document.activeElement;
  while (active !== null && active.shadowRoot && active.shadowRoot.activeElement) {
    active = active.shadowRoot.activeElement;
  }
  if (active === null) {
    return null;
  }
  return {
    id: active.id || '',
    cls: typeof active.className === 'string' ? active.className : '',
    text: (active.textContent || '').trim().slice(0, 40),
    inSidebar: active.closest ? active.closest('mj-side-nav') !== null : false
  };
}
"""


__all__ = [
    "ApiStubs",
    "DEEP_FOCUS_JS",
    "FAKE_ORIGIN",
    "FIXTURE_PATH",
    "RAW_CATALOG_KEYS_JS",
    "READY_TIMEOUT_MS",
    "SHELL_USER_DISPLAY_NAME",
    "all_navigation_permissions",
    "install_site_routes",
    "open_fixture_page",
    "open_shell_page",
    "render_shell_html",
    "webworks_static_root",
]
