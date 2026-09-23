"""
.. module:: cli.transport
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: HTTP transport with bearer / mTLS auth modes.

.. moduleauthor:: Code Craft AI LLC

The transport is built on the standard library to keep the CLI free
of network-side dependencies. ``execute_request`` substitutes path
parameters into the operation template, attaches the configured auth
material, sends the request via ``urllib``, and reclassifies the
outcome into the documented exception types so the entry-point
dispatcher can return stable exit codes:

* No redirect is ever followed. An API call that is redirected (to the
  sign-in page, typically) or answered with an HTML page is not the
  API talking; it raises :class:`UnexpectedResponseError` naming the
  likely cause (a ``server_url`` that is not the service root, or a
  missing / rejected token) instead of printing the page as success.
* A request that gets no HTTP answer at all -- connection refused, DNS
  failure, TLS failure, timeout, malformed URL -- raises
  :class:`ServerUnreachableError` ("cannot reach <url>: <reason>").
* 4xx / 5xx answers map to one exception class per exit-code category;
  an RFC 7807 problem document is rendered as ``title: detail``.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import http.client
import json
import os
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request

from typing import Callable, Dict, Mapping, Optional

from ccai.pychestrate.cli.exceptions import (
    AuthenticationError,
    BadRequestError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitedError,
    ServerError,
    ServerUnreachableError,
    UnexpectedResponseError,
)
from ccai.pychestrate.cli.models import CliProfile, RestOperation, RestResponse


DEFAULT_REQUEST_TIMEOUT_SECONDS: float = 30.0
USER_AGENT: str = "pyc-cli/1.0 (+https://docs.pychestrate.io)"

#: Longest non-JSON body excerpt quoted in an error message.
_BODY_EXCERPT_LIMIT: int = 300


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """
        Refuse every redirect: ``urllib`` then surfaces the 3xx as an
        :class:`urllib.error.HTTPError`, which the transport classifies
        as an unexpected response.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        return None


def _resolve_path(*, operation: RestOperation, path_params: Mapping[str, str]) -> str:
    """
        Substitute ``{name}`` placeholders in an OpenAPI path template.

        :param operation: :class:`RestOperation`.
        :param path_params: Mapping of path-parameter values.

        :returns: Concrete path string ready to append to the server URL.
        :raises: KeyError when a required path parameter is missing.
    """
    rendered = operation.path_template
    for name in operation.path_param_names:
        placeholder = "{" + name + "}"
        if name in path_params:
            value = urllib.parse.quote(str(path_params[name]), safe="")
            rendered = rendered.replace(placeholder, value)
            continue
        if name in operation.required_path_param_names:
            err_msg_lines = ["Missing required path parameter."]
            err_msg_lines.append("OPERATION_ID: {}".format(operation.operation_id))
            err_msg_lines.append("PARAM: {}".format(name))
            raise KeyError(os.linesep.join(err_msg_lines)) from None
    rtnval = rendered
    return rtnval


def _attach_query_string(*, base_url: str, query_params: Mapping[str, str]) -> str:
    """
        Append a query string to ``base_url`` when ``query_params`` has any
        non-``None`` value.

        :param base_url: URL up to and including the path.
        :param query_params: Caller-supplied query mapping.

        :returns: URL with optional ``?...`` suffix.
    """
    pairs = []
    for key, value in query_params.items():
        if value is None:
            continue
        pairs.append((key, str(value)))
    if len(pairs) == 0:
        rtnval = base_url
        return rtnval
    encoded = urllib.parse.urlencode(pairs)
    rtnval = "{}?{}".format(base_url, encoded)
    return rtnval


def _build_ssl_context(*, profile: CliProfile) -> ssl.SSLContext:
    """
        Build an :class:`ssl.SSLContext` honoring ``verify_tls`` and
        loading the mTLS keypair when both paths are configured.

        :param profile: Resolved :class:`CliProfile`.

        :returns: Configured SSL context.
    """
    context = ssl.create_default_context()
    if profile.verify_tls is False:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    if profile.mtls_cert_path is not None and profile.mtls_key_path is not None:
        context.load_cert_chain(
            certfile=profile.mtls_cert_path,
            keyfile=profile.mtls_key_path,
        )
    return context


