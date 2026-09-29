"""
.. module:: api.problem_json
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: RFC 7807 problem-document builder for the REST surface.

.. moduleauthor:: Code Craft AI LLC

Every error response Pychestrate's REST surface emits SHALL be a
"problem detail" document per RFC 7807, served with the
``application/problem+json`` content type. This module produces those
documents in a framework-agnostic shape: a frozen dataclass and a
builder returning a ``(body, content_type, status_code)`` triple
that webworks, ASGI, or stdlib HTTP layers can dispatch.

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

The documented ``type`` values are references to pages the service
itself serves (``/errors/<slug>``, see :mod:`api.error_catalogue`), so
following one always leads somewhere. A ``type`` is the service-relative
reference ``/errors/not-found`` unless ``PYCHESTRATE_PUBLIC_BASE_URL`` is
set, in which case it is the absolute URL under that base (the same rule
:mod:`public_endpoint` applies to the URLs it signs). They used to name
``https://docs.pychestrate.io/errors/...``, a site nothing publishes.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional, Tuple


PROBLEM_JSON_MEDIA_TYPE: str = "application/problem+json"
#: Where the documented problem types live on the service itself.
PROBLEM_TYPE_BASE_URL: str = "/errors/"

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


UNKNOWN_ERROR_SLUG: str = "unknown-error"


@dataclass(frozen=True)
class ProblemTypeInfo:
    """
        What the catalogue page of one documented problem type says.

        :param slug: The last segment of the ``type`` reference.
        :param status: The HTTP status the type goes with (0 for the
                       catch-all).
        :param title: The ``title`` member responses of this type carry.
        :param meaning: What the problem is, in a sentence or two.
        :param remedy: What the caller can do about it.
    """
    slug: str
    status: int
    title: str
    meaning: str
    remedy: str


#: The documented problem types, in status order. The page for each is
#: ``/errors/<slug>``.
PROBLEM_TYPES: Tuple[ProblemTypeInfo, ...] = (
    ProblemTypeInfo(
        "bad-request", 400, "Bad Request",
        "The request could not be understood: a malformed body, a missing or misspelt field, or a parameter of the wrong kind.",
        "Read the detail member, correct the request and send it again.",
    ),
    ProblemTypeInfo(
        "unauthenticated", 401, "Unauthenticated",
        "The request carries no valid credentials: no API token or session, or the token has expired or been revoked.",
        "Sign in, or send an Authorization: Bearer header with an API token from Account > API tokens.",
    ),
    ProblemTypeInfo(
        "forbidden", 403, "Forbidden",
        "The credentials are valid, but the account may not do this: it lacks the permission, or the token is read-only and the request changes something.",
        "Ask an administrator for the permission the detail member names, or use a token that is allowed to write.",
    ),
    ProblemTypeInfo(
        "not-found", 404, "Not Found",
        "Nothing is at that address or under that id. The path may be mistyped, the object may have been deleted, or you may not be allowed to know it exists.",
        "Check the path against the API reference (/api/docs) and check the id.",
    ),
    ProblemTypeInfo(
        "method-not-allowed", 405, "Method Not Allowed",
        "The path exists, but not for the HTTP method that was used.",
        "Look up the path in the API reference (/api/docs) and use a method it lists.",
    ),
    ProblemTypeInfo(
        "conflict", 409, "Conflict",
        "The request is well formed but clashes with the current state: a name that is already taken, an object that is in use, or a state that cannot change from where it is.",
        "Read the detail member, look at the current state of the object, and change the request or the state.",
    ),
    ProblemTypeInfo(
        "validation-failed", 422, "Validation Failed",
        "The request was understood, but a value in it is not acceptable.",
        "Correct the values the detail member lists and send the request again.",
    ),
    ProblemTypeInfo(
        "rate-limited", 429, "Rate Limited",
        "Too many requests were made in a short time.",
        "Wait a little and try again, with a longer pause between calls.",
    ),
    ProblemTypeInfo(
        "internal-server-error", 500, "Internal Server Error",
        "The service failed while handling a request that was valid. The failure is logged.",
        "Try once more. If it keeps happening, give an administrator the time of the request and its instance member.",
    ),
    ProblemTypeInfo(
        "service-unavailable", 503, "Service Unavailable",
        "The service, or something it depends on, cannot answer right now: for example while it starts or restarts, or while its database is unreachable.",
        "Wait and try again. The /readyz address says whether the service is ready.",
    ),
    ProblemTypeInfo(
        UNKNOWN_ERROR_SLUG, 0, "Error",
        "The response has a status that has no page of its own.",
        "Use the status and the detail member.",
    ),
)


def problem_type_info(*, slug: str) -> Optional[ProblemTypeInfo]:
    """
        The catalogue entry for ``slug``.

        :param slug: Last segment of a documented ``type``.

        :returns: The entry, or None when the slug is not documented.
    """
    for entry in PROBLEM_TYPES:
        if entry.slug == slug:
            return entry
    return None


def resolve_problem_type(problem_type: str) -> str:
    """
        Make a documented ``type`` reference absolute when the service
        knows its public address. Other types (an extension's own) and
        every type when no public base URL is configured are returned
        unchanged, as the service-relative reference.

        :param problem_type: The ``type`` a builder was given.

        :returns: The ``type`` to put on the wire.
    """
    if not problem_type.startswith(PROBLEM_TYPE_BASE_URL):
        return problem_type
    try:
        from ccai.pychestrate.webservice.public_endpoint import resolve_public_base_url  # noqa: E402
        base = resolve_public_base_url()
    except Exception:  # noqa: BLE001 -- an error response must never fail for want of a base URL
        base = None
    if base is None:
        return problem_type
    return base + problem_type


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
        problem_type=resolve_problem_type(problem_type),
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
        problem_type = PROBLEM_TYPE_BASE_URL + UNKNOWN_ERROR_SLUG
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
