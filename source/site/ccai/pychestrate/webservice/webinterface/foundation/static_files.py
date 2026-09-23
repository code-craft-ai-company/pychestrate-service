"""
.. module:: webinterface.foundation.static_files
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Static file serving for the webworks-side
               consumer web UI.

.. moduleauthor:: Code Craft AI LLC

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

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import logging
import mimetypes
import hashlib
import os

from typing import Dict, Tuple, Any, Optional

from ccai.webworks.routing.request import Request
from ccai.webworks.routing.response import Response


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

    # Caching: a versioned URL (``?v=<content hash>``, built by
    # :func:`build_static_url`) is immutable for a year; a bare URL
    # must revalidate on every use. Either way an ETag lets the
    # browser skip the body when nothing changed.
    etag = '"{}"'.format(hashlib.sha256(body_bytes).hexdigest()[:32])
    if _request_has_version_param(request=request) is True:
        cache_control = "public, max-age=31536000, immutable"
    else:
        cache_control = "no-cache"
    headers = {
        "Content-Type": content_type,
        "Cache-Control": cache_control,
        "ETag": etag,
    }
    if _if_none_match_matches(request=request, etag=etag) is True:
        rtnval = Response(status_code=304, body=b"", headers=headers)
        return rtnval
    rtnval = Response(
        status_code=200,
        body=body_bytes,
        headers=headers,
    )
    return rtnval


def _request_has_version_param(*, request: Request) -> bool:
    try:
        value = request.query_params.get("v", None)
    except Exception:
        value = None
    rtnval = value is not None and len(str(value)) > 0
    return rtnval


def _if_none_match_matches(*, request: Request, etag: str) -> bool:
    try:
        header = request.headers.get("If-None-Match", None)
    except Exception:
        header = None
    if header is None:
        return False
    candidates = [part.strip() for part in str(header).split(",")]
    rtnval = etag in candidates or "*" in candidates
    return rtnval


_STATIC_URL_CACHE: Dict[str, Tuple[float, int, str]] = {}
_static_url_root: Optional[str] = None


def configure_static_url_root(*, static_root: str) -> None:
    """
        Tell :func:`build_static_url` where the static tree lives so
        it can hash file contents. Called once at bootstrap alongside
        :func:`register_static_routes`.

        :param static_root: Absolute path to the static directory.

        :returns: None.
    """
    global _static_url_root
    _static_url_root = static_root
    _STATIC_URL_CACHE.clear()
    return


def build_static_url(relative_path: str) -> str:
    """
        Build a cache-busting URL for a static asset:
        ``/static/<relative_path>?v=<content hash>``. The hash is
        recomputed only when the file's mtime or size changes, so
        the per-render cost is one ``stat``. A file that cannot be
        found is returned un-versioned so the page still links it.

        Installed on the jinja environment as the ``static_url``
        global.

        :param relative_path: Path under the static root, e.g.
                              ``"styles/pyc-tokens.css"``.

        :returns: URL string.
    """
    clean = str(relative_path).lstrip("/")
    base_url = "/static/" + clean
    root = _static_url_root
    if root is None:
        try:
            from ccai.pychestrate.webservice.metadata import SITE_DIRECTORIES  # noqa: E402
            root = SITE_DIRECTORIES.DIR_STATIC
        except Exception:
            return base_url
    full_path = os.path.join(root, clean)
    try:
        stat_result = os.stat(full_path)
    except OSError:
        return base_url
    cached = _STATIC_URL_CACHE.get(clean, None)
    if cached is not None and cached[0] == stat_result.st_mtime and cached[1] == stat_result.st_size:
        digest = cached[2]
    else:
        hasher = hashlib.sha1()
        with open(full_path, "rb") as fh:
            hasher.update(fh.read())
        digest = hasher.hexdigest()[:12]
        _STATIC_URL_CACHE[clean] = (stat_result.st_mtime, stat_result.st_size, digest)
    rtnval = "{}?v={}".format(base_url, digest)
    return rtnval


def install_static_url_global(*, environment: Any) -> None:
    """
        Attach :func:`build_static_url` to a jinja environment as the
        ``static_url`` global, and :func:`build_mj_static_url` as the
        ``mj_static_url`` global.

        :param environment: :class:`jinja2.Environment`.

        :returns: None.
    """
    environment.globals["static_url"] = build_static_url
    environment.globals["mj_static_url"] = build_mj_static_url
    return


# ---------------------------------------------------------------------------
# Versioned URLs for the component-library assets mounted at /mj
# ---------------------------------------------------------------------------

MJ_STATIC_URL_PREFIX: str = "/mj/"

_MJ_STATIC_URL_CACHE: Dict[str, Tuple[float, int, str]] = {}
_mj_static_url_root: Optional[str] = None


def configure_mj_static_url_root(*, static_root: Optional[str]) -> None:
    """
        Point :func:`build_mj_static_url` at the directory served under
        ``/mj``. Optional: by default the builder resolves the
        installed ``codecraftai-webworks`` package's ``static/``
        directory, the same directory the bootstrap mounts at ``/mj``.
        Passing ``None`` restores that default.

        :param static_root: Absolute path to the directory, or ``None``.

        :returns: None.
    """
    global _mj_static_url_root
    _mj_static_url_root = static_root
    _MJ_STATIC_URL_CACHE.clear()
    return


def _resolve_mj_static_url_root() -> Optional[str]:
    """
        The directory served under ``/mj``: the configured root, else
        the installed webworks package's ``static/`` directory.

        :returns: Absolute path, or ``None`` when it cannot be found.
    """
    if _mj_static_url_root is not None:
        return _mj_static_url_root
    try:
        import ccai.webworks as webworks_package  # noqa: E402
    except Exception:
        return None
    rtnval = os.path.join(os.path.dirname(webworks_package.__file__), "static")
    return rtnval


def build_mj_static_url(relative_path: str) -> str:
    """
        Build a cache-busting URL for a component-library asset served
        under ``/mj`` (``/mj/styles/tokens.css?v=<content hash>``), the
        ``/mj`` counterpart of :func:`build_static_url`. Versioned URLs
        are served ``immutable`` by :func:`serve_static_file`, so the
        shell stops revalidating the library stylesheets on every page.
        A file that cannot be found is returned un-versioned so the
        page still links it.

        Installed on the jinja environment as the ``mj_static_url``
        global.

        :param relative_path: Path under the ``/mj`` root, e.g.
                              ``"styles/tokens.css"``.

        :returns: URL string.
    """
    clean = str(relative_path).lstrip("/")
    base_url = MJ_STATIC_URL_PREFIX + clean
    root = _resolve_mj_static_url_root()
    if root is None:
        return base_url
    full_path = os.path.join(root, clean)
    try:
        stat_result = os.stat(full_path)
    except OSError:
        return base_url
    cached = _MJ_STATIC_URL_CACHE.get(clean, None)
    if cached is not None and cached[0] == stat_result.st_mtime and cached[1] == stat_result.st_size:
        digest = cached[2]
    else:
        hasher = hashlib.sha1()
        with open(full_path, "rb") as fh:
            hasher.update(fh.read())
        digest = hasher.hexdigest()[:12]
        _MJ_STATIC_URL_CACHE[clean] = (stat_result.st_mtime, stat_result.st_size, digest)
    rtnval = "{}?v={}".format(base_url, digest)
    return rtnval


def register_favicon_route(*, app: Any, favicon_path: str) -> None:
    """
        Serve ``/favicon.ico`` from the SVG favicon so browsers stop
        receiving a redirect to the login page for it.

        :param app: WebWorks application.
        :param favicon_path: Absolute path to ``favicon.svg``.

        :returns: None.
    """
    def favicon_handler(request: Request) -> Response:
        try:
            with open(favicon_path, "rb") as fh:
                body = fh.read()
        except OSError:
            rtnval = _not_found_response()
            return rtnval
        rtnval = Response(
            status_code=200,
            body=body,
            headers={
                "Content-Type": "image/svg+xml",
                "Cache-Control": "public, max-age=86400",
            },
        )
        return rtnval

    app.attach_route("/favicon.ico", methods=["GET"])(favicon_handler)
    return
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
    "build_mj_static_url",
    "build_static_url",
    "configure_mj_static_url_root",
    "configure_static_url_root",
    "MJ_STATIC_URL_PREFIX",
    "install_static_url_global",
    "register_favicon_route",
    "DEFAULT_CONTENT_TYPE",
    "serve_static_file",
    "register_static_routes",
]