def validate_server_url(*, server_url: str) -> str:
    """
        Check that ``server_url`` is an absolute ``http(s)`` URL with a
        host, and return it without a trailing slash.

        :param server_url: Configured server URL.

        :returns: Normalized URL.
        :raises: ServerUnreachableError for anything else.
    """
    candidate = (server_url or "").strip()
    parsed = urllib.parse.urlsplit(candidate)
    if parsed.scheme not in ("http", "https") or len(parsed.netloc) == 0:
        shown = candidate if len(candidate) > 0 else "(empty)"
        raise ServerUnreachableError(
            "cannot reach {}: invalid server URL (expected http(s)://host[:port]);"
            " set it with 'pyc login --server-url <url>' or --server-url".format(shown)
        ) from None
    rtnval = candidate.rstrip("/")
    return rtnval


def _describe_network_error(*, xcpt: BaseException) -> str:
    """
        One-line reason for a failed connection.

        :param xcpt: The raised exception.

        :returns: Reason text.
    """
    reason = xcpt
    if isinstance(xcpt, urllib.error.URLError) and not isinstance(xcpt, urllib.error.HTTPError):
        reason = xcpt.reason
    if isinstance(reason, (socket.timeout, TimeoutError)):
        return "timed out"
    if isinstance(reason, ssl.SSLCertVerificationError):
        return "TLS certificate verification failed ({})".format(
            getattr(reason, "verify_message", None) or reason
        )
    if isinstance(reason, ssl.SSLError):
        return "TLS error ({})".format(reason)
    if isinstance(reason, socket.gaierror):
        return "host name not found ({})".format(reason.strerror or reason)
    if isinstance(reason, ConnectionRefusedError):
        return "connection refused (is the server running on that host and port?)"
    if isinstance(reason, OSError) and reason.strerror is not None:
        return reason.strerror
    rtnval = str(reason) if len(str(reason)) > 0 else type(reason).__name__
    return rtnval


def _stdlib_open_callable(
        *,
        request: urllib.request.Request,
        timeout: float,
        context: Optional[ssl.SSLContext]
    ) -> RestResponse:
    """
        Default opener: :mod:`urllib` with redirects disabled. Pulled out
        so tests can substitute via ``execute_request(opener=...)``.

        :param request: Built :class:`urllib.request.Request`.
        :param timeout: Total timeout in seconds.
        :param context: Optional SSL context for HTTPS targets.

        :returns: Populated :class:`RestResponse` (any status).
        :raises: ServerUnreachableError when no HTTP answer arrives.
    """
    opener = urllib.request.build_opener(
        _NoRedirectHandler(), urllib.request.HTTPSHandler(context=context)
    )
    url = request.full_url
    try:
        with opener.open(request, timeout=timeout) as resp:
            raw_bytes = resp.read()
            status = int(resp.status)
            headers = {k.lower(): v for k, v in resp.headers.items()}
    except urllib.error.HTTPError as xcpt:
        try:
            raw_bytes = xcpt.read()
        except Exception:  # noqa: BLE001 — defensive
            raw_bytes = b""
        status = int(xcpt.code)
        headers = {}
        if xcpt.headers is not None:
            headers = {k.lower(): v for k, v in xcpt.headers.items()}
    except (urllib.error.URLError, http.client.HTTPException, OSError, ValueError) as xcpt:
        if isinstance(xcpt, ValueError):
            reason = "invalid URL ({})".format(xcpt)
        elif isinstance(xcpt, (socket.timeout, TimeoutError)):
            reason = "timed out after {:g}s".format(timeout)
        else:
            reason = _describe_network_error(xcpt=xcpt)
            if reason == "timed out":
                reason = "timed out after {:g}s".format(timeout)
        raise ServerUnreachableError("cannot reach {}: {}".format(url, reason)) from None

    raw_text = raw_bytes.decode("utf-8", errors="replace")
    body = _decode_body(raw_text=raw_text, content_type=headers.get("content-type", ""))
    rtnval = RestResponse(
        status_code=status,
        headers=headers,
        body=body,
        raw_text=raw_text,
    )
    return rtnval


