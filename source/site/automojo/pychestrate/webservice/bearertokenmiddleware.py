"""
.. module:: pychestrate.webservice.bearertokenmiddleware
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Webworks middleware that resolves Bearer tokens to client identities.

.. moduleauthor:: Automation Mojo LLC

The :class:`BearerTokenMiddleware` complements
:class:`PychestrateSessionMiddleware` (cookies) by providing a second
authentication path keyed on the ``Authorization: Bearer <token>``
header. When an agent that successfully redeemed an enrollment token
calls back into the service, this middleware hashes the submitted
bearer using the same HMAC-SHA256 + pepper recipe the redeem flow
uses and looks up the matching :class:`Client` row.

Order in the pipeline matters: this middleware runs **after**
:class:`PychestrateSessionMiddleware` so cookie callers (which set
``request.auth`` first) win over any Authorization header. The bearer
path only fires when ``request.auth is None`` — i.e. there's no
cookie or the cookie didn't resolve.

Authenticated agents land with an :class:`AuthenticationContext`
carrying a :class:`Principal` whose:

* ``identifier`` is the client's UUID (string);
* ``display_name`` is ``"agent:<pod_name>"``;
* ``roles`` is ``{"agent"}`` (so ``AccessPolicy(roles=("agent",))``
  can gate agent-only endpoints);
* ``attributes`` carry ``client_id`` / ``pod_name`` / ``project_id``
  / ``status`` / ``liveness_state`` for downstream use.

The middleware never raises 401 itself; an absent or unrecognized
bearer leaves ``request.auth`` as ``None`` so
:class:`AccessPolicyMiddleware` can apply the per-endpoint gate
uniformly.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Callable, Optional

from automojo.errors.exceptions import ConfigurationError

from automojo.webworks.authentication.core import (
    AuthenticationContext,
    Principal,
)
from automojo.webworks.routing.request import Request
from automojo.webworks.routing.response import Response

from automojo.pychestrate.webservice.clients.enrollment.factories.stdlib_token_issuer import (
    StdlibHmacTokenIssuer,
    _digest,
)
from automojo.pychestrate.webservice.clients.models import Client


BEARER_SCHEME = "bearer-client"
BEARER_AGENT_ROLE = "agent"


class BearerTokenMiddleware:
    """
        Resolve ``Authorization: Bearer <token>`` headers to a
        :class:`Client` identity and attach an
        :class:`AuthenticationContext` to ``request.auth``.

        Cooperates with :class:`PychestrateSessionMiddleware`: only
        runs when no prior middleware has set ``request.auth``. That
        way callers carrying both a cookie and a bearer header keep
        the cookie identity (the human-side seat) and bearer-only
        callers get the agent identity.

        The middleware queries the ``clients`` table directly via
        the request-scoped ``db_session`` populated by
        :class:`DbSessionMiddleware`. When the db_session is not
        attached, the middleware passes through silently (the
        underlying handler will raise 503 anyway).
    """

    name: str = "bearer_token"

    def __init__(self):
        return

    def __call__(
            self,
            request: Request,
            call_next: Callable[[Request], Response],
        ) -> Response:
        existing = getattr(request, "auth", None)
        if existing is not None:
            response = call_next(request)
            return response

        token = self._extract_bearer_token(request=request)
        if token is None:
            response = call_next(request)
            return response

        db_session = getattr(request, "db_session", None)
        if db_session is None:
            response = call_next(request)
            return response

        client = self._lookup_client(
            db_session=db_session, token=token,
        )
        if client is not None:
            request.auth = self._build_context(client=client)
        response = call_next(request)
        return response

    def _extract_bearer_token(
            self, *, request: Request,
        ) -> Optional[str]:
        """
            Pull the bearer token out of the Authorization header.
        """
        header = request.get_header("Authorization", default=None)
        if header is None:
            return None
        stripped = header.strip()
        if len(stripped) == 0:
            return None
        # Header format: "Bearer <token>". We accept any case for
        # the scheme prefix.
        parts = stripped.split(None, 1)
        if len(parts) != 2:
            return None
        scheme = parts[0].lower()
        if scheme != "bearer":
            return None
        token = parts[1].strip()
        if len(token) == 0:
            return None
        return token

    def _lookup_client(
            self, *, db_session, token: str,
        ) -> Optional[Client]:
        """
            Hash the token via the same HMAC-SHA256 + pepper recipe
            the redeem flow uses and look up the matching row.

            Returns ``None`` when no match (so anonymous handling
            applies). Returns ``None`` also when the pepper is not
            installed — bearer auth is silently disabled in that
            case rather than 500-ing.
        """
        try:
            candidate = _digest(secret=token)
        except ConfigurationError:
            return None
        row = (
            db_session.query(Client)
            .filter(Client.bearer_token_hash == candidate)
            .first()
        )
        return row

    def _build_context(
            self, *, client: Client,
        ) -> AuthenticationContext:
        """
            Build the :class:`AuthenticationContext` that downstream
            middleware + handlers consume.
        """
        attributes = {
            "client_id": str(client.client_id),
            "pod_name": client.pod_name,
            "project_id": str(client.project_id),
        }
        if client.status is not None:
            attributes["status"] = client.status.value
        if client.liveness_state is not None:
            attributes["liveness_state"] = client.liveness_state.value
        principal = Principal(
            identifier=str(client.client_id),
            display_name="agent:{0}".format(client.pod_name),
            roles={BEARER_AGENT_ROLE},
            permissions=set(),
            attributes=attributes,
        )
        rtnval = AuthenticationContext(
            principal=principal,
            scheme=BEARER_SCHEME,
            attributes=attributes,
        )
        return rtnval
