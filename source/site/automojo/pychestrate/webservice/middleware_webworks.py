"""
.. module:: pychestrate.webservice.middleware_webworks
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: pychestrate-specific webworks middleware components.

.. moduleauthor:: Automation Mojo LLC

This module ships the request-scoped database session middleware that
replaces the Flask ``g.db_session`` pattern. It is the second half of the
P24a worked example (paired with the migrated ``auth_controller``).

Webworks ``MiddlewareContext`` is sealed (only ``endpoint_descriptor``,
``scope``, ``config``, ``logger`` properties), so request-scoped state
attaches directly to the :class:`Request` instance — verified by
``Request.__init__`` not declaring ``__slots__``. Handlers consume the
session via ``request.db_session``.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from typing import Callable, Optional

from sqlalchemy.orm import Session as DbSession

from automojo.webworks.routing.request import Request
from automojo.webworks.routing.response import Response


SessionFactory = Callable[[], DbSession]


def get_request_db_session(*, request: Request) -> Optional[DbSession]:
    """
        Return the request-scoped SQLAlchemy session attached by
        :class:`DbSessionMiddleware`, or ``None`` when the middleware
        was not installed in the pipeline.

        :param request: The incoming :class:`Request`.

        :returns: The request-scoped ``DbSession``, or ``None``.
    """
    rtnval = getattr(request, "db_session", None)
    return rtnval


def get_request_actor_user_id(*, request: Request) -> Optional[str]:
    """
        Return the acting principal's user id derived from the
        :class:`AuthenticationContext` attached by
        :class:`PychestrateSessionMiddleware`, or ``None`` when the
        request is anonymous.

        Replaces the legacy Flask ``g.actor_user_id`` lookup.

        :param request: The incoming :class:`Request`.

        :returns: The acting user id string, or ``None``.
    """
    auth_context = getattr(request, "auth", None)
    if auth_context is None:
        return None
    principal = getattr(auth_context, "principal", None)
    if principal is None:
        return None
    rtnval = principal.identifier
    return rtnval


class DbSessionMiddleware:
    """
        Webworks middleware that opens a request-scoped SQLAlchemy
        session, attaches it to the :class:`Request` as ``db_session``,
        and closes it after the downstream handler returns.

        :param session_factory: Zero-argument callable returning a fresh
                                ``DbSession``. The middleware owns the
                                lifecycle and always calls ``close()`` on
                                the resulting session.
    """

    name: str = "db_session"

    def __init__(self, *, session_factory: SessionFactory):
        """
            Construct a :class:`DbSessionMiddleware`.

            :param session_factory: Callable returning a fresh
                                    ``DbSession`` for the request.

            :raises ValueError: If ``session_factory`` is None.
        """
        if session_factory is None:
            err_lines = [
                "DbSessionMiddleware requires a session_factory.",
            ]
            err_msg = os.linesep.join(err_lines)
            raise ValueError(err_msg) from None
        self._session_factory: SessionFactory = session_factory
        return

    @property
    def session_factory(self) -> SessionFactory:
        """
            The configured session factory.

            :returns: The zero-argument callable returning a fresh
                      ``DbSession``.
        """
        rtnval = self._session_factory
        return rtnval

    def __call__(
        self,
        request: Request,
        call_next: Callable[[Request], Response],
    ) -> Response:
        """
            Open a request-scoped ``db_session``, attach it to
            ``request``, dispatch the next handler, and close the
            session in a ``finally`` block.

            :param request: The incoming :class:`Request`.
            :param call_next: The next callable in the pipeline.

            :returns: The :class:`Response` returned by the downstream
                      handler.
        """
        db_session = self._session_factory()
        request.db_session = db_session
        try:
            response = call_next(request)
        finally:
            db_session.close()
        rtnval = response
        return rtnval
