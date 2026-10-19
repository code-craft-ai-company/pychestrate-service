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

The same document is shown to people at ``GET /api/v1/_meta/docs`` with Swagger UI, from the copy that ships inside codecraftai-webworks and is
served from this origin (``/api/v1/_meta/docs/assets/``), so the page needs no third-party host and works under the service's Content-Security-Policy
(which allows scripts from this origin only, so the starter script is a file of its own). It opens folded, grouped by where each operation's path puts it
(``projects / rpa``): the page reads ``GET /api/v1/_meta/openapi.json?group_by=path``, a copy of the document whose operations are tagged by path (the plain
document, which ``pyc`` builds its commands from, keeps the feature tags). **Try it out** sends the request to this service as the person signed in, so the page
adds no access the API does not already give; ``PYCHESTRATE_API_DOCS_TRY_IT_OUT`` (``all``, ``get`` or ``off``) limits what it may send. Like the document, the
page needs a signed-in caller, and it lives beside it because only ``/api/v1/`` resolves the session cookie. ``GET /api/docs``, the address people try first,
redirects to it (audit finding DOC-06). It replaced a read-only ReDoc page: a read-only reference protected nothing, since the page is behind the same sign-in.
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

#: The human-readable explorer, the files it loads, and the address
#: people try first (a redirect: only /api/v1/ resolves the session).
API_DOCS_PATH: str = "/_meta/docs"
API_DOCS_ASSET_PATH: str = "/_meta/docs/assets/{filename}"
API_DOCS_ASSET_DIRECTORY: str = "/_meta/docs/assets"
API_DOCS_ALIAS_PATH: str = "/api/docs"
API_DOCS_TITLE: str = "Pychestrate REST API"

#: The ``group_by`` value that asks the document endpoint for the copy tagged by path, and the one the explorer page asks for.
GROUP_BY_PATH: str = "path"

#: How many fixed words of a path name its group in the explorer (``projects / rpa``).
GROUP_DEPTH: int = 2

#: The operator setting that limits what **Try it out** may send: ``all`` (every method, the default), ``get`` (reads only, for a production system) or
#: ``off`` (no Try it out). Anything else is read as ``get``, the safe choice, and logged.
TRY_IT_OUT_ENV_VAR: str = "PYCHESTRATE_API_DOCS_TRY_IT_OUT"

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

#: The path-grouped copy of the served document, made once per parsed document.
_GROUPED: Dict[str, Any] = {"source": None, "grouped": None}


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
        _GROUPED["source"] = None
        _GROUPED["grouped"] = None
    return


