"""
.. module:: api.rest_authz
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Route-level permission enforcement for REST handlers.

.. moduleauthor:: Code Craft AI LLC

Most REST route modules check permissions inside each handler. A
number of modules (projects writes, enrollment tokens, identity
users, audit, feature flags, notification channels, retention,
tags, variables) never did, so any caller -- including an anonymous
one -- could reach them. :func:`require_rest_permission` wraps a
handler at registration time, so the permission a route needs is
declared next to the route itself::

    app.attach_route(base, methods=["POST"])(
        require_rest_permission(handle_create_user, permission_key="system:users.write")
    )

The session middleware attaches ``auth_principal`` and
``db_session`` to every ``/api/v1/*`` request before the wrapper
runs (see :mod:`middleware_webworks`).
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import functools

from datetime import datetime, timezone
from typing import Any, Callable, Optional

from ccai.pychestrate.webservice.api.problem_json_webworks import (
    problem_response_for_http_status,
)


#: Use as ``permission_key`` for routes any signed-in principal may
#: call; the wrapper then only requires authentication.
AUTHENTICATED_ONLY: Optional[str] = None


def permission_denial(
        *,
        request: Any,
        permission_key: Optional[str]
    ) -> Optional[Any]:
    """
        Decide whether the caller may use a route.

        :param request: Webworks request carrying ``auth_principal``
                        and ``db_session`` from the session
                        middleware.
        :param permission_key: Canonical ``system:*`` key the route
                               requires, or :data:`AUTHENTICATED_ONLY`.

        :returns: ``None`` when the caller may proceed; otherwise the
                  RFC 7807 response to return (401 without a
                  principal, 403 without the permission, 503 when the
                  permission cannot be evaluated -- fail closed).
    """
    instance = getattr(request, "path", None)

    principal = getattr(request, "auth_principal", None)
    if principal is None:
        rtnval = problem_response_for_http_status(
            status=401,
            detail="Authentication required.",
            instance=instance,
        )
        return rtnval

    if permission_key is None:
        return None

    db_session = getattr(request, "db_session", None)
    if db_session is None:
        rtnval = problem_response_for_http_status(
            status=503,
            detail="Permission check unavailable.",
            instance=instance,
        )
        return rtnval

    from ccai.pychestrate.webservice.security.rbac import (  # noqa: E402
        rbac_evaluator,
    )
    try:
        decision = rbac_evaluator.check_permission(
            db_session=db_session,
            principal=principal,
            permission_key=permission_key,
            now=datetime.now(timezone.utc),
        )
        allowed = decision.allowed is True
    except Exception:
        allowed = False

    if allowed is False:
        rtnval = problem_response_for_http_status(
            status=403,
            detail="Permission denied: {}".format(permission_key),
            instance=instance,
            extensions={"required_permission": permission_key},
        )
        return rtnval

    return None


def require_rest_permission(
        handler: Callable[[Any], Any],
        *,
        permission_key: Optional[str]
    ) -> Callable[[Any], Any]:
    """
        Wrap a REST handler so it runs only for callers holding
        ``permission_key`` (or, with :data:`AUTHENTICATED_ONLY`, for
        any signed-in caller).

        :param handler: The route handler.
        :param permission_key: Required permission key, or
                               :data:`AUTHENTICATED_ONLY`.

        :returns: The wrapped handler.
    """

    @functools.wraps(handler)
    def _authorized_handler(request: Any) -> Any:
        denial = permission_denial(request=request, permission_key=permission_key)
        if denial is not None:
            return denial
        rtnval = handler(request)
        return rtnval

    _authorized_handler.required_permission = permission_key
    return _authorized_handler


__all__ = [
    "AUTHENTICATED_ONLY",
    "permission_denial",
    "require_rest_permission",
]
