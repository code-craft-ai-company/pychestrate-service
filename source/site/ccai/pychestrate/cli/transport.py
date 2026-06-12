"""
.. module:: cli.transport
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: HTTP transport with bearer / mTLS auth modes.

.. moduleauthor:: Code Craft AI LLC

The transport is built on the standard library to keep the CLI free
of network-side dependencies. ``execute_request`` substitutes path
parameters into the operation template, attaches the configured auth
material, sends the request via ``urllib``, and reclassifies HTTP
status codes into the documented exception types so the entry-point
dispatcher can return stable exit codes.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import os
import ssl
import urllib.error
import urllib.parse
import urllib.request

from typing import Callable, Mapping, Optional

from ccai.pychestrate.cli.exceptions import (
    AuthenticationError,
    ConflictError,
    NotFoundError,
    RateLimitedError,
    ServerError,
)
from ccai.pychestrate.cli.models import CliProfile, RestOperation, RestResponse


DEFAULT_REQUEST_TIMEOUT_SECONDS: float = 30.0
USER_AGENT: str = "pyc-cli/1.0 (+https://docs.pychestrate.io)"


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
            err_msg = os.linesep.join(err_msg_lines)
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


def _classify_status(*, status_code: int, response_text: str) -> None:
    """
        Reclassify HTTP status codes >= 400 into the documented
        exception types so the entry-point dispatcher can map them to
        exit codes.

        :param status_code: HTTP status code from the server.
        :param response_text: Decoded response body for diagnostics.

        :returns: None (raises on errors).
    """
    if status_code < 400:
        return

    if status_code in (401, 403):
        raise AuthenticationError(
            "HTTP {}: {}".format(status_code, response_text)
        )
    if status_code == 404:
        raise NotFoundError("HTTP 404: {}".format(response_text))
    if status_code == 409:
        raise ConflictError("HTTP 409: {}".format(response_text))
    if status_code == 429:
        raise RateLimitedError("HTTP 429: {}".format(response_text))
    if status_code >= 500:
        raise ServerError("HTTP {}: {}".format(status_code, response_text))

    raise ServerError("HTTP {}: {}".format(status_code, response_text))


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


def _stdlib_open_callable(
        *,
        request: urllib.request.Request,
        timeout: float,
        context: Optional[ssl.SSLContext]
    ) -> RestResponse:
    """
        Default opener wrapping :func:`urllib.request.urlopen`. Pulled
        out so tests can substitute via ``execute_request(opener=...)``.

        :param request: Built :class:`urllib.request.Request`.
        :param timeout: Total timeout in seconds.
        :param context: Optional SSL context for HTTPS targets.

        :returns: Populated :class:`RestResponse`.
    """
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=context) as resp:
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

    raw_text = raw_bytes.decode("utf-8", errors="replace")
    body = _decode_body(raw_text=raw_text, content_type=headers.get("content-type", ""))
    rtnval = RestResponse(
        status_code=status,
        headers=headers,
        body=body,
        raw_text=raw_text,
    )
    return rtnval


def execute_request(
        *,
        profile: CliProfile,
        operation: RestOperation,
        path_params: Mapping[str, str],
        query_params: Mapping[str, str],
        body: Optional[object],
        idempotency_key: Optional[str],
        timeout_seconds: Optional[float],
        opener: Optional[Callable[..., RestResponse]]
    ) -> RestResponse:
    """
        Drive a single REST call.

        :param profile: Active :class:`CliProfile`.
        :param operation: Selected :class:`RestOperation`.
        :param path_params: Mapping of path parameters.
        :param query_params: Mapping of query parameters.
        :param body: Optional JSON-encodable body for POST/PUT/PATCH.
        :param idempotency_key: Optional ``Idempotency-Key`` header value.
        :param timeout_seconds: Override request timeout.
        :param opener: Test seam — alternative opener with the same
                       signature as :func:`_stdlib_open_callable`.

        :returns: :class:`RestResponse`.
        :raises: AuthenticationError, NotFoundError, ConflictError,
                 RateLimitedError, ServerError
    """
    server_url = profile.server_url
    if server_url.endswith("/"):
        server_url = server_url[:-1]

    rendered_path = _resolve_path(operation=operation, path_params=path_params)
    full_url = _attach_query_string(
        base_url="{}{}".format(server_url, rendered_path),
        query_params=query_params,
    )

    headers = {
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    }
    if profile.bearer_token is not None and len(profile.bearer_token) > 0:
        headers["Authorization"] = "Bearer {}".format(profile.bearer_token)
    if idempotency_key is not None and len(idempotency_key) > 0:
        headers["Idempotency-Key"] = idempotency_key

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

    effective_timeout = timeout_seconds if timeout_seconds is not None else DEFAULT_REQUEST_TIMEOUT_SECONDS
    context = _build_ssl_context(profile=profile)

    if opener is None:
        response = _stdlib_open_callable(
            request=request, timeout=effective_timeout, context=context
        )
    else:
        response = opener(
            request=request, timeout=effective_timeout, context=context
        )

    _classify_status(status_code=response.status_code, response_text=response.raw_text)
    rtnval = response
    return rtnval
