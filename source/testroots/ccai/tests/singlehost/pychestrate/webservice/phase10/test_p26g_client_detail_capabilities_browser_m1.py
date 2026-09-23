"""
.. module:: test_p26g_client_detail_capabilities_browser_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Browser test of the client detail page's "Capabilities &
               attributes" section (E2E-18).

.. moduleauthor:: Code Craft AI LLC

A pod advertises its capabilities with ``PUT
/api/v1/clients/{id}/capabilities``; the service keeps them apart from
the attributes operators set on the client record, and serves them at
``GET /api/v1/clients/{id}/capabilities``. The client detail view read
only the attributes, so a pod whose advertisement succeeded was still
shown with "No capabilities reported for this client."

The committed pods bundle (``pyc-pods-bundle/index.js``) is loaded in
headless Chromium from a local stub site that answers the view's REST
calls for four clients -- capabilities only, capabilities and
attributes, neither, and a failing capabilities endpoint -- and the
rendered section is recorded. Each test asserts one property of the
recorded observations.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import os
import threading

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Generator, Optional, Tuple

from playwright.sync_api import sync_playwright

from ccai import testbase
from ccai.testbase.resourcelifespan import ResourceLifespan


PROJECT_ID = "471906de-b71d-4774-8250-c1e7e340bce4"

#: scenario -> (client id, attributes, capabilities response status, body)
SCENARIOS: Dict[str, Tuple[str, Dict[str, Any], int, Any]] = {
    "advertised": (
        "0790e0ed-5f28-4dcc-b932-be9b83d9ee44", {}, 200,
        [{"kind": "rpa", "value": {"job_types": ["hello-echo"], "taskplus": None, "tags": ["gpu"]},
          "revision_token": "r1", "updated_at": "2026-09-23T07:07:17.470863"}],
    ),
    "advertised_and_attributes": (
        "1c6ff194-6f88-4c55-ba6f-ff2af037b0c1", {"location": "lab-1"}, 200,
        [{"kind": "rpa", "value": {"job_types": [], "taskplus": None, "tags": []},
          "revision_token": "r2", "updated_at": "2026-09-23T07:08:00"}],
    ),
    "nothing": (
        "2d3e4f5a-6b7c-4d8e-9f0a-1b2c3d4e5f6a", {}, 200, [],
    ),
    "capabilities_unavailable": (
        "3e4f5a6b-7c8d-4e9f-8a0b-2c3d4e5f6a7b", {"location": "lab-2"}, 500,
        {"title": "Internal Server Error", "status": 500},
    ),
}


def _bundle_path() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.normpath(os.path.join(here, "..", "..", "..", "..", "..", "..", "..", ".."))
    rtnval = os.path.join(
        repo_root, "source", "site", "ccai", "pychestrate", "webservice", "webinterface",
        "static", "javascript", "pyc-pods-bundle", "index.js",
    )
    return rtnval


def _client_record(*, client_id: str, attributes: Dict[str, Any]) -> Dict[str, Any]:
    rtnval = {
        "client_id": client_id, "project_id": PROJECT_ID, "pod_name": "live-pod-01",
        "status": "ACTIVE", "liveness_state": "ALIVE", "enrolled_at": "2026-09-23T06:59:11",
        "last_seen": "2026-09-23T07:07:17", "last_agent_version": None,
        "transport_name": "http-long-poll", "degraded_at": None,
        "revision_token": "rev", "attributes": attributes,
    }
    return rtnval


class _StubSiteHandler(BaseHTTPRequestHandler):
    """
        Serves the pods bundle, a page hosting ``<pyc-client-detail>``,
        and the REST answers the view asks for.
    """

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        return

    def _send(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        return

    def _send_json(self, status: int, payload: Any) -> None:
        self._send(status, "application/json", json.dumps(payload).encode("utf-8"))
        return

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        by_client = {client_id: (attributes, status, body)
                     for client_id, attributes, status, body in SCENARIOS.values()}
        if path == "/static/javascript/pyc-pods-bundle/index.js":
            with open(_bundle_path(), "rb") as handle:
                self._send(200, "text/javascript", handle.read())
        elif path.startswith("/clients/"):
            client_id = path[len("/clients/"):]
            page = ('<!doctype html><html><head><meta charset="utf-8"><title>client</title></head><body>'
                    '<pyc-client-detail client-id="{}"></pyc-client-detail>'
                    '<script type="module" src="/static/javascript/pyc-pods-bundle/index.js"></script>'
                    '</body></html>').format(client_id)
            self._send(200, "text/html; charset=utf-8", page.encode("utf-8"))
        elif path.startswith("/api/v1/clients/") and path.endswith("/capabilities"):
            client_id = path[len("/api/v1/clients/"):-len("/capabilities")]
            _attributes, status, body = by_client[client_id]
            self._send_json(status, body)
        elif path.startswith("/api/v1/clients/"):
            client_id = path[len("/api/v1/clients/"):]
            attributes, _status, _body = by_client[client_id]
            self._send_json(200, _client_record(client_id=client_id, attributes=attributes))
        elif path == "/api/v1/projects":
            self._send_json(200, {"items": [{"project_id": PROJECT_ID, "display_name": "Live loop POC"}]})
        elif path.endswith("/pod-definitions"):
            self._send_json(200, [])
        else:
            self._send_json(404, {"title": "Not Found", "status": 404})
        return


_OBSERVE_JS = """
() => {
    const view = document.querySelector('pyc-client-detail');
    const texts = (selector) => Array.from(view.querySelectorAll(selector)).map((e) => e.textContent.trim());
    return {
        error_state: view.querySelector('[data-role="error-state"]') !== null,
        summary_shown: view.querySelector('[data-role="client-id"]') !== null,
        empty_shown: view.querySelector('[data-role="capabilities-empty"]') !== null,
        advertised_tags: texts('[data-role="advertised-capabilities"] .pyc-client-detail__tag'),
        section_tags: texts('[data-role="capabilities-section"] .pyc-client-detail__tag'),
    };
}
"""


#: Upper bound for rendering every scenario (browser launch included).
RENDER_TIMEOUT_SECONDS: float = 120.0


def _render_scenarios(*, base_url: str) -> Dict[str, Any]:
    """
        Open the client detail page of every scenario in headless
        Chromium and record what the view rendered.

        :param base_url: Origin of the stub site.

        :returns: ``{scenario: observations}``.
    """
    rtnval: Dict[str, Any] = {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            for scenario, (client_id, _attributes, _status, _body) in SCENARIOS.items():
                page = browser.new_page()
                page.goto(base_url + "/clients/" + client_id)
                page.wait_for_selector(
                    '[data-role="capabilities-section"], [data-role="error-state"]', timeout=20000)
                rtnval[scenario] = page.evaluate(_OBSERVE_JS)
                page.close()
        finally:
            browser.close()
    return rtnval


@testbase.register.resource_factory()
def create_client_detail_observations(constraints: Optional[Dict[str, Any]] = None) -> Generator[Dict[str, Any], None, None]:
    """
        Render the client detail view for every scenario in headless
        Chromium and yield what each page showed.

        The browser runs on a dedicated thread: Playwright's sync API
        refuses to start on a thread where another sync Playwright
        instance is active (the phase-11 session browser is, in a full
        run), and a fresh thread has no event loop of its own yet.

        :yields: ``{scenario: observations}``.
    """
    server = ThreadingHTTPServer(("127.0.0.1", 0), _StubSiteHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    base_url = "http://127.0.0.1:{}".format(server.server_address[1])
    outcome: Dict[str, Any] = {}

    def _render() -> None:
        try:
            outcome["observations"] = _render_scenarios(base_url=base_url)
        except BaseException as xcpt:  # re-raised on the test thread below
            outcome["error"] = xcpt
        return

    try:
        render_thread = threading.Thread(target=_render, name="p26g-playwright", daemon=True)
        render_thread.start()
        render_thread.join(timeout=RENDER_TIMEOUT_SECONDS)
        if "error" in outcome:
            raise outcome["error"]
        if "observations" not in outcome:
            raise TimeoutError("rendering the client detail scenarios took longer than {} s".format(
                RENDER_TIMEOUT_SECONDS))
        yield outcome["observations"]
    finally:
        server.shutdown()
        server.server_close()
    return


testbase.originate.parameter(
    create_client_detail_observations,
    identifier="detail",
    life_span=ResourceLifespan.Package,
)


def test_client_detail_lists_the_capabilities_the_pod_advertised(detail: Dict[str, Any]):
    """
    **Feature: client detail capabilities (E2E-18)**
    **Property: the capabilities a pod advertised are listed as the tags
    dispatch matches on -- kind, rpa:<job type>, and the pod's tags.**
    """
    testbase.assert_equal(detail["advertised"]["advertised_tags"], ["rpa", "rpa:hello-echo", "gpu"])
    return


def test_advertised_capabilities_are_not_reported_as_missing(detail: Dict[str, Any]):
    """
    **Feature: client detail capabilities (E2E-18)**
    **Property: a client whose pod advertised capabilities is not shown
    with "No capabilities reported".**
    """
    testbase.assert_equal(detail["advertised"]["empty_shown"], False)
    return


def test_operator_attributes_are_listed_beside_advertised_capabilities(detail: Dict[str, Any]):
    """
    **Feature: client detail capabilities (E2E-18)**
    **Property: operator-set attributes are still listed, after the
    advertised capabilities.**
    """
    testbase.assert_equal(detail["advertised_and_attributes"]["section_tags"], ["rpa", "location:lab-1"])
    return


def test_client_with_neither_says_none_were_reported(detail: Dict[str, Any]):
    """
    **Feature: client detail capabilities (E2E-18)**
    **Property: with no advertised capabilities and no attributes the
    section says none were reported.**
    """
    testbase.assert_equal(detail["nothing"]["empty_shown"], True)
    return


def test_failed_capabilities_fetch_does_not_block_the_client_view(detail: Dict[str, Any]):
    """
    **Feature: client detail capabilities (E2E-18)**
    **Property: when the capabilities endpoint fails the client is still
    shown, with its attributes, not an error state.**
    """
    observed = detail["capabilities_unavailable"]
    testbase.assert_equal(
        (observed["error_state"], observed["summary_shown"], observed["section_tags"]),
        (False, True, ["location:lab-2"]),
    )
    return
