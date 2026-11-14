"""
.. module:: test_p40r_wsgi_request_body_limit_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The service's WSGI application accepts request bodies up to the largest upload a route takes.

.. moduleauthor:: Code Craft AI LLC

webworks 1.7 refuses a WSGI request body larger than 16 MiB unless the application sets ``max_request_body_size`` (1.6 had no
limit). Run artifacts are uploaded up to ``MAX_LOCAL_UPLOAD_BYTES`` (256 MiB) and JUnit reports up to 64 MiB, so the WSGI
application the service builds (``create_dispatch_wsgi_application``) sets that limit; without it an artifact between 16 and
256 MiB was answered 413 by webworks before the upload route ran.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import io

from typing import Any, Dict, List

from ccai import testbase

from ccai.webworks.routing.response import Response

from ccai.pychestrate.webservice.runs.restapi.v1.artifacts_routes import MAX_LOCAL_UPLOAD_BYTES
from ccai.pychestrate.webservice.wsgi_dispatch import create_dispatch_wsgi_application


class _RecordingDispatcher:
    """
        Stands in for the webworks dispatcher: records the size of each request body it is handed and answers 200.
    """

    def __init__(self):
        self.body_sizes: List[int] = []
        return

    def dispatch(self, request: Any) -> Response:
        self.body_sizes.append(len(request.body))
        rtnval = Response(status_code=200, headers={"Content-Type": "text/plain"}, body=b"ok")
        return rtnval


class _App:
    """
        The part of the webworks application the dispatch WSGI application uses.
    """

    def __init__(self):
        self.dispatcher = _RecordingDispatcher()
        return


def _post(wsgi_app: Any, body: bytes) -> str:
    """
        Send a POST with ``body`` through a WSGI application and return the status line.
    """
    environ: Dict[str, Any] = {
        "REQUEST_METHOD": "POST",
        "PATH_INFO": "/api/v1/runs/run-1/artifacts/local",
        "QUERY_STRING": "",
        "SERVER_NAME": "pyc.example.test",
        "SERVER_PORT": "443",
        "SERVER_PROTOCOL": "HTTP/1.1",
        "CONTENT_TYPE": "application/octet-stream",
        "CONTENT_LENGTH": str(len(body)),
        "wsgi.input": io.BytesIO(body),
        "wsgi.url_scheme": "https",
        "wsgi.errors": io.StringIO(),
        "wsgi.version": (1, 0),
        "wsgi.multithread": True,
        "wsgi.multiprocess": False,
        "wsgi.run_once": False,
    }
    statuses: List[str] = []

    def start_response(status: str, headers: List[Any], exc_info: Any = None) -> Any:
        statuses.append(status)
        return lambda data: None

    chunks = wsgi_app(environ, start_response)
    b"".join(chunks)
    if hasattr(chunks, "close"):
        chunks.close()

    rtnval = statuses[0]
    return rtnval


def test_a_body_larger_than_16_mib_reaches_the_dispatcher():
    """
        Feature: the service's WSGI application.
        Property: a 17 MiB request body (over webworks' 16 MiB default) is handed to the dispatcher, not refused with 413.
    """
    app = _App()
    wsgi_app = create_dispatch_wsgi_application(app=app)

    status = _post(wsgi_app, b"\0" * (17 * 1024 * 1024))

    testbase.assert_equal(status.split(" ", 1)[0], "200", "a 17 MiB body is answered by the dispatcher")
    testbase.assert_equal(app.dispatcher.body_sizes, [17 * 1024 * 1024], "the dispatcher received the whole body")
    return


def test_the_body_limit_is_the_artifact_upload_limit():
    """
        Feature: the service's WSGI application.
        Property: the largest body the WSGI application accepts is MAX_LOCAL_UPLOAD_BYTES, the largest body a route takes.
    """
    wsgi_app = create_dispatch_wsgi_application(app=_App())

    testbase.assert_equal(wsgi_app.max_request_body_size, MAX_LOCAL_UPLOAD_BYTES, "the WSGI body limit")
    return
