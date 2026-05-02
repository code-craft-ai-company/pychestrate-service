"""
.. module:: api.problem_json_flask
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Flask glue for the framework-agnostic problem_json builder.

.. moduleauthor:: Automation Mojo LLC

The framework-agnostic builder under :mod:`api.problem_json` produces
``(body, content_type, status_code)`` triples. Flask-restx
controllers historically call ``ns.abort(<status>, "<message>")``
which produces a ``{"message": "..."}`` body. This module bridges
the two worlds: :func:`abort_with_problem` builds the documented
RFC 7807 problem document, wraps it in a Flask response with the
``application/problem+json`` content type, and raises the HTTP
exception so flask-restx returns the body verbatim.

Flask is imported lazily inside the function so this module is
importable in environments where flask is not installed (the test
venv, the CLI build, doc generators). Production callers (REST
controllers running inside the service) always have flask
available — the lazy import is purely a build-hygiene measure.

Tests inject a ``flask_module`` keyword argument carrying a stub
that captures calls; production callers omit it and the function
imports the real :mod:`flask` package.
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


def _resolve_flask_module(flask_module: Optional[Any]) -> Any:
    """
        Return the supplied flask stub or import the real package.

        :param flask_module: Optional injected module (test seam).

        :returns: Module-like object exposing
                  ``jsonify`` / ``make_response`` / ``abort``.
    """
    if flask_module is not None:
        rtnval = flask_module
        return rtnval

    import flask

    rtnval = flask
    return rtnval


def _wrap_problem_response_for_flask(
        *,
        problem_response: ProblemResponse,
        flask_module: Any
    ) -> Any:
    """
        Build a Flask response object carrying the RFC 7807 body.

        Pulled out so :func:`abort_with_problem` and
        :func:`build_flask_problem_response` (the non-aborting form
        used by ``after_request`` middleware) share the wrapper.

        :param problem_response: :class:`ProblemResponse` from the
                                 builder.
        :param flask_module: Resolved flask module.

        :returns: Flask response object.
    """
    body = flask_module.jsonify(problem_response.body)
    flask_response = flask_module.make_response(
        body, problem_response.status_code
    )
    flask_response.headers["Content-Type"] = problem_response.content_type
    rtnval = flask_response
    return rtnval


def build_flask_problem_response(
        *,
        problem_type: str,
        title: str,
        status: int,
        detail: str,
        instance: Optional[str] = None,
        extensions: Optional[Mapping[str, Any]] = None,
        flask_module: Optional[Any] = None
    ) -> Any:
    """
        Construct a Flask response carrying a custom-typed RFC 7807
        problem document. Use when the caller has a specific
        ``problem_type`` URI (extension-defined error class).

        :param problem_type: URI for the problem class.
        :param title: Short summary.
        :param status: HTTP status code.
        :param detail: Occurrence-specific explanation.
        :param instance: Optional URI for this occurrence.
        :param extensions: Optional namespaced extension members.
        :param flask_module: Test seam — substitute a stub flask.

        :returns: Flask response object ready to ``return`` from a
                  controller method (instead of ``abort``-ing).
    """
    response_envelope = build_problem_response(
        problem_type=problem_type,
        title=title,
        status=status,
        detail=detail,
        instance=instance,
        extensions=extensions,
    )
    resolved_flask = _resolve_flask_module(flask_module)
    rtnval = _wrap_problem_response_for_flask(
        problem_response=response_envelope, flask_module=resolved_flask
    )
    return rtnval


def abort_with_problem(
        *,
        status: int,
        detail: str,
        instance: Optional[str] = None,
        extensions: Optional[Mapping[str, Any]] = None,
        flask_module: Optional[Any] = None
    ) -> None:
    """
        Abort the current Flask request with an RFC 7807 problem
        document. The status maps to a documented ``type`` URI under
        ``https://docs.pychestrate.io/errors/`` via
        :func:`problem_for_http_status`; unrecognized status codes
        fall back to ``unknown-error`` rather than producing a
        malformed document.

        :param status: HTTP status code (1xx-5xx).
        :param detail: Occurrence-specific explanation.
        :param instance: Optional URI for this occurrence (typically
                         the request path the controller was serving).
        :param extensions: Optional namespaced extension members
                           (e.g., ``{"flag_key": "auth.local"}`` for
                           a 409 on a duplicate flag).
        :param flask_module: Test seam — substitute a stub flask.

        :returns: Never returns; raises ``flask.abort``'s
                  HTTPException via the resolved flask module.
    """
    response_envelope = problem_for_http_status(
        status=status,
        detail=detail,
        instance=instance,
        extensions=extensions,
    )
    resolved_flask = _resolve_flask_module(flask_module)
    flask_response = _wrap_problem_response_for_flask(
        problem_response=response_envelope, flask_module=resolved_flask
    )
    resolved_flask.abort(flask_response)
    return


__all__ = [
    "PROBLEM_JSON_MEDIA_TYPE",
    "abort_with_problem",
    "build_flask_problem_response",
]
