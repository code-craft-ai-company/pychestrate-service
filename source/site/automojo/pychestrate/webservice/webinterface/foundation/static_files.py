"""
.. module:: webinterface.foundation.static_files
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Static file serving for the webworks-side
               consumer web UI.

.. moduleauthor:: Automation Mojo LLC

WebWorks does not ship a static file handler. This module
provides one for the consumer web UI:

* :func:`serve_static_file` -- handler that resolves a request
  path inside a configured root directory, performs path
  traversal protection, and returns a webworks
  :class:`Response` with the right ``Content-Type``.

* :func:`register_static_routes` -- wires the handler under the
  configured URL prefix using a webworks ``{filepath:path}``
  parameterized route. Operators / blueprint ports call this
  during ``register_service_extensions()``.

Path-traversal protection
-------------------------

The handler uses :func:`os.path.realpath` resolution and
verifies the resolved path stays inside the configured root.
Requests for ``../../../etc/passwd`` resolve outside the root
and return 404. Symlinks that point outside the root are
similarly refused.

Content-Type detection
----------------------

The :mod:`mimetypes` stdlib module guesses the type from the
file extension. Unknown extensions fall back to
``application/octet-stream`` -- safe default that browsers do
not render.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import logging
import mimetypes
import os

from typing import Any, Optional

from automojo.webworks.routing.request import Request
from automojo.webworks.routing.response import Response


_module_logger = logging.getLogger(__name__)


DEFAULT_CONTENT_TYPE: str = "application/octet-stream"


def serve_static_file(
        *,
        request: Request,
        static_root: str
    ) -> Response:
    """
        Resolve the request's ``filepath`` path parameter inside
        ``static_root``, return the file bytes with a guessed
        ``Content-Type``. Refuses requests that traverse outside
        the root.

        :param request: Incoming webworks request. The handler
                        reads ``request.path_params["filepath"]``.
        :param static_root: Absolute path to the directory the
                            handler serves from.

        :returns: :class:`Response` carrying the file bytes (200)
                  or an empty 404 response on miss / traversal.
    """
    filepath = request.path_params.get("filepath", "")
    if filepath is None or len(filepath) == 0:
        return _not_found_response()

    # Resolve the requested path under the root, then verify the
    # resolved real path stays inside the root. Using realpath on
    # both sides handles symlinks safely.
    candidate = os.path.join(static_root, filepath)
    resolved_root = os.path.realpath(static_root)
    resolved_candidate = os.path.realpath(candidate)

    if not resolved_candidate.startswith(resolved_root + os.sep):
        # The resolved path escaped the root -- traversal attempt.
        # Log at warning level so operators can spot scanning.
        _module_logger.warning(
            "pychestrate.static.traversal_refused requested=%s",
            filepath,
        )
        return _not_found_response()

    if os.path.isfile(resolved_candidate) is False:
        return _not_found_response()

    with open(resolved_candidate, "rb") as fh:
        body_bytes = fh.read()

    content_type, _ = mimetypes.guess_type(resolved_candidate)
    if content_type is None:
        content_type = DEFAULT_CONTENT_TYPE

    rtnval = Response(
        status_code=200,
        body=body_bytes,
        headers={"Content-Type": content_type},
    )
    return rtnval


def _not_found_response() -> Response:
    """
        Build the standard 404 response the static handler emits
        on miss / traversal. Pulled out so the shape is uniform.

        :returns: :class:`Response` (404, empty body).
    """
    rtnval = Response(status_code=404, body=b"")
    return rtnval


def register_static_routes(
        *,
        app: Any,
        url_prefix: str,
        static_root: str
    ) -> None:
    """
        Attach the static-file handler to a webworks application.
        After registration, requests under
        ``{url_prefix}/{filepath:path}`` resolve under
        ``static_root``.

        :param app: WebWorks application built by
                    ``establish_webapp_persona``.
        :param url_prefix: URL prefix under which the static files
                           live (e.g. ``"/static"`` so
                           ``/static/styles/main.css`` serves
                           ``static_root/styles/main.css``).
        :param static_root: Absolute path to the directory served.

        :returns: None.
        :raises: ValueError on missing / non-existent static_root.
    """
    if static_root is None or len(static_root) == 0:
        raise ValueError(
            "register_static_routes requires a non-empty static_root"
        )
    if os.path.isdir(static_root) is False:
        raise ValueError(
            "static_root does not exist or is not a directory: {}".format(
                static_root
            )
        )
    if url_prefix is None or len(url_prefix) == 0:
        raise ValueError(
            "register_static_routes requires a non-empty url_prefix"
        )

    # Closure captures static_root so the handler signature stays
    # the standard (request) -> Response webworks shape.
    def static_handler(request: Request) -> Response:
        rtnval = serve_static_file(
            request=request, static_root=static_root
        )
        return rtnval

    full_pattern = url_prefix + "/{filepath:path}"
    app.attach_route(full_pattern, methods=["GET"])(static_handler)
    return


__all__ = [
    "DEFAULT_CONTENT_TYPE",
    "serve_static_file",
    "register_static_routes",
]
