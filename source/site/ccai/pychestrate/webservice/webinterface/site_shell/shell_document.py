"""
.. module:: webinterface.site_shell.shell_document
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Renders the host HTML page that mounts the
               ``<pyc-site-shell>`` Custom Element and imports the
               bundles registered for the request's route.

.. moduleauthor:: Code Craft AI LLC

The shell document is intentionally tiny. It carries:

* The ``<pyc-site-shell>`` Custom Element with its observed
  attributes initialized from the request.
* One ``<script type="module" src=".../<name>/index.js">`` per
  bundle returned by :func:`bundles_for`.
* The stylesheet ``<link>`` tags: the mj token/base sheets, the
  ``--pyc-*`` design-token pack, and the shell stylesheet.

The Custom Element itself owns header, sidebar, main, and empty-
state rendering. Server-side this module is pure plumbing -- pick
the bundles, pick a page title, render the template, return the
``HTMLResponse``.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from typing import List, Any, Dict, Optional

from ccai.webworks.routing.response import HTMLResponse

from ccai.pychestrate.webservice.webinterface.foundation.templating import (
    render_template_response,
)

from ccai.pychestrate.webservice.webinterface.site_shell.bundle_registry import (
    bundles_for,
)


SHELL_TEMPLATE_NAME: str = "site_shell/shell_document.html"


def _read_shell_session(*, request: Any) -> Dict[str, Any]:
    """
        Decode the signed UI session cookie so the shell document can
        carry the signed-in username and the CSRF token (the sign-out
        control POSTs with it). Any failure yields an empty view: the
        shell then renders the anonymous placeholders.

        :param request: Incoming webworks request.

        :returns: Dict with optional ``username`` / ``csrf_token``.
    """
    rtnval: Dict[str, Any] = {}
    if request is None:
        return rtnval
    try:
        from ccai.pychestrate.webservice.metadata import (  # noqa: E402
            SITE_SHARED_GLOBALS,
        )
        from ccai.pychestrate.webservice.webinterface.foundation import (  # noqa: E402
            cookie_session,
        )
        secret = SITE_SHARED_GLOBALS.UI_COOKIE_SECRET
        if secret is None or len(secret) < 32:
            return rtnval
        session = cookie_session.read_session_from_request(
            request=request, secret=secret
        )
        if isinstance(session, dict) is False:
            return rtnval
        username = session.get("username", "")
        if isinstance(username, str) and len(username) > 0:
            rtnval["username"] = username
        csrf_token = session.get("csrf_token", "")
        if isinstance(csrf_token, str) and len(csrf_token) > 0:
            rtnval["csrf_token"] = csrf_token
    except Exception:
        return {}
    return rtnval


def _bundle_stylesheets_for(*, bundle_names: List[str]) -> List[str]:
    """
        The subset of ``bundle_names`` that ship a
        ``<bundle>/<bundle>.css`` next to their module. The shell
        document links these in ``<head>`` so a bundle's first paint
        is styled; the bundles' own runtime injectors see the link
        (``data-pyc-bundle``) and skip.

        :param bundle_names: Bundles selected for the page.

        :returns: Bundle names with a stylesheet on disk.
    """
    rtnval: List[str] = []
    try:
        from ccai.pychestrate.webservice.metadata import (  # noqa: E402
            SITE_DIRECTORIES,
        )
        static_root = SITE_DIRECTORIES.DIR_STATIC
    except Exception:
        return rtnval
    for bundle_name in bundle_names:
        candidate = os.path.join(static_root, "javascript", bundle_name, bundle_name + ".css")
        if os.path.isfile(candidate):
            rtnval.append(bundle_name)
    return rtnval


def render_shell_document(
        *,
        request: Any,
        page_title: str = "Pychestrate",
        content_html: Optional[str] = None,
        bundle_name: Optional[str] = None
    ) -> HTMLResponse:
    """
        Render the shell HTML for the supplied request and return
        an :class:`HTMLResponse`.

        :param request: Incoming webworks request -- the request's
                        ``path`` drives the bundle selection.
        :param page_title: ``<title>`` text. Defaults to
                           ``"Pychestrate"``; per-page handlers
                           override.
        :param content_html: Optional pre-rendered content slot.
                             For M1 this is typically ``None`` --
                             the shell renders an empty state
                             until PR4 wires per-route bundles.
        :param bundle_name: Optional extra bundle to include for
                            this render call. Stacks on top of
                            whatever :func:`bundles_for` returns
                            for the request path.

        :returns: :class:`HTMLResponse` carrying the shell HTML.
    """
    path = ""
    if request is not None:
        candidate = getattr(request, "path", None)
        if isinstance(candidate, str) is True:
            path = candidate

    bundle_names = bundles_for(path=path)
    if bundle_name is not None and len(bundle_name) > 0:
        if bundle_name not in bundle_names:
            bundle_names = list(bundle_names) + [bundle_name]

    session_view = _read_shell_session(request=request)
    context: Dict[str, Any] = {
        "page_title": page_title,
        "initial_route": path if len(path) > 0 else "/",
        "bundle_names": bundle_names,
        "bundle_stylesheets": _bundle_stylesheets_for(bundle_names=bundle_names),
        "content_html": content_html if content_html is not None else "",
        "csrf_token": session_view.get("csrf_token", ""),
        "user_display_name": session_view.get("username", ""),
    }
    rtnval = render_template_response(
        template_name=SHELL_TEMPLATE_NAME,
        context=context,
    )
    return rtnval


def get_shell_template_search_path() -> str:
    """
        Return the absolute filesystem path of the site-shell
        template directory so the bootstrap can wire it into the
        jinja environment's loader chain.

        :returns: Absolute path to the template directory.
    """
    here = os.path.dirname(__file__)
    rtnval = os.path.join(here, "templates")
    return rtnval


__all__ = [
    "render_shell_document",
    "get_shell_template_search_path",
    "SHELL_TEMPLATE_NAME",
]
