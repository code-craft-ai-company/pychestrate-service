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

Compression
-----------

Text assets (JavaScript, CSS, SVG, JSON, plain text) of at least
:data:`MIN_COMPRESSIBLE_BYTES` are sent ``Content-Encoding: gzip``
when the request's ``Accept-Encoding`` allows it, so a deployment
without a compressing reverse proxy does not ship the 1.6 MB
component library uncompressed on every page. The gzip body and
the file bytes are cached in process per file (keyed by path,
mtime and size), so an asset is read, hashed and compressed once
per release rather than on every request. Each representation
carries its own ETag and every text asset answers
``Vary: Accept-Encoding`` so shared caches keep them apart.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import gzip
import logging
import mimetypes
import hashlib
import os
import threading

from dataclasses import dataclass
from typing import Dict, Tuple, Any, Optional

from ccai.webworks.routing.request import Request
from ccai.webworks.routing.response import Response


_module_logger = logging.getLogger(__name__)


DEFAULT_CONTENT_TYPE: str = "application/octet-stream"

#: Content types worth gzip-encoding. Images other than SVG and web
#: fonts are already compressed, so they are always sent as-is.
COMPRESSIBLE_CONTENT_TYPES = frozenset((
    "application/javascript",
    "application/json",
    "application/manifest+json",
    "application/xml",
    "image/svg+xml",
    "text/css",
    "text/html",
    "text/javascript",
    "text/plain",
    "text/xml",
))

#: Files smaller than this are sent uncompressed: below ~1 KiB the
#: gzip framing overhead eats most of the saving.
MIN_COMPRESSIBLE_BYTES: int = 1024

#: zlib level used for static assets. Level 6 is the usual
#: size / CPU balance; the result is cached, so it is paid once per
#: file per release.
GZIP_COMPRESSION_LEVEL: int = 6

#: Files larger than this are not held in the in-process cache; they
#: are read (and compressed) per request instead.
MAX_CACHED_ASSET_BYTES: int = 16 * 1024 * 1024

#: Suffix appended inside the quotes of the ETag of the gzip
#: representation, so the two representations never share a
#: validator.
GZIP_ETAG_SUFFIX: str = "-gzip"


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

    asset = _load_static_asset(file_path=resolved_candidate)

    # Caching: a versioned URL (``?v=<content hash>``, built by
    # :func:`build_static_url`) is immutable for a year; a bare URL
    # must revalidate on every use. Either way an ETag lets the
    # browser skip the body when nothing changed.
    if _request_has_version_param(request=request) is True:
        cache_control = "public, max-age=31536000, immutable"
    else:
        cache_control = "no-cache"

    send_gzip = False
    if asset.compressible is True:
        send_gzip = _request_accepts_gzip(request=request)

    if send_gzip is True:
        body_bytes = _gzip_body_for(asset=asset)
        etag = asset.gzip_etag
    else:
        body_bytes = asset.body
        etag = asset.etag

    headers = {
        "Content-Type": asset.content_type,
        "Cache-Control": cache_control,
        "ETag": etag,
    }
    if asset.compressible is True:
        headers["Vary"] = "Accept-Encoding"
    if send_gzip is True:
        headers["Content-Encoding"] = "gzip"

    if _if_none_match_matches(request=request, etag=etag) is True:
        headers.pop("Content-Encoding", None)
        rtnval = Response(status_code=304, body=b"", headers=headers)
        return rtnval
    rtnval = Response(
        status_code=200,
        body=body_bytes,
        headers=headers,
    )
    return rtnval


@dataclass
class _StaticAsset:
    """
        One static file as served: its bytes, content type, strong
        ETag, and (filled in lazily) its gzip representation.

        :ivar mtime_ns: File modification time the entry was built
                        from; a change invalidates the entry.
        :ivar size: File size the entry was built from.
        :ivar body: Identity (uncompressed) bytes.
        :ivar content_type: Guessed ``Content-Type``.
        :ivar etag: Quoted strong ETag of the identity bytes.
        :ivar compressible: Whether the asset is worth gzip-encoding.
        :ivar gzip_etag: Quoted ETag of the gzip representation.
        :ivar gzip_body: Cached gzip bytes, or ``None`` until the
                         first gzip request.
    """
    mtime_ns: int
    size: int
    body: bytes
    content_type: str
    etag: str
    compressible: bool
    gzip_etag: str
    gzip_body: Optional[bytes] = None


_STATIC_ASSET_CACHE: Dict[str, _StaticAsset] = {}
_STATIC_ASSET_CACHE_LOCK = threading.Lock()


def _is_compressible(*, content_type: str, size: int) -> bool:
    """
        Decide whether an asset is worth gzip-encoding.

        :param content_type: Guessed content type (no parameters).
        :param size: Size of the identity body in bytes.

        :returns: True for text types of at least
                  :data:`MIN_COMPRESSIBLE_BYTES`.
    """
    if size < MIN_COMPRESSIBLE_BYTES:
        return False
    rtnval = content_type in COMPRESSIBLE_CONTENT_TYPES
    return rtnval