def _decode_body(*, raw_text: str, content_type: str) -> Optional[object]:
    """
        Decode the response body when it advertises JSON.

        :param raw_text: Raw response text.
        :param content_type: ``Content-Type`` header value.

        :returns: Parsed JSON object, raw text, or ``None`` for empty
                  responses.
    """
    if raw_text is None or len(raw_text) == 0:
        rtnval: Optional[object] = None
        return rtnval

    if content_type is not None and "json" in content_type.lower():
        try:
            rtnval = json.loads(raw_text)
            return rtnval
        except json.JSONDecodeError:
            pass

    rtnval = raw_text
    return rtnval


def _content_type(headers: Mapping[str, str]) -> str:
    """
        Lower-cased ``Content-Type`` without parameters.

        :param headers: Lower-cased header mapping.

        :returns: Media type or ``""``.
    """
    raw = headers.get("content-type", "") if headers is not None else ""
    rtnval = str(raw).split(";", 1)[0].strip().lower()
    return rtnval


def describe_error_body(*, status_code: int, response_text: str, headers: Mapping[str, str]) -> str:
    """
        Render an error response for the terminal: a problem document
        as ``title: detail``, anything else as a short excerpt.

        :param status_code: HTTP status.
        :param response_text: Raw body.
        :param headers: Lower-cased headers.

        :returns: One-line message.
    """
    problem = None
    try:
        problem = json.loads(response_text) if response_text else None
    except (TypeError, ValueError):
        problem = None

    if isinstance(problem, dict) and ("title" in problem or "detail" in problem):
        # Server details are often multi-line ("...\nSLUG: x"); keep
        # the report on one line.
        title = " ".join(str(problem.get("title", "") or "").split())
        detail = " ".join(str(problem.get("detail", "") or "").split())
        parts = [part for part in (title, detail) if len(part) > 0]
        message = ": ".join(parts)
        if "required_permission" in problem:
            message = "{} (requires {})".format(message, problem["required_permission"])
        rtnval = "{} (HTTP {})".format(message, status_code)
        return rtnval

    if _content_type(headers) == "text/html" or "<html" in (response_text or "")[:500].lower():
        rtnval = "HTTP {}: the server answered with an HTML page".format(status_code)
        return rtnval

    excerpt = " ".join((response_text or "").split())
    if len(excerpt) > _BODY_EXCERPT_LIMIT:
        excerpt = excerpt[:_BODY_EXCERPT_LIMIT] + "..."
    if len(excerpt) == 0:
        excerpt = http.client.responses.get(status_code, "no body")
    rtnval = "HTTP {}: {}".format(status_code, excerpt)
    return rtnval


def _redirect_message(*, status_code: int, headers: Mapping[str, str], url: str) -> str:
    """
        Explain a redirect answer to an API call.

        :param status_code: 3xx status.
        :param headers: Lower-cased headers.
        :param url: Requested URL.

        :returns: Message.
    """
    location = headers.get("location", "") if headers is not None else ""
    lines = [
        "the server answered HTTP {} (redirect to {}) instead of JSON for {}.".format(
            status_code, location or "an unspecified location", url
        )
    ]
    if "login" in location:
        lines.append(
            "It is sending you to the sign-in page: the request carried no accepted"
            " API token (run 'pyc login'), or server_url is not the service root."
        )
    else:
        lines.append(
            "server_url is probably not the service root: use https://host[:port],"
            " not a web-UI page or a /api/v1 URL."
        )
    rtnval = " ".join(lines)
    return rtnval


