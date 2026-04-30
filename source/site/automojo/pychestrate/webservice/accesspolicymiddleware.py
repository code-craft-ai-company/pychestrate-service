"""
.. module:: pychestrate.webservice.accesspolicymiddleware
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Webworks middleware that enforces per-endpoint AccessPolicy.

.. moduleauthor:: Automation Mojo LLC

The pychestrate REST surface declares its security constraints by
attaching :class:`automojo.webworks.security.accesspolicy.AccessPolicy`
instances to each endpoint via the ``access_policy=`` argument of
:meth:`RestBlueprint.attach_at`. The constraint lives at
``descriptor.constraints.access_policy``.

The :class:`PychestrateApplication` dispatcher attach-shim resolves
the matched descriptor and stashes it on
``request.endpoint_descriptor`` before the pipeline runs.
:class:`AccessPolicyMiddleware` reads that attribute and enforces:

* No descriptor or no policy attached → pass-through (every legacy
  endpoint stays public until it's gated explicitly).
* ``policy.require_auth`` is True and ``request.auth`` is None →
  HTTP 401.
* ``policy.roles`` is non-empty and the principal's role set has no
  intersection with the required roles → HTTP 403.
* ``policy.scopes`` is non-empty and the principal's permission set
  has no intersection with the required scopes → HTTP 403.

Otherwise the request continues down the pipeline.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from typing import Callable, Optional, Set

from automojo.webworks.routing.exceptions import HTTPException
from automojo.webworks.routing.request import Request
from automojo.webworks.routing.response import Response
from automojo.webworks.security.accesspolicy import AccessPolicy


class AccessPolicyMiddleware:
    """
        Pipeline middleware that enforces per-endpoint
        :class:`AccessPolicy` against the resolved
        ``request.auth`` from
        :class:`PychestrateSessionMiddleware`.
    """

    name: str = "access_policy"

    def __init__(self):
        """
            Construct an :class:`AccessPolicyMiddleware`. Stateless.
        """
        return

    def __call__(
            self,
            request: Request,
            call_next: Callable[[Request], Response],
        ) -> Response:
        """
            Enforce the access policy before delegating to the next
            handler in the pipeline.
        """
        descriptor = getattr(request, "endpoint_descriptor", None)
        policy = self._extract_policy(descriptor=descriptor)
        if policy is None:
            response = call_next(request)
            return response

        auth_context = getattr(request, "auth", None)

        if policy.require_auth is True:
            if auth_context is None:
                err_msg = "authentication required"
                raise HTTPException(status_code=401, detail=err_msg)

        principal_roles = self._principal_roles(auth_context=auth_context)
        if len(policy.roles) > 0:
            required = set(policy.roles)
            if len(required & principal_roles) == 0:
                err_lines = [
                    "Access denied — required role not granted.",
                    "REQUIRED: {0}".format(sorted(required)),
                    "GRANTED: {0}".format(sorted(principal_roles)),
                ]
                err_msg = os.linesep.join(err_lines)
                raise HTTPException(status_code=403, detail=err_msg)

        principal_permissions = self._principal_permissions(
            auth_context=auth_context,
        )
        if len(policy.scopes) > 0:
            required_scopes = set(policy.scopes)
            if len(required_scopes & principal_permissions) == 0:
                err_lines = [
                    "Access denied — required scope not granted.",
                    "REQUIRED: {0}".format(sorted(required_scopes)),
                    "GRANTED: {0}".format(sorted(principal_permissions)),
                ]
                err_msg = os.linesep.join(err_lines)
                raise HTTPException(status_code=403, detail=err_msg)

        response = call_next(request)
        return response

    def _extract_policy(self, *, descriptor) -> Optional[AccessPolicy]:
        """
            Pull the :class:`AccessPolicy` off the descriptor, or
            ``None`` when the endpoint is unprotected.
        """
        if descriptor is None:
            return None
        constraints = getattr(descriptor, "constraints", None)
        if constraints is None:
            return None
        rtnval = getattr(constraints, "access_policy", None)
        return rtnval

    def _principal_roles(self, *, auth_context) -> Set[str]:
        """
            Return the role set carried by ``request.auth.principal``,
            or an empty set when the request is anonymous.
        """
        if auth_context is None:
            return set()
        principal = getattr(auth_context, "principal", None)
        if principal is None:
            return set()
        roles_attr = getattr(principal, "roles", None)
        if roles_attr is None:
            return set()
        rtnval = set(roles_attr)
        return rtnval

    def _principal_permissions(self, *, auth_context) -> Set[str]:
        """
            Return the permission set carried by
            ``request.auth.principal``, or an empty set.
        """
        if auth_context is None:
            return set()
        principal = getattr(auth_context, "principal", None)
        if principal is None:
            return set()
        permissions_attr = getattr(principal, "permissions", None)
        if permissions_attr is None:
            return set()
        rtnval = set(permissions_attr)
        return rtnval
