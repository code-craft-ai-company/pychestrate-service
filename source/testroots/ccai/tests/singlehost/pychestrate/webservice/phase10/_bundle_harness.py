"""
.. module:: tests.singlehost.pychestrate.webservice.phase10._bundle_harness
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Offline browser harness for the ``pyc-*`` bundle views.

.. moduleauthor:: Code Craft AI LLC

The ``pyc-*`` bundles are Web Components that talk to the REST API
with ``fetch``. This harness runs a committed bundle (the served
``index.js``) in a real Chromium page without a server:

* every request to :data:`FAKE_ORIGIN` is answered through
  Playwright request routing -- ``/static/...`` from the checkout's
  static directory, ``/api/...`` from a :class:`FakeApi` the test
  scripts;
* the page loads the ``pyc-mj-lib`` component library first (as the
  shell document does) and then imports the bundle, which defines
  its custom elements;
* :class:`FakeApi` records every API request (method, path, query,
  JSON body) so tests assert on what the view actually sent.

Nothing leaves the process: the origin is fake and no socket is
opened.

The browser lives on its own thread (:class:`ThreadedBrowser`).
Playwright's sync API refuses to start a second instance on a thread
that already runs one, and the phase-11 suite owns a session-scoped
sync browser on the main thread; running this harness's browser on a
dedicated worker thread keeps the two independent. Tests hand a
scenario callable to :meth:`ThreadedBrowser.run` and make their
assertions on the returned values in the test thread.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import mimetypes
import os

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Generator, List, Optional, Tuple
from urllib.parse import parse_qs, urlsplit

from ccai import testbase

from ccai.pychestrate.webservice.metadata import SITE_DIRECTORIES


FAKE_ORIGIN: str = "http://pyc-bundles.test"
HARNESS_PAGE_PATH: str = "/__bundle_harness"
READY_TIMEOUT_MS: int = 15_000

STATIC_ROOT: str = SITE_DIRECTORIES.DIR_STATIC


@dataclass
class RecordedRequest:
    """
        One API request the page sent.

        :ivar method: HTTP method, upper case.
        :ivar path: URL path (no query string).
        :ivar query: Decoded query parameters (first value per key).
        :ivar body: Decoded JSON body, or ``None``.
    """
    method: str
    path: str
    query: Dict[str, str] = field(default_factory=dict)
    body: Any = None


Responder = Callable[[RecordedRequest], Tuple[int, Any]]


class FakeApi:
    """
        Scriptable stand-in for the REST API. Responses are matched
        on ``(method, path)``; the most recently registered match
        wins so a test can override a default. Unmatched requests
        answer 404 with a problem document.
    """

    def __init__(self) -> None:
        self._responders: List[Tuple[str, str, Responder]] = []
        self.requests: List[RecordedRequest] = []
        return

    def respond(
            self,
            *,
            method: str,
            path: str,
            status: int = 200,
            body: Any = None
        ) -> None:
        """
            Answer ``method path`` with a fixed JSON body.

            :param method: HTTP method.
            :param path: Exact URL path.
            :param status: HTTP status code.
            :param body: JSON-serializable body.

            :returns: None.
        """
        def _fixed(_request: RecordedRequest) -> Tuple[int, Any]:
            rtnval = (status, body)
            return rtnval

        self._responders.append((method.upper(), path, _fixed))
        return

    def respond_with(
            self,
            *,
            method: str,
            path: str,
            handler: Responder
        ) -> None:
        """
            Answer ``method path`` by calling ``handler``.

            :param method: HTTP method.
            :param path: Exact URL path.
            :param handler: ``(RecordedRequest) -> (status, body)``.

            :returns: None.
        """
        self._responders.append((method.upper(), path, handler))
        return

    def requests_for(self, *, method: str, path: str) -> List[RecordedRequest]:
        """
            The recorded requests matching ``method path``.

            :param method: HTTP method.
            :param path: Exact URL path.

            :returns: Matching requests, oldest first.
        """
        rtnval = [
            recorded for recorded in self.requests
            if recorded.method == method.upper() and recorded.path == path
        ]
        return rtnval

    def answer(self, *, recorded: RecordedRequest) -> Tuple[int, Any]:
        """
            Resolve the response for a recorded request.

            :param recorded: The request.

            :returns: ``(status, body)``.
        """
        for method, path, handler in reversed(self._responders):
            if method == recorded.method and path == recorded.path:
                rtnval = handler(recorded)
                return rtnval
        rtnval = (
            404,
            {
                "type": "about:blank",
                "title": "Not Found",
                "status": 404,
                "detail": "No fake response for {} {}".format(
                    recorded.method, recorded.path,
                ),
            },
        )
        return rtnval


def _harness_html(*, bundle: str) -> str:
    """
        The harness page: loads the component library, then the bundle.

        :param bundle: Bundle directory name (e.g. ``pyc-ops-bundle``).

        :returns: HTML text.
    """
    rtnval = (
        "<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"UTF-8\">"
        "<title>bundle harness</title></head><body>"
        "<main class=\"harness-host\"></main>"
        "<script type=\"module\">"
        "window.__pycHarnessErrors = [];"
        "window.addEventListener('error', (e) => { window.__pycHarnessErrors.push(String(e.message)); });"
        "await import('/static/javascript/pyc-mj-lib/index.js');"
        "window.__pycBundle = await import('/static/javascript/" + bundle + "/index.js');"
        "window.__pycHarnessReady = true;"
        "</script></body></html>"
    )
    return rtnval


def _static_file(*, url_path: str) -> Optional[Tuple[bytes, str]]:
    """
        Read a file below :data:`STATIC_ROOT` for a ``/static/...``
        URL path.

        :param url_path: URL path starting with ``/static/``.

        :returns: ``(bytes, content_type)`` or ``None`` when missing.
    """
    relative = url_path[len("/static/"):]
    candidate = os.path.normpath(os.path.join(STATIC_ROOT, relative))
    if candidate.startswith(os.path.normpath(STATIC_ROOT) + os.sep) is False:
        return None
    if os.path.isfile(candidate) is False:
        return None
    with open(candidate, "rb") as handle:
        content = handle.read()
    content_type = mimetypes.guess_type(candidate)[0] or "application/octet-stream"
    if candidate.endswith(".js"):
        content_type = "application/javascript"
    rtnval = (content, content_type)
    return rtnval


def _decode_json_body(raw: Optional[str]) -> Any:
    if raw is None or len(raw) == 0:
        return None
    try:
        rtnval = json.loads(raw)
    except ValueError:
        rtnval = raw
    return rtnval


def open_bundle_page(*, browser: Any, api: FakeApi, bundle: str) -> Tuple[Any, Any]:
    """
        Open a fresh context + page with ``bundle`` loaded.

        :param browser: Playwright :class:`Browser`.
        :param api: The :class:`FakeApi` answering ``/api/...``.
        :param bundle: Bundle directory name.

        :returns: ``(context, page)``; close the context when done.
    """
    context = browser.new_context()
    page = context.new_page()
    html = _harness_html(bundle=bundle)

    def _route(route: Any, request: Any) -> None:
        parts = urlsplit(request.url)
        path = parts.path
        if path == HARNESS_PAGE_PATH:
            route.fulfill(status=200, content_type="text/html", body=html)
            return
        if path.startswith("/static/"):
            served = _static_file(url_path=path)
            if served is None:
                route.fulfill(status=404, content_type="text/plain", body="missing")
                return
            route.fulfill(status=200, content_type=served[1], body=served[0])
            return
        if path.startswith("/api/"):
            query = {
                key: values[0]
                for key, values in parse_qs(parts.query).items()
                if len(values) > 0
            }
            recorded = RecordedRequest(
                method=request.method.upper(),
                path=path,
                query=query,
                body=_decode_json_body(request.post_data),
            )
            api.requests.append(recorded)
            status, body = api.answer(recorded=recorded)
            content_type = "application/json"
            if status >= 400:
                content_type = "application/problem+json"
            route.fulfill(
                status=status,
                content_type=content_type,
                body=json.dumps(body if body is not None else {}),
            )
            return
        route.fulfill(status=404, content_type="text/plain", body="not routed")
        return

    page.route(FAKE_ORIGIN + "/**", _route)
    page.goto(FAKE_ORIGIN + HARNESS_PAGE_PATH)
    page.wait_for_function(
        "window.__pycHarnessReady === true", timeout=READY_TIMEOUT_MS,
    )
    rtnval = (context, page)
    return rtnval


def mount_element(*, page: Any, tag: str) -> None:
    """
        Create ``<tag>`` inside the harness host so its
        ``connectedCallback`` runs.

        :param page: Playwright page from :func:`open_bundle_page`.
        :param tag: Custom-element tag name.

        :returns: None.
    """
    page.evaluate(
        "(tag) => { const host = document.querySelector('main.harness-host');"
        " host.replaceChildren(document.createElement(tag)); }",
        tag,
    )
    return


def wait_for_request(
        *,
        page: Any,
        api: FakeApi,
        method: str,
        path: str,
        count: int = 1,
        timeout_ms: int = 10_000
    ) -> List[RecordedRequest]:
    """
        Pump the page until ``api`` has recorded ``count`` matching
        requests.

        :param page: Playwright page.
        :param api: The fake API.
        :param method: HTTP method.
        :param path: Exact URL path.
        :param count: Requests to wait for.
        :param timeout_ms: Give-up bound.

        :returns: The matching requests.

        :raises: AssertionError when they do not arrive in time.
    """
    waited = 0
    step_ms = 50
    while waited <= timeout_ms:
        matches = api.requests_for(method=method, path=path)
        if len(matches) >= count:
            return matches
        page.wait_for_timeout(step_ms)
        waited = waited + step_ms
    err_lines = ["Expected API request never arrived."]
    err_lines.append("EXPECTED: {} {} x{}".format(method, path, count))
    err_lines.append("SEEN: {}".format(
        ["{} {}".format(r.method, r.path) for r in api.requests],
    ))
    raise AssertionError(os.linesep.join(err_lines))


class ThreadedBrowser:
    """
        A headless Chromium owned by a single dedicated worker thread.
        Every Playwright call happens on that thread; callers submit a
        scenario ``fn(browser) -> result`` through :meth:`run`.
    """

    def __init__(self) -> None:
        self._executor: ThreadPoolExecutor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="pyc-bundle-browser",
        )
        self._playwright: Any = None
        self._browser: Any = None
        return

    def start(self) -> None:
        """
            Start Playwright and launch Chromium on the worker thread.

            :returns: None.
        """
        self._executor.submit(self._start_on_worker).result()
        return

    def run(self, fn: Callable[[Any], Any]) -> Any:
        """
            Run ``fn(browser)`` on the worker thread and return its
            result; exceptions propagate to the caller.

            :param fn: Scenario callable taking the Playwright browser.

            :returns: Whatever ``fn`` returns.
        """
        rtnval = self._executor.submit(fn, self._browser).result()
        return rtnval

    def close(self) -> None:
        """
            Close the browser and stop Playwright, then release the
            worker thread.

            :returns: None.
        """
        try:
            self._executor.submit(self._close_on_worker).result()
        finally:
            self._executor.shutdown(wait=True)
        return

    def _start_on_worker(self) -> None:
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=True)
        return

    def _close_on_worker(self) -> None:
        try:
            if self._browser is not None:
                self._browser.close()
        finally:
            if self._playwright is not None:
                self._playwright.stop()
        return


@testbase.register.resource_factory()
def create_threaded_bundle_browser(
        constraints: Optional[Dict[str, Any]] = None,
    ) -> Generator[ThreadedBrowser, None, None]:
    """
        Yield a started :class:`ThreadedBrowser` for the bundle UI
        tests; closed on the way out.

        :param constraints: Unused; accepted for the factory protocol.

        :yields: The running :class:`ThreadedBrowser`.
    """
    _ = constraints
    threaded = ThreadedBrowser()
    threaded.start()
    try:
        yield threaded
    finally:
        threaded.close()
    return


__all__ = [
    "FAKE_ORIGIN",
    "FakeApi",
    "RecordedRequest",
    "ThreadedBrowser",
    "create_threaded_bundle_browser",
    "open_bundle_page",
    "mount_element",
    "wait_for_request",
]