def _load_static_asset(*, file_path: str) -> _StaticAsset:
    """
        Return the cached :class:`_StaticAsset` for ``file_path``,
        (re)building it when the file's mtime or size changed.

        :param file_path: Resolved absolute path inside the static
                          root.

        :returns: The asset entry.
    """
    stat_result = os.stat(file_path)
    with _STATIC_ASSET_CACHE_LOCK:
        cached = _STATIC_ASSET_CACHE.get(file_path, None)
    if cached is not None:
        if cached.mtime_ns == stat_result.st_mtime_ns and cached.size == stat_result.st_size:
            return cached

    with open(file_path, "rb") as fh:
        body_bytes = fh.read()
    content_type, _ = mimetypes.guess_type(file_path)
    if content_type is None:
        content_type = DEFAULT_CONTENT_TYPE
    digest = hashlib.sha256(body_bytes).hexdigest()[:32]
    asset = _StaticAsset(
        mtime_ns=stat_result.st_mtime_ns,
        size=stat_result.st_size,
        body=body_bytes,
        content_type=content_type,
        etag='"{}"'.format(digest),
        compressible=_is_compressible(content_type=content_type, size=len(body_bytes)),
        gzip_etag='"{}{}"'.format(digest, GZIP_ETAG_SUFFIX),
    )
    if len(body_bytes) <= MAX_CACHED_ASSET_BYTES:
        with _STATIC_ASSET_CACHE_LOCK:
            _STATIC_ASSET_CACHE[file_path] = asset
    rtnval = asset
    return rtnval


def _gzip_body_for(*, asset: _StaticAsset) -> bytes:
    """
        Return the gzip representation of an asset, compressing it
        on first use. ``mtime=0`` keeps the output byte-stable so the
        representation matches its ETag across processes.

        :param asset: Cached asset entry.

        :returns: gzip-encoded bytes.
    """
    if asset.gzip_body is not None:
        return asset.gzip_body
    compressed = gzip.compress(
        asset.body, compresslevel=GZIP_COMPRESSION_LEVEL, mtime=0,
    )
    asset.gzip_body = compressed
    rtnval = compressed
    return rtnval


def _request_accepts_gzip(*, request: Request) -> bool:
    """
        Parse ``Accept-Encoding`` and decide whether a gzip body is
        acceptable (``gzip`` or ``*`` listed with a non-zero q-value,
        and ``gzip`` not explicitly refused).

        :param request: Incoming webworks request.

        :returns: True when the response may be gzip-encoded.
    """
    try:
        header = request.headers.get("Accept-Encoding", None)
    except Exception:
        header = None
    if header is None:
        return False

    gzip_quality: Optional[float] = None
    wildcard_quality: Optional[float] = None
    for part in str(header).split(","):
        pieces = [piece.strip() for piece in part.split(";")]
        coding = pieces[0].lower()
        if len(coding) == 0:
            continue
        quality = 1.0
        for param in pieces[1:]:
            if param.lower().startswith("q="):
                try:
                    quality = float(param[2:])
                except ValueError:
                    quality = 0.0
        if coding in ("gzip", "x-gzip"):
            gzip_quality = quality
        elif coding == "*":
            wildcard_quality = quality

    if gzip_quality is not None:
        rtnval = gzip_quality > 0.0
        return rtnval
    rtnval = wildcard_quality is not None and wildcard_quality > 0.0
    return rtnval


def reset_static_asset_cache_for_testing() -> None:
    """
        Drop every cached static asset. Tests call this when they
        rewrite a file in place faster than the mtime resolution.

        :returns: None.
    """
    with _STATIC_ASSET_CACHE_LOCK:
        _STATIC_ASSET_CACHE.clear()
    return


def _request_has_version_param(*, request: Request) -> bool:
    try:
        value = request.query_params.get("v", None)
    except Exception:
        value = None
    rtnval = value is not None and len(str(value)) > 0
    return rtnval


def _if_none_match_matches(*, request: Request, etag: str) -> bool:
    """
        Evaluate ``If-None-Match`` against ``etag`` with the weak
        comparison RFC 9110 prescribes for this header: a ``W/``
        prefix on either side is ignored, so a validator a proxy
        weakened still revalidates.

        :param request: Incoming webworks request.
        :param etag: Quoted ETag of the representation being served.

        :returns: True when the client's copy is current.
    """
    try:
        header = request.headers.get("If-None-Match", None)
    except Exception:
        header = None
    if header is None:
        return False
    target = _opaque_etag(etag)
    candidates = [part.strip() for part in str(header).split(",")]
    for candidate in candidates:
        if candidate == "*":
            return True
        if _opaque_etag(candidate) == target:
            return True
    rtnval = False
    return rtnval


def _opaque_etag(value: str) -> str:
    """
        Strip the weakness indicator from an entity tag.

        :param value: Entity tag, possibly ``W/``-prefixed.

        :returns: The quoted opaque tag.
    """
    stripped = value.strip()
    if stripped.startswith("W/"):
        stripped = stripped[2:]
    rtnval = stripped
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
    "COMPRESSIBLE_CONTENT_TYPES",
    "DEFAULT_CONTENT_TYPE",
    "GZIP_ETAG_SUFFIX",
    "MIN_COMPRESSIBLE_BYTES",
    "reset_static_asset_cache_for_testing",
    "serve_static_file",
    "register_static_routes",
]