def _classify_status(
        *,
        status_code: int,
        response_text: str,
        headers: Optional[Mapping[str, str]] = None,
        url: str = ""
    ) -> None:
    """
        Reclassify an HTTP answer into the documented exception types
        so the entry-point dispatcher can map them to exit codes.

        :param status_code: HTTP status code from the server.
        :param response_text: Decoded response body for diagnostics.
        :param headers: Lower-cased response headers.
        :param url: The requested URL (for messages).

        :returns: None (raises on errors).
    """
    resolved_headers: Mapping[str, str] = headers if headers is not None else {}

    if 300 <= status_code < 400:
        raise UnexpectedResponseError(
            _redirect_message(status_code=status_code, headers=resolved_headers, url=url)
        )

    if 200 <= status_code < 300:
        if _content_type(resolved_headers) == "text/html":
            raise UnexpectedResponseError(
                "the server answered HTTP {} with an HTML page instead of JSON for {}."
                " server_url is probably a web-UI page or a proxy, not the service root"
                " (use https://host[:port]).".format(status_code, url)
            )
        return

    if status_code < 400:
        return

    message = describe_error_body(
        status_code=status_code, response_text=response_text, headers=resolved_headers
    )
    if status_code in (400, 422):
        raise BadRequestError(message)
    if status_code == 401:
        raise AuthenticationError(message)
    if status_code == 403:
        raise PermissionDeniedError(message)
    if status_code == 404:
        raise NotFoundError(message)
    if status_code == 409:
        raise ConflictError(message)
    if status_code == 429:
        retry_after = resolved_headers.get("retry-after", "")
        if len(str(retry_after)) > 0:
            message = "{}; retry after {}s".format(message, retry_after)
        raise RateLimitedError(message)
    if status_code >= 500:
        raise ServerError(message)

    raise UnexpectedResponseError(message)


def execute_request(
        *,
        profile: CliProfile,
        operation: RestOperation,
        path_params: Mapping[str, str],
        query_params: Mapping[str, str],
        body: Optional[object],
        idempotency_key: Optional[str],
        timeout_seconds: Optional[float],
        opener: Optional[Callable[..., RestResponse]],
        extra_headers: Optional[Mapping[str, str]] = None
    ) -> RestResponse:
    """
        Drive a single REST call.

        :param profile: Active :class:`CliProfile`.
        :param operation: Selected :class:`RestOperation`.
        :param path_params: Mapping of path parameters.
        :param query_params: Mapping of query parameters.
        :param body: Optional JSON-encodable body for POST/PUT/PATCH.
        :param idempotency_key: Optional ``Idempotency-Key`` header value.
        :param timeout_seconds: Override request timeout (falls back to
                                the profile's, then 30 s).
        :param opener: Test seam — alternative opener with the same
                       signature as :func:`_stdlib_open_callable`.
        :param extra_headers: Additional request headers.

        :returns: :class:`RestResponse`.
        :raises: AuthenticationError, PermissionDeniedError,
                 BadRequestError, NotFoundError, ConflictError,
                 RateLimitedError, ServerError, UnexpectedResponseError,
                 ServerUnreachableError
    """
    server_url = validate_server_url(server_url=profile.server_url)

    rendered_path = _resolve_path(operation=operation, path_params=path_params)
    full_url = _attach_query_string(
        base_url="{}{}".format(server_url, rendered_path),
        query_params=query_params,
    )

    headers: Dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    }
    if profile.bearer_token is not None and len(profile.bearer_token) > 0:
        headers["Authorization"] = "Bearer {}".format(profile.bearer_token)
    if idempotency_key is not None and len(idempotency_key) > 0:
        headers["Idempotency-Key"] = idempotency_key
    if extra_headers is not None:
        for header_name, header_value in extra_headers.items():
            headers[header_name] = header_value

    body_bytes: Optional[bytes] = None
    if body is not None:
        body_bytes = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(
        url=full_url,
        data=body_bytes,
        headers=headers,
        method=operation.method.upper(),
    )

    if timeout_seconds is not None:
        effective_timeout = timeout_seconds
    elif profile.timeout_seconds is not None:
        effective_timeout = profile.timeout_seconds
    else:
        effective_timeout = DEFAULT_REQUEST_TIMEOUT_SECONDS
    context = _build_ssl_context(profile=profile)

    if opener is None:
        response = _stdlib_open_callable(
            request=request, timeout=effective_timeout, context=context
        )
    else:
        response = opener(
            request=request, timeout=effective_timeout, context=context
        )

    _classify_status(
        status_code=response.status_code,
        response_text=response.raw_text,
        headers=response.headers,
        url=full_url,
    )
    rtnval = response
    return rtnval