def load_grouped_document(*, spec_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """
        The served document with its operations tagged by path (``projects / rpa``), for the explorer page. Made once per parsed document.

        :param spec_path: Override the spec location (tests).

        :returns: The grouped copy, or ``None`` when the deployment does not carry the spec.
    """
    from ccai.webworks.openapi.grouping import group_operations_by_path  # noqa: E402

    document = load_served_document(spec_path=spec_path)
    if document is None:
        return None
    with _CACHE_LOCK:
        if _GROUPED["source"] is not document:
            _GROUPED["grouped"] = group_operations_by_path(document, depth=GROUP_DEPTH)
            _GROUPED["source"] = document
        rtnval = _GROUPED["grouped"]
    return rtnval


def try_it_out_methods() -> Optional[Tuple[str, ...]]:
    """
        The HTTP methods the explorer's **Try it out** may send, from ``PYCHESTRATE_API_DOCS_TRY_IT_OUT``.

        :returns: ``None`` for every method (``all``, the default, also when unset), ``("GET",)`` for ``get``, ``()`` for ``off``. Any other value is read as ``get``:
                  a typo in a setting meant to make the page safer must not leave every method enabled.
    """
    raw = os.environ.get(TRY_IT_OUT_ENV_VAR, None)
    if raw is None or len(raw.strip()) == 0:
        return None
    value = raw.strip().lower()
    if value == "all":
        return None
    if value == "off":
        return ()
    if value != "get":
        _module_logger.warning(
            "pychestrate.openapi_document.unknown_try_it_out_setting value=%r reading=get (allowed: all, get, off)", raw,
        )
    return ("GET",)


def handle_get_openapi_document(request: Any) -> Any:
    """
        ``GET /api/v1/_meta/openapi.json`` -- the REST contract as JSON. ``?group_by=path`` returns the copy whose operations are tagged by where
        their path puts them (what the explorer page reads); any other ``group_by`` is a 400.

        :param request: Incoming webworks request.

        :returns: 200 JSON document, a 400 problem document for an unknown ``group_by``, or a 404 problem document when the
                  deployment does not carry the spec.
    """
    from ccai.webworks.routing.response import JSONResponse  # noqa: E402

    query = getattr(request, "query_params", None)
    group_by = str(query.get("group_by", "") or "").strip() if query is not None else ""
    if len(group_by) > 0 and group_by != GROUP_BY_PATH:
        rtnval = problem_response_for_http_status(
            status=400,
            detail="Query param 'group_by' must be '{}' when given.".format(GROUP_BY_PATH),
            instance=getattr(request, "path", None),
        )
        return rtnval
    document = load_grouped_document() if group_by == GROUP_BY_PATH else load_served_document()
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


#: The page's own policy: scripts from this origin only (no inline script, no eval), requests to this origin only (so Try it out can only call this
#: service), no third-party host. Swagger UI writes inline styles and uses data: images, which is all it is given beyond the service's default.
API_DOCS_CONTENT_SECURITY_POLICY: str = "; ".join([
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data:",
    "font-src 'self' data:",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
])

def _docs_page_html(*, version_prefix: str) -> str:
    """
        The Swagger UI page for a version prefix: the library and its starter, both from this origin, and no script of its own.

        :param version_prefix: Versioned API prefix (``"/api/v1"``).

        :returns: HTML.
    """
    from ccai.webworks.openapi.swaggerui import render_swagger_ui_page  # noqa: E402

    rtnval = render_swagger_ui_page(title=API_DOCS_TITLE, static_path=version_prefix + API_DOCS_ASSET_DIRECTORY)
    return rtnval


def _docs_initializer_js(*, version_prefix: str) -> bytes:
    """
        The script that starts Swagger UI on the path-grouped document, folded, with **Try it out** limited as ``PYCHESTRATE_API_DOCS_TRY_IT_OUT`` says.

        :param version_prefix: Versioned API prefix (``"/api/v1"``).

        :returns: The script, UTF-8.
    """
    from ccai.webworks.openapi.swaggerui import SwaggerUIOptions, render_swagger_ui_initializer  # noqa: E402

    script = render_swagger_ui_initializer(
        spec_url="{}{}?group_by={}".format(version_prefix, OPENAPI_DOCUMENT_PATH, GROUP_BY_PATH),
        options=SwaggerUIOptions(supported_submit_methods=try_it_out_methods()),
    )
    rtnval = script.encode("utf-8")
    return rtnval


def make_api_docs_handler(*, version_prefix: str) -> Any:
    """
        Build the ``GET <prefix>/_meta/docs`` handler.

        :param version_prefix: Versioned API prefix (``"/api/v1"``).

        :returns: A handler answering the Swagger UI page.
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


def make_api_docs_asset_handler(*, version_prefix: str) -> Any:
    """
        Build the ``GET <prefix>/_meta/docs/assets/{filename}`` handler.

        :param version_prefix: Versioned API prefix (``"/api/v1"``), which the starter script names the document under.

        :returns: A handler answering the Swagger UI library files and the starter script, and a 404 problem document for any other name (the
                  allowlist is webworks': only those files are ever read).
    """
    def handle_get_api_docs_asset(request: Any) -> Any:
        from ccai.webworks.openapi.swaggerui import SWAGGER_UI_INITIALIZER_NAME, read_swagger_ui_asset  # noqa: E402
        from ccai.webworks.routing.response import Response  # noqa: E402

        filename = str(request.path_params.get("filename", ""))
        content: Optional[bytes] = None
        content_type = ""
        if filename == SWAGGER_UI_INITIALIZER_NAME:
            content = _docs_initializer_js(version_prefix=version_prefix)
            content_type = "application/javascript"
        else:
            found = read_swagger_ui_asset(filename)
            if found is not None:
                content, content_type = found
        if content is None:
            rtnval = problem_response_for_http_status(
                status=404,
                detail="No such documentation asset.",
                instance=getattr(request, "path", None),
            )
            return rtnval
        # The starter script depends on a setting and the prefix; the library files never change under a release.
        cache = "no-cache" if filename == SWAGGER_UI_INITIALIZER_NAME else "private, max-age=86400"
        rtnval = Response(
            status_code=200,
            headers={"Content-Type": content_type, "Cache-Control": cache},
            body=content,
        )
        return rtnval

    return handle_get_api_docs_asset


def register_api_docs_routes(*, app: Any, version_prefix: str) -> None:
    """
        Attach ``GET <prefix>/_meta/docs`` (the Swagger UI explorer) and
        ``GET <prefix>/_meta/docs/assets/{filename}`` (its files and starter
        script), for any signed-in principal, and ``GET /api/docs``, which
        redirects to the page.

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
        require_rest_permission(make_api_docs_asset_handler(version_prefix=version_prefix), permission_key=AUTHENTICATED_ONLY)
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
    "API_DOCS_CONTENT_SECURITY_POLICY",
    "GROUP_BY_PATH",
    "API_DOCS_PATH",
    "OPENAPI_DOCUMENT_PATH",
    "SERVICE_VERSION_EXTENSION",
    "SPEC_RELATIVE_PATH",
    "handle_get_api_docs_alias",
    "load_grouped_document",
    "make_api_docs_asset_handler",
    "make_api_docs_handler",
    "handle_get_openapi_document",
    "load_served_document",
    "locate_spec_file",
    "try_it_out_methods",
    "read_service_version",
    "register_api_docs_routes",
    "register_openapi_document_routes",
    "reset_cache_for_testing",
]
