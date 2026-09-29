"""
.. module:: api.openapi_document
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Serve the authoritative OpenAPI document at
               ``GET /api/v1/_meta/openapi.json``.

.. moduleauthor:: Code Craft AI LLC

``specs/openapi/pychestrate.yaml`` is the single source of truth for
the REST surface, and the ``pyc`` CLI builds its commands from it --
but the service never served it, so every generated command failed
before sending its request (audit finding CLI-01). This module serves
it as JSON to any signed-in caller (session cookie or API token).

The document is read from the source tree the service runs from
(deployments rsync the whole tree), parsed once, and re-read only when
the file changes. Its ``servers`` list, which names the author's own
host, is replaced with ``/api/v1`` on the answering server so clients
resolve paths against the server they asked. A deployment without the
``specs`` tree answers 404, and ``pyc`` falls back to its built-in
commands.

``info.version`` is the version of the REST contract; the served copy
also names the running service's own version as
``info.x-service-version`` (the ``[tool.poetry] version`` of the
checkout's ``pyproject.toml``), which ``pyc version`` reports.

The same document is rendered for people at
``GET /api/v1/_meta/docs`` with ReDoc, from the copy of ReDoc that ships
inside codecraftai-webworks and is served from this origin
(``/api/v1/_meta/docs/assets/redoc.standalone.js``), so the page needs no
third-party host and works under the service's Content-Security-Policy.
Like the document, it needs a signed-in caller, and it lives beside it
because only ``/api/v1/`` resolves the session cookie. ``GET /api/docs``,
the address people try first, redirects to it (audit finding DOC-06).
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import logging
import os
import re
import threading

from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from ccai.pychestrate.webservice.api.problem_json_webworks import (
    problem_response_for_http_status,
)
from ccai.pychestrate.webservice.api.rest_authz import (
    AUTHENTICATED_ONLY,
    require_rest_permission,
)


_module_logger = logging.getLogger(__name__)


OPENAPI_DOCUMENT_PATH: str = "/_meta/openapi.json"

#: The human-readable reference, the script it loads, and the address
#: people try first (a redirect: only /api/v1/ resolves the session).
API_DOCS_PATH: str = "/_meta/docs"
API_DOCS_ASSET_PATH: str = "/_meta/docs/assets/{filename}"
API_DOCS_ASSET_DIRECTORY: str = "/_meta/docs/assets"
API_DOCS_ALIAS_PATH: str = "/api/docs"
API_DOCS_TITLE: str = "Pychestrate REST API"

#: The only files served under the assets path. An allowlist, not a
#: directory read: the asset resolver joins the name onto a directory
#: and would follow a ".." out of it.
API_DOCS_ASSETS: Tuple[str, ...] = ("redoc.standalone.js",)

#: Where the authoritative spec lives, relative to the repository root.
SPEC_RELATIVE_PATH: Tuple[str, ...] = ("specs", "openapi", "pychestrate.yaml")

#: How far up from this module to look for the repository root.
_MAX_PARENT_LEVELS: int = 10

#: The ``info`` member naming the running service's version.
SERVICE_VERSION_EXTENSION: str = "x-service-version"

_POETRY_SECTION_PATTERN = re.compile(r"^\[tool\.poetry\]\s*$")
_SECTION_PATTERN = re.compile(r"^\[.*\]\s*$")
_VERSION_LINE_PATTERN = re.compile(r"""^version\s*=\s*["']([^"']+)["']""")

_CACHE_LOCK = threading.Lock()
_CACHE: Dict[str, Any] = {"path": None, "mtime": None, "document": None}


def locate_spec_file(*, start: Optional[Path] = None) -> Optional[Path]:
    """
        Find ``specs/openapi/pychestrate.yaml`` by walking up from this
        module (or ``start``).

        :param start: Directory to start from (tests).

        :returns: The spec path, or ``None`` when this deployment does
                  not carry the ``specs`` tree.
    """
    current = start if start is not None else Path(__file__).resolve().parent
    for _level in range(_MAX_PARENT_LEVELS):
        candidate = current.joinpath(*SPEC_RELATIVE_PATH)
        if candidate.is_file():
            return candidate
        if current.parent == current:
            break
        current = current.parent
    return None


def _json_default(value: Any) -> Any:
    """
        JSON fallback for YAML scalars JSON cannot express (dates).

        :param value: Value.

        :returns: ISO string or ``str(value)``.
    """
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        return isoformat()
    rtnval = str(value)
    return rtnval


def read_service_version(*, pyproject_path: Path) -> Optional[str]:
    """
        The ``[tool.poetry] version`` of a ``pyproject.toml`` (read
        line by line, so no TOML parser is needed).

        :param pyproject_path: The file.

        :returns: Version text, or ``None`` when absent / unreadable.
    """
    try:
        with open(pyproject_path, "r", encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return None
    in_poetry_section = False
    for line in lines:
        stripped = line.strip()
        if _SECTION_PATTERN.match(stripped) is not None:
            in_poetry_section = _POETRY_SECTION_PATTERN.match(stripped) is not None
            continue
        if in_poetry_section is True:
            match = _VERSION_LINE_PATTERN.match(stripped)
            if match is not None:
                rtnval: Optional[str] = match.group(1)
                return rtnval
    return None


def _parse_spec(*, spec_path: Path) -> Dict[str, Any]:
    """
        Parse the YAML spec into the JSON-safe document to serve.

        :param spec_path: Spec file.

        :returns: Document.
    """
    import yaml  # noqa: E402 -- only the serving path needs PyYAML

    loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
    with open(spec_path, "r", encoding="utf-8") as fh:
        raw = yaml.load(fh, Loader=loader)
    if not isinstance(raw, dict):
        raise ValueError("{} does not hold an OpenAPI document".format(spec_path))
    document = json.loads(json.dumps(raw, default=_json_default))
    document["servers"] = [
        {"url": "/api/v1", "description": "The server that returned this document."}
    ]
    # <repo>/specs/openapi/pychestrate.yaml -> <repo>/pyproject.toml
    service_version = read_service_version(pyproject_path=spec_path.parents[2] / "pyproject.toml")
    if service_version is not None and isinstance(document.get("info", None), dict):
        document["info"][SERVICE_VERSION_EXTENSION] = service_version
    return document


def load_served_document(*, spec_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """
        The document to serve, parsed once and re-parsed when the file
        changes.

        :param spec_path: Spec file (tests); defaults to
                          :func:`locate_spec_file`.

        :returns: Document, or ``None`` when the spec is unavailable.
    """
    resolved_path = spec_path if spec_path is not None else locate_spec_file()
    if resolved_path is None:
        return None
    try:
        mtime = os.stat(resolved_path).st_mtime
    except OSError:
        return None

    with _CACHE_LOCK:
        if _CACHE["path"] == str(resolved_path) and _CACHE["mtime"] == mtime:
            return _CACHE["document"]
        try:
            document = _parse_spec(spec_path=resolved_path)
        except Exception:
            _module_logger.exception(
                "pychestrate.openapi_document.parse_failed path=%s", resolved_path
            )
            return None
        _CACHE["path"] = str(resolved_path)
        _CACHE["mtime"] = mtime
        _CACHE["document"] = document
        rtnval = document
    return rtnval


def reset_cache_for_testing() -> None:
    """
        Forget the parsed document (tests).

        :returns: None.
    """
    with _CACHE_LOCK:
        _CACHE["path"] = None
        _CACHE["mtime"] = None
        _CACHE["document"] = None
    return


def handle_get_openapi_document(request: Any) -> Any:
    """
        ``GET /api/v1/_meta/openapi.json`` -- the REST contract as JSON.

        :param request: Incoming webworks request.

        :returns: 200 JSON document, or a 404 problem document when the
                  deployment does not carry the spec.
    """
    from ccai.webworks.routing.response import JSONResponse  # noqa: E402

    document = load_served_document()
    if document is None:
        rtnval = problem_response_for_http_status(
            status=404,
            detail="This deployment does not carry the OpenAPI document.",
            instance=getattr(request, "path", None),
        )
        return rtnval
    response = JSONResponse(content=document, status_code=200)
    response.set_header("Cache-Control", "private, max-age=300")
    rtnval = response
    return rtnval


#: The page's own policy. The service's default policy blocks a
#: blob: worker, which ReDoc uses for its search box, so search found
#: nothing. Everything else stays as strict as the default: same-origin
#: scripts only, and no third-party host. (ReDoc's footer badge asks a
#: third-party CDN for a logo; the policy refuses it and the badge shows
#: its text, with one console message.)
API_DOCS_CONTENT_SECURITY_POLICY: str = "; ".join([
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self' data:",
    "connect-src 'self'",
    "worker-src 'self' blob:",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
])

def _docs_page_html(*, version_prefix: str) -> str:
    """
        The ReDoc page for a version prefix.

        :param version_prefix: Versioned API prefix (``"/api/v1"``).

        :returns: HTML.
    """
    from ccai.webworks.openapi.redoc import REDOC_HTML_TEMPLATE  # noqa: E402

    rtnval = REDOC_HTML_TEMPLATE.format(
        title=API_DOCS_TITLE,
        spec_url=version_prefix + OPENAPI_DOCUMENT_PATH,
        static_path=version_prefix + API_DOCS_ASSET_DIRECTORY,
        extra_config="",
    )
    return rtnval


def make_api_docs_handler(*, version_prefix: str) -> Any:
    """
        Build the ``GET <prefix>/_meta/docs`` handler.

        :param version_prefix: Versioned API prefix (``"/api/v1"``).

        :returns: A handler answering the ReDoc page.
    """
    def handle_get_api_docs(request: Any) -> Any:
        from ccai.webworks.routing.response import HTMLResponse  # noqa: E402

        rtnval = HTMLResponse(_docs_page_html(version_prefix=version_prefix))
        rtnval.set_header("Content-Security-Policy", API_DOCS_CONTENT_SECURITY_POLICY)
        return rtnval

    return handle_get_api_docs


def handle_get_api_docs_alias(request: Any) -> Any:
    """
        ``GET /api/docs`` -- redirect to the reference page. Answered
        without a session: the page it leads to asks for one.

        :param request: Incoming webworks request.

        :returns: A redirect.
    """
    from ccai.webworks.routing.response import RedirectResponse  # noqa: E402

    rtnval = RedirectResponse(url="/api/v1" + API_DOCS_PATH)
    return rtnval


def handle_get_api_docs_asset(request: Any) -> Any:
    """
        ``GET /api/docs/assets/{filename}`` -- the bundled ReDoc script.

        :param request: Incoming webworks request.

        :returns: 200 with the file, or a 404 problem document for any
                  name that is not on the allowlist.
    """
    from ccai.webworks.openapi.assets import AssetResolver  # noqa: E402
    from ccai.webworks.routing.response import Response  # noqa: E402

    filename = str(request.path_params.get("filename", ""))
    content: Optional[bytes] = None
    if filename in API_DOCS_ASSETS:
        content = AssetResolver().resolve("redoc", filename)
    if content is None:
        rtnval = problem_response_for_http_status(
            status=404,
            detail="No such documentation asset.",
            instance=getattr(request, "path", None),
        )
        return rtnval
    resolver = AssetResolver()
    rtnval = Response(
        status_code=200,
        headers={
            "Content-Type": resolver.content_type(filename),
            "Cache-Control": "private, max-age=86400",
        },
        body=content,
    )
    return rtnval


def register_api_docs_routes(*, app: Any, version_prefix: str) -> None:
    """
        Attach ``GET <prefix>/_meta/docs`` and
        ``GET <prefix>/_meta/docs/assets/{filename}`` (any signed-in
        principal), and ``GET /api/docs``, which redirects to the page.

        :param app: WebWorks application.
        :param version_prefix: Versioned API prefix (``"/api/v1"``).

        :returns: None.
    """
    app.attach_route(version_prefix + API_DOCS_PATH, methods=["GET"])(
        require_rest_permission(
            make_api_docs_handler(version_prefix=version_prefix), permission_key=AUTHENTICATED_ONLY,
        )
    )
    app.attach_route(version_prefix + API_DOCS_ASSET_PATH, methods=["GET"])(
        require_rest_permission(handle_get_api_docs_asset, permission_key=AUTHENTICATED_ONLY)
    )
    app.attach_route(API_DOCS_ALIAS_PATH, methods=["GET"])(handle_get_api_docs_alias)
    return


def register_openapi_document_routes(*, app: Any, version_prefix: str) -> None:
    """
        Attach ``GET <version_prefix>/_meta/openapi.json`` (any
        signed-in principal).

        :param app: WebWorks application.
        :param version_prefix: Versioned API prefix (``"/api/v1"``).

        :returns: None.
    """
    app.attach_route(version_prefix + OPENAPI_DOCUMENT_PATH, methods=["GET"])(
        require_rest_permission(handle_get_openapi_document, permission_key=AUTHENTICATED_ONLY)
    )
    return


__all__ = [
    "API_DOCS_ALIAS_PATH",
    "API_DOCS_ASSETS",
    "API_DOCS_CONTENT_SECURITY_POLICY",
    "API_DOCS_PATH",
    "OPENAPI_DOCUMENT_PATH",
    "SERVICE_VERSION_EXTENSION",
    "SPEC_RELATIVE_PATH",
    "handle_get_api_docs_alias",
    "handle_get_api_docs_asset",
    "make_api_docs_handler",
    "handle_get_openapi_document",
    "load_served_document",
    "locate_spec_file",
    "read_service_version",
    "register_api_docs_routes",
    "register_openapi_document_routes",
    "reset_cache_for_testing",
]
