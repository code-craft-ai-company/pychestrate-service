"""
.. module:: api.problem_json_webworks
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks glue for the framework-agnostic problem_json builder.

.. moduleauthor:: Automation Mojo LLC

The framework-agnostic builder under :mod:`api.problem_json` produces
``(body, content_type, status_code)`` triples. WebWorks handlers
return :class:`automojo.webworks.routing.response.JSONResponse`
objects directly — there is no ``abort()``-style flow control in
the dispatcher. Handlers RETURN responses, including error
responses.

This module bridges the two worlds for the webworks REST surface:

* :func:`build_webworks_problem_response` — accepts a custom
  ``problem_type`` URI (extension-defined error class) and returns
  a JSON response carrying the RFC 7807 body with the documented
  ``application/problem+json`` content type.

* :func:`problem_response_for_http_status` — looks the status up
  in the documented type / title registry and returns the same.

Note on raise-vs-return
-----------------------
The flask glue exposes ``abort_with_problem`` because flask's
``abort(response)`` flow returns the supplied response verbatim.
The webworks dispatcher does NOT carry custom bodies through
:class:`HTTPException`: when a handler raises an HTTPException the
dispatcher rebuilds the body itself in its content-negotiated
shape (e.g., ``{"detail": ..., "status_code": ...}`` for the JSON
mode), discarding any body the exception carried. Therefore this
module provides only return-shaped helpers. Callers should::

    return problem_response_for_http_status(status=404, detail=...)

instead of raising HTTPException for problem-document errors.

A test seam — ``response_cls`` — accepts a stub response class so
the helpers are exercisable without coupling to webworks internals;
production callers omit it and the real :class:`JSONResponse` is
imported lazily.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Mapping, Optional

from automojo.pychestrate.webservice.api.problem_json import (
    PROBLEM_JSON_MEDIA_TYPE,
    ProblemResponse,
    build_problem_response,
    problem_for_http_status,
)


def _resolve_response_cls(response_cls: Optional[Any]) -> Any:
    """
        Return the supplied response class stub or import the real
        webworks ``JSONResponse``.

        The import is lazy so this module stays importable in
        environments where webworks is not yet installed (e.g.,
        partial dev installs); production callers always have
        webworks available.

        :param response_cls: Optional injected class (test seam).

        :returns: Class compatible with the JSONResponse constructor
                  signature ``(content, status_code, headers)``.
    """
    if response_cls is not None:
        rtnval = response_cls
        return rtnval

    from automojo.webworks.routing.response import JSONResponse

    rtnval = JSONResponse
    return rtnval


def _wrap_problem_response_for_webworks(
        *,
        problem_response: ProblemResponse,
        response_cls: Any
    ) -> Any:
    """
        Build a webworks JSON response carrying the RFC 7807 body
        with the documented ``application/problem+json`` content
        type.

        Pulled out so :func:`build_webworks_problem_response` and
        :func:`problem_response_for_http_status` share the wrapper
        and the content-type override stays in one place.

        :param problem_response: :class:`ProblemResponse` from the
                                 builder.
        :param response_cls: Resolved response class (real
                             :class:`JSONResponse` or stub).

        :returns: webworks response object with status, body, and
                  ``Content-Type: application/problem+json``.
    """
    response = response_cls(
        content=problem_response.body,
        status_code=problem_response.status_code,
    )
    response.set_header("Content-Type", problem_response.content_type)
    rtnval = response
    return rtnval


def build_webworks_problem_response(
        *,
        problem_type: str,
        title: str,
        status: int,
        detail: str,
        instance: Optional[str] = None,
        extensions: Optional[Mapping[str, Any]] = None,
        response_cls: Optional[Any] = None
    ) -> Any:
    """
        Construct a webworks JSON response carrying a custom-typed
        RFC 7807 problem document. Use when the caller has a
        specific ``problem_type`` URI (extension-defined error
        class).

        :param problem_type: URI for the problem class.
        :param title: Short summary.
        :param status: HTTP status code.
        :param detail: Occurrence-specific explanation.
        :param instance: Optional URI for this occurrence.
        :param extensions: Optional namespaced extension members.
        :param response_cls: Test seam — substitute a stub response
                             class.

        :returns: webworks response object ready to ``return`` from
                  a handler.
    """
    response_envelope = build_problem_response(
        problem_type=problem_type,
        title=title,
        status=status,
        detail=detail,
        instance=instance,
        extensions=extensions,
    )
    resolved_cls = _resolve_response_cls(response_cls)
    rtnval = _wrap_problem_response_for_webworks(
        problem_response=response_envelope,
        response_cls=resolved_cls,
    )
    return rtnval


def problem_response_for_http_status(
        *,
        status: int,
        detail: str,
        instance: Optional[str] = None,
        extensions: Optional[Mapping[str, Any]] = None,
        response_cls: Optional[Any] = None
    ) -> Any:
    """
        Build a webworks RFC 7807 response from a stock HTTP status
        code, routing the status to the documented ``type`` URI and
        ``title`` via :func:`problem_for_http_status`.

        Equivalent to flask's ``abort_with_problem`` in shape but
        returns the response instead of aborting — webworks handlers
        return responses (the dispatcher does not carry custom
        bodies through :class:`HTTPException`).

        :param status: HTTP status code (1xx-5xx).
        :param detail: Occurrence-specific explanation.
        :param instance: Optional URI for this occurrence (typically
                         the request path the handler was serving).
        :param extensions: Optional namespaced extension members
                           (e.g., ``{"flag_key": "auth.local"}`` for
                           a 409 on a duplicate flag).
        :param response_cls: Test seam — substitute a stub response
                             class.

        :returns: webworks response object ready to ``return`` from
                  a handler.
    """
    response_envelope = problem_for_http_status(
        status=status,
        detail=detail,
        instance=instance,
        extensions=extensions,
    )
    resolved_cls = _resolve_response_cls(response_cls)
    rtnval = _wrap_problem_response_for_webworks(
        problem_response=response_envelope,
        response_cls=resolved_cls,
    )
    return rtnval


__all__ = [
    "PROBLEM_JSON_MEDIA_TYPE",
    "build_webworks_problem_response",
    "problem_response_for_http_status",
]
