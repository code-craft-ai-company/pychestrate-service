"""
.. module:: security.auth.anonymous_access
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The explicit list of REST routes that may be reached
               without a signed-in principal.

.. moduleauthor:: Code Craft AI LLC

Every ``/api/v1/*`` request that carries no session principal is
refused with a 401 by :class:`middleware_webworks.PychestrateSessionMiddleware`
unless the route appears in :data:`ANONYMOUS_ROUTE_ALLOWLIST`. The
default is deny: a new route is authenticated unless someone adds it
here, with the reason, on purpose.

Routes land on the list for one of two reasons:

* **The caller has no session by design** and the handler
  authenticates it another way -- a pod presenting its client
  certificate, a signed upload URL, an HMAC-signed webhook, or a
  one-time enrollment token. These handlers keep doing their own
  checks; the list only lets the request reach them.
* **The route is harmless without a principal** -- the UI metrics
  beacon validates its payload and stores nothing.

Before this list existed, individual handlers decided whether to
require a principal, and 52 of 217 REST routes ran without one,
including project create/update/delete, enrollment-token minting,
feature-flag writes, and the audit log.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import re

from dataclasses import dataclass
from typing import Pattern, Tuple


#: Prefix the anonymous-access policy governs. Paths outside it (the
#: server-rendered UI, static assets, the MCP endpoint) are not
#: affected by this module.
GOVERNED_PATH_PREFIX: str = "/api/v1/"


@dataclass(frozen=True)
class AnonymousRoute:
    """
        One route that may be reached without a session principal.

        :ivar method: Upper-case HTTP method.
        :ivar pattern: Compiled full-path regular expression.
        :ivar reason: Why the route is exempt, for reviewers.
    """
    method: str
    pattern: Pattern
    reason: str


def _route(method: str, path_regex: str, reason: str) -> AnonymousRoute:
    """
        Build an :class:`AnonymousRoute` from a path regex.

        :param method: HTTP method.
        :param path_regex: Regular expression matched against the
                           full request path.
        :param reason: Why the route is exempt.

        :returns: The route entry.
    """
    rtnval = AnonymousRoute(
        method=method.upper(),
        pattern=re.compile(path_regex),
        reason=reason,
    )
    return rtnval


_POD_MTLS = "pod client; the handler requires the client certificate identity"

ANONYMOUS_ROUTE_ALLOWLIST: Tuple[AnonymousRoute, ...] = (
    # Credentials other than a session.
    _route("POST", r"^/api/v1/enrollment-tokens/redeem$",
           "the one-time enrollment token in the body is the credential"),
    _route("POST", r"^/api/v1/webhooks/in/[^/]+/[^/]+$",
           "the receiver verifies the provider's HMAC signature"),
    _route("PUT", r"^/api/v1/runs/[^/]+/artifacts/_local-upload$",
           "the presigned upload URL carries an HMAC signature the handler verifies"),
    _route("GET", r"^/api/v1/runs/[^/]+/artifacts/.+$",
           "the handler accepts a session, a pod certificate, or a presigned URL"),
    _route("GET", r"^/api/v1/envelope-signing-keys$",
           "the handler accepts a session or a pod certificate"),
    _route("GET", r"^/api/v1/envelope-signing-keys/jwks\.json$",
           "the handler accepts a session or a pod certificate"),
    # Pod (client) machine plane.
    _route("GET", r"^/api/v1/clients/[^/]+/heartbeat$", _POD_MTLS),
    _route("GET", r"^/api/v1/clients/[^/]+/dispatches:next$", _POD_MTLS),
    _route("PUT", r"^/api/v1/clients/[^/]+/capabilities$", _POD_MTLS),
    _route("POST", r"^/api/v1/runs/[^/]+/dispatch-ack$", _POD_MTLS),
    _route("POST", r"^/api/v1/runs/[^/]+/progress$", _POD_MTLS),
    _route("POST", r"^/api/v1/runs/[^/]+/results/complete$", _POD_MTLS),
    _route("POST", r"^/api/v1/runs/[^/]+/artifacts:presign$", _POD_MTLS),
    # Harmless without a principal.
    _route("POST", r"^/api/v1/_metrics/ui$",
           "UI metrics beacon: validates the payload, logs a summary, stores nothing"),
)


def is_anonymous_request_permitted(method: str, path: str) -> bool:
    """
        Decide whether a request without a session principal may
        reach its handler.

        :param method: HTTP method of the request.
        :param path: Request path (no query string).

        :returns: ``True`` when the path is outside
                  :data:`GOVERNED_PATH_PREFIX` or the route is on
                  :data:`ANONYMOUS_ROUTE_ALLOWLIST`; ``False`` when
                  the request must be refused with a 401.
    """
    if path.startswith(GOVERNED_PATH_PREFIX) is False:
        return True

    upper_method = str(method).upper()
    for route in ANONYMOUS_ROUTE_ALLOWLIST:
        if route.method != upper_method:
            continue
        if route.pattern.match(path) is not None:
            return True

    rtnval = False
    return rtnval


__all__ = [
    "ANONYMOUS_ROUTE_ALLOWLIST",
    "AnonymousRoute",
    "GOVERNED_PATH_PREFIX",
    "is_anonymous_request_permitted",
]
