"""
.. module:: api.problem_json
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: RFC 7807 problem-document builder for the REST surface.

.. moduleauthor:: Automation Mojo LLC

Every error response Pychestrate's REST surface emits SHALL be a
"problem detail" document per RFC 7807, served with the
``application/problem+json`` content type. This module produces those
documents in a framework-agnostic shape: a frozen dataclass and a
builder returning a ``(body, content_type, status_code)`` triple that
flask-restx, ASGI, or stdlib HTTP layers can dispatch.

The standard members per RFC 7807 §3.1 are:

* ``type`` — URI reference identifying the problem class.
* ``title`` — short human-readable summary.
* ``status`` — HTTP status code.
* ``detail`` — human-readable explanation specific to this occurrence.
* ``instance`` — URI reference identifying the specific occurrence.

Implementations may add extension members; this module supports them
via the ``extensions`` mapping on :class:`ProblemDocument`.

Documented problem types are exposed via the
``PROBLEM_TYPE_*`` constants and the :func:`problem_for_http_status`
shortcut. Operators can extend the registry with site-specific
``type`` URLs by passing ``problem_type=`` to
:func:`build_problem_response` directly.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional, Tuple


PROBLEM_JSON_MEDIA_TYPE: str = "application/problem+json"
PROBLEM_TYPE_BASE_URL: str = "https://docs.pychestrate.io/errors/"

PROBLEM_TYPE_BAD_REQUEST: str = PROBLEM_TYPE_BASE_URL + "bad-request"
PROBLEM_TYPE_UNAUTHENTICATED: str = PROBLEM_TYPE_BASE_URL + "unauthenticated"
PROBLEM_TYPE_FORBIDDEN: str = PROBLEM_TYPE_BASE_URL + "forbidden"
PROBLEM_TYPE_NOT_FOUND: str = PROBLEM_TYPE_BASE_URL + "not-found"
PROBLEM_TYPE_METHOD_NOT_ALLOWED: str = PROBLEM_TYPE_BASE_URL + "method-not-allowed"
PROBLEM_TYPE_CONFLICT: str = PROBLEM_TYPE_BASE_URL + "conflict"
PROBLEM_TYPE_VALIDATION_FAILED: str = PROBLEM_TYPE_BASE_URL + "validation-failed"
PROBLEM_TYPE_RATE_LIMITED: str = PROBLEM_TYPE_BASE_URL + "rate-limited"
PROBLEM_TYPE_INTERNAL_SERVER_ERROR: str = PROBLEM_TYPE_BASE_URL + "internal-server-error"
PROBLEM_TYPE_SERVICE_UNAVAILABLE: str = PROBLEM_TYPE_BASE_URL + "service-unavailable"


_DEFAULT_PROBLEM_BY_STATUS: Dict[int, Tuple[str, str]] = {
    400: (PROBLEM_TYPE_BAD_REQUEST, "Bad Request"),
    401: (PROBLEM_TYPE_UNAUTHENTICATED, "Unauthenticated"),
    403: (PROBLEM_TYPE_FORBIDDEN, "Forbidden"),
    404: (PROBLEM_TYPE_NOT_FOUND, "Not Found"),
    405: (PROBLEM_TYPE_METHOD_NOT_ALLOWED, "Method Not Allowed"),
    409: (PROBLEM_TYPE_CONFLICT, "Conflict"),
    422: (PROBLEM_TYPE_VALIDATION_FAILED, "Validation Failed"),
    429: (PROBLEM_TYPE_RATE_LIMITED, "Rate Limited"),
    500: (PROBLEM_TYPE_INTERNAL_SERVER_ERROR, "Internal Server Error"),
    503: (PROBLEM_TYPE_SERVICE_UNAVAILABLE, "Service Unavailable"),
}


_RFC7807_RESERVED_KEYS = ("type", "title", "status", "detail", "instance")


@dataclass(frozen=True)
class ProblemDocument:
    """
        RFC 7807 problem detail.

        :param type: URI reference identifying the problem class.
        :param title: Short, human-readable summary. Should not change
                      from occurrence to occurrence.
        :param status: HTTP status code.
        :param detail: Occurrence-specific human-readable explanation.
        :param instance: Optional URI identifying this specific
                         occurrence (typically the request path).
        :param extensions: Optional mapping of namespaced extension
                           members. Keys SHOULD NOT collide with the
                           reserved RFC 7807 names.
    """
    type: str
    title: str
    status: int
    detail: str
    instance: Optional[str] = None
    extensions: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProblemResponse:
    """
        Serialization-ready triple matching the contract framework
        adapters expect.

        :param body: JSON-friendly dict that ``json.dumps`` round-trips
                     into the problem-document wire format.
        :param content_type: Always ``application/problem+json``.
        :param status_code: HTTP status code.
    """
    body: Dict[str, Any]
    content_type: str
    status_code: int


def _ensure_extension_keys_are_safe(*, extensions: Mapping[str, Any]) -> None:
    """
        Guard against extension members that shadow the reserved RFC
        7807 names. Shadowing is silent corruption — we refuse rather
        than letting the caller produce a wire response that contradicts
        the spec.

        :param extensions: Caller-supplied mapping.

        :returns: None.
        :raises: ValueError on collision.
    """
    for reserved in _RFC7807_RESERVED_KEYS:
        if reserved in extensions:
            raise ValueError(
                "Extension key {!r} collides with a reserved RFC 7807 member".format(
                    reserved
                )
            )
    return


def build_problem_document(
        *,
        problem_type: str,
        title: str,
        status: int,
        detail: str,
        instance: Optional[str],
        extensions: Optional[Mapping[str, Any]]
    ) -> ProblemDocument:
    """
        Build a :class:`ProblemDocument` from caller-supplied fields.

        :param problem_type: URI reference identifying the problem class.
        :param title: Short, human-readable summary.
        :param status: HTTP status code (1xx-5xx).
        :param detail: Occurrence-specific explanation.
        :param instance: Optional URI for this occurrence.
        :param extensions: Optional namespaced extension members.

        :returns: :class:`ProblemDocument` ready for serialization.
        :raises: ValueError on invalid status / extension collision.
    """
    if not isinstance(status, int) or status < 100 or status > 599:
        raise ValueError("status must be a 1xx-5xx HTTP status code")

    if extensions is None:
        normalized_extensions: Mapping[str, Any] = {}
    else:
        _ensure_extension_keys_are_safe(extensions=extensions)
        normalized_extensions = dict(extensions)

    rtnval = ProblemDocument(
        type=problem_type,
        title=title,
        status=int(status),
        detail=detail,
        instance=instance,
        extensions=normalized_extensions,
    )
    return rtnval


def _document_to_body(*, document: ProblemDocument) -> Dict[str, Any]:
    """
        Render a :class:`ProblemDocument` as a JSON-friendly dict in
        the documented order: type, title, status, detail, instance,
        then the extensions in insertion order.

        :param document: Document under serialization.

        :returns: Dict ready for ``json.dumps``.
    """
    body: Dict[str, Any] = {
        "type": document.type,
        "title": document.title,
        "status": document.status,
        "detail": document.detail,
    }
    if document.instance is not None:
        body["instance"] = document.instance

    for key, value in document.extensions.items():
        body[key] = value

    rtnval = body
    return rtnval


def build_problem_response(
        *,
        problem_type: str,
        title: str,
        status: int,
        detail: str,
        instance: Optional[str] = None,
        extensions: Optional[Mapping[str, Any]] = None
    ) -> ProblemResponse:
    """
        Convenience wrapper returning the
        ``(body, content_type, status_code)`` triple framework
        adapters dispatch.

        :param problem_type: URI reference for the problem class.
        :param title: Short summary.
        :param status: HTTP status.
        :param detail: Occurrence-specific explanation.
        :param instance: Optional occurrence URI.
        :param extensions: Optional namespaced extension members.

        :returns: :class:`ProblemResponse`.
    """
    document = build_problem_document(
        problem_type=problem_type,
        title=title,
        status=status,
        detail=detail,
        instance=instance,
        extensions=extensions,
    )
    body = _document_to_body(document=document)
    rtnval = ProblemResponse(
        body=body,
        content_type=PROBLEM_JSON_MEDIA_TYPE,
        status_code=int(status),
    )
    return rtnval


def problem_for_http_status(
        *,
        status: int,
        detail: str,
        instance: Optional[str] = None,
        extensions: Optional[Mapping[str, Any]] = None
    ) -> ProblemResponse:
    """
        Build a :class:`ProblemResponse` from a stock HTTP status code.

        Looks the status up in the documented type / title registry
        (covering the common 4xx and 5xx codes) and falls back to a
        generic ``unknown-error`` type when the status is not in the
        registry — that fallback should be rare, but ensures the
        builder never returns a malformed document.

        :param status: HTTP status code.
        :param detail: Occurrence-specific explanation.
        :param instance: Optional occurrence URI.
        :param extensions: Optional namespaced extension members.

        :returns: :class:`ProblemResponse`.
    """
    if status in _DEFAULT_PROBLEM_BY_STATUS:
        problem_type, title = _DEFAULT_PROBLEM_BY_STATUS[status]
    else:
        problem_type = PROBLEM_TYPE_BASE_URL + "unknown-error"
        title = "Error"

    rtnval = build_problem_response(
        problem_type=problem_type,
        title=title,
        status=status,
        detail=detail,
        instance=instance,
        extensions=extensions,
    )
    return rtnval
