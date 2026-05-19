"""
.. module:: webinterface.site_shell.catchall_route
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Attaches the catch-all webworks handler that serves
               the shell document for every non-chromeless,
               non-API, non-static GET.

.. moduleauthor:: Automation Mojo LLC

The catch-all is registered LAST so explicit blueprint routes
(e.g. ``/admin/users`` from PR #200) win the dispatcher match.
For any path that no other handler claims, this module's handler
renders :func:`render_shell_document`.

Why not register a catch-all at ``/{path:path}`` and let webworks
priority-match? Because webworks' router uses
explicit-route-wins semantics, but our concern in M1 is to not
shadow the existing config / projects / resources blueprints
that already render their own templates. We accomplish this by
registering only after every other blueprint -- webworks
considers earlier registrations first.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import logging

from typing import Any

from automojo.webworks.routing.request import Request
from automojo.webworks.routing.response import Response

from automojo.pychestrate.webservice.webinterface.site_shell.chromeless_routes import (
    is_shell_candidate,
)
from automojo.pychestrate.webservice.webinterface.site_shell.shell_document import (
    render_shell_document,
)


_module_logger = logging.getLogger(__name__)


CATCHALL_ROOT_PATTERN: str = "/"
CATCHALL_PATH_PATTERN: str = "/{shell_path:path}"


def register_shell_catchall(*, app: Any) -> None:
    """
        Attach the catch-all shell-document handler to the
        supplied webworks application.

        Call this AFTER every other route registration so explicit
        blueprint routes (``/admin/users``, ``/projects/...``,
        ``/login``, ``/api/...``) match first. Webworks gives the
        first-registered route priority on collision; the catch-
        all is a fallback.

        Two handlers register:

        * ``GET /`` -- the root document.
        * ``GET /{shell_path:path}`` -- everything else not
          claimed by a more specific route.

        Both return the same shell document; the JS-side router
        decides what to render once the shell mounts.

        :param app: WebWorks application built by
                    ``establish_webapp_persona``.

        :returns: None.
    """
    def _shell_root_handler(request: Request) -> Response:
        rtnval = _serve_shell_or_pass(request=request)
        return rtnval

    def _shell_catchall_handler(request: Request) -> Response:
        rtnval = _serve_shell_or_pass(request=request)
        return rtnval

    app.attach_route(CATCHALL_ROOT_PATTERN, methods=["GET"])(
        _shell_root_handler,
    )
    app.attach_route(CATCHALL_PATH_PATTERN, methods=["GET"])(
        _shell_catchall_handler,
    )
    return


def _serve_shell_or_pass(*, request: Request) -> Response:
    """
        Decide whether the request path should render the shell.
        For non-shell candidates return a 404 so the dispatcher
        does not surface a half-rendered shell on API / static /
        chromeless paths. (In practice, those paths are claimed by
        their own handlers and never reach the catch-all.)

        :param request: Incoming webworks request.

        :returns: :class:`Response` carrying either the rendered
                  shell document or a 404.
    """
    path = getattr(request, "path", "")
    if isinstance(path, str) is False:
        path = ""
    if is_shell_candidate(path=path) is False:
        rtnval = Response(status_code=404, body=b"")
        return rtnval
    rtnval = render_shell_document(request=request)
    return rtnval


__all__ = [
    "register_shell_catchall",
    "CATCHALL_ROOT_PATTERN",
    "CATCHALL_PATH_PATTERN",
]
