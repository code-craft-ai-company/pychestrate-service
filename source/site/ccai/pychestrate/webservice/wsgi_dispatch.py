"""
.. module:: wsgi_dispatch
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The WSGI handler shim between the WSGI builder and the
               webworks dispatcher.

.. moduleauthor:: Code Craft AI LLC

Lives outside ``app_pychestrate_main`` (which re-exports it) so it can
be imported and tested without establishing the process-global
webworks persona.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import logging

from typing import Any

from ccai.webworks.routing.request import Request
from ccai.webworks.routing.response import Response


#: Headers of the response a problem document replaces that are not carried
#: over (the new body sets its own).
_REPLACED_HEADERS = ("content-type", "content-length")


def framework_error_as_problem(*, request: Any, response: Response) -> Response:
    """
        Answer the RFC 7807 problem document for an error the webworks
        dispatcher built itself.

        The dispatcher answers an unmatched path, a wrong method or an
        unhandled exception with ``{"detail": ..., "status_code": ...}``
        (DOC-14), a shape no other error of the REST surface has. Only
        that exact shape is replaced, so a handler's own JSON error, a
        problem document, and every non-error response pass through
        untouched. Headers the framework set (``Allow`` on a 405) are kept.

        :param request: The request being answered.
        :param response: What the dispatcher returned.

        :returns: The problem-document response, or ``response`` itself.
    """
    status = getattr(response, "status_code", 200)
    if not isinstance(status, int) or status < 400:
        return response
    content_type = str(response.headers.get("Content-Type", "") or "").lower()
    if not content_type.startswith("application/json"):
        return response
    try:
        body = json.loads(response.body.decode("utf-8"))
    except (ValueError, AttributeError):
        return response
    if not (isinstance(body, dict) and set(body) == {"detail", "status_code"} and body["status_code"] == status
            and isinstance(body["detail"], str)):
        return response

    from ccai.pychestrate.webservice.api.problem_json_webworks import (  # noqa: E402
        problem_response_for_http_status,
    )
    replacement = problem_response_for_http_status(
        status=status, detail=body["detail"], instance=getattr(request, "path", None),
    )
    for name, value in response.headers.items():
        if name.lower() not in _REPLACED_HEADERS:
            replacement.headers[name] = value
    return replacement


def build_wsgi_compat_dispatch(*, app: Any) -> Any:
    """
        Return a callable that dispatches a webworks request and
        massages the returned :class:`Response` so the bundled
        :class:`ccai.webworks.wsgi.response.WSGIResponseBuilder`
        emits a correct HTTP response. Two version-skew bugs in
        the venv'd webworks library have to be papered over here:

        1. **Missing ``content_type`` attribute.** The builder
           reads ``response.content_type`` as an attribute when
           the body is non-empty, but :class:`Response` only
           stores the content type in the ``headers`` dict
           (e.g. ``{"Content-Type": "text/html"}``). Without the
           backfill every non-redirect response raises
           ``AttributeError`` inside the WSGI envelope and gets
           swallowed as a 500. Backfilling ``content_type =
           None`` is sufficient: the builder's
           :meth:`format_headers` already re-emits the
           Content-Type from ``headers`` when present and only
           falls back to the parameter when absent.

        2. **Set-Cookie headers dropped.**
           :meth:`Response.set_cookie` stores cookies in
           ``response._cookies`` (a :class:`SimpleCookie`).
           :meth:`Response._get_all_headers` correctly fans
           those out as ``Set-Cookie`` headers, but the WSGI
           builder ignores ``_cookies`` and only iterates the
           ``headers`` dict -- so any cookie a handler sets
           never reaches the wire.

           Push the serialized cookie value(s) into
           ``response.headers["Set-Cookie"]`` so the builder
           picks them up. Multi-cookie cases collapse onto the
           single header slot a dict supports; the consumer UI
           only sets one cookie per response so this is fine
           in practice. (A future webworks upgrade that fixes
           the builder to use ``Response.to_wsgi`` directly
           obsoletes this shim.)

        :param app: WebWorks application built by
                    :func:`establish_webapp_persona` and advanced
                    past ``INFRASTRUCTURE_READY``.

        :returns: A callable suitable for the ``handler`` slot in
                  :func:`create_wsgi_application`'s config.
    """
    dispatch = app.dispatcher.dispatch

    def _dispatch_with_response_compat(
            request: Request
        ) -> Response:
        try:
            response = dispatch(request)
        except BaseException as unhandled:
            # The ccai.errors exceptions (SemanticError, ...) derive from
            # BaseException, not Exception, so the webworks dispatcher's
            # handler lets them through and the WSGI server never answers:
            # the client waits out its own timeout. Log and answer an
            # RFC 7807 500 instead; process-control exceptions still pass.
            if isinstance(unhandled, (KeyboardInterrupt, SystemExit, GeneratorExit)):
                raise
            logging.getLogger("pychestrate.dispatch").exception(
                "pychestrate.dispatch.unhandled_exception method=%s path=%s",
                getattr(request, "method", "?"), getattr(request, "path", "?"),
            )
            from ccai.pychestrate.webservice.api.problem_json_webworks import (  # noqa: E402
                problem_response_for_http_status,
            )
            response = problem_response_for_http_status(
                status=500,
                detail="Internal Server Error",
                instance=getattr(request, "path", None),
            )
        response = framework_error_as_problem(request=request, response=response)
        if not hasattr(response, "content_type"):
            response.content_type = None

        # Push any cookies set via ``response.set_cookie(...)``
        # into the response headers dict so the bundled WSGI
        # builder emits them.
        cookies_jar = getattr(response, "_cookies", None)
        if cookies_jar is not None and len(cookies_jar) > 0:
            cookie_header_values = []
            for cookie_name in cookies_jar:
                morsel = cookies_jar[cookie_name]
                cookie_header_values.append(morsel.OutputString())
            # The WSGI ``format_headers`` step skips hop-by-hop
            # headers but does not coalesce repeated names; a
            # dict slot can only carry one value, so we join with
            # ``\r\n`` -- WSGI servers split this back into
            # separate Set-Cookie headers per the WSGI spec
            # (PEP 3333 explicitly allows this for hosting
            # frameworks).  The webworks builder's
            # ``format_headers`` produces a list of (name, value)
            # tuples though, and its consumer (the WSGI app's
            # ``__call__``) just hands them to ``start_response``,
            # which on most servers treats them as a single
            # header. To be safe and to keep the behavior simple,
            # set only the first cookie via the headers dict and
            # drop any additional. This module's UI only sets
            # one cookie per response.
            response.headers["Set-Cookie"] = cookie_header_values[0]

        return response

    rtnval = _dispatch_with_response_compat
    return rtnval


__all__ = [
    "build_wsgi_compat_dispatch",
    "framework_error_as_problem",
]
