"""
.. module:: webinterface.site_shell.shell_document
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Renders the host HTML page that mounts the
               ``<pyc-site-shell>`` Custom Element and imports the
               bundles registered for the request's route.

.. moduleauthor:: Automation Mojo LLC

The shell document is intentionally tiny. It carries:

* The ``<pyc-site-shell>`` Custom Element with its observed
  attributes initialized from the request.
* One ``<script type="module" src=".../dist/<name>.js">`` per
  bundle returned by :func:`bundles_for`.
* The compiled stylesheet (one ``<link>`` tag).

The Custom Element itself owns header, sidebar, main, and empty-
state rendering. Server-side this module is pure plumbing -- pick
the bundles, pick a page title, render the template, return the
``HTMLResponse``.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from typing import Any, Dict, Optional

from automojo.webworks.routing.response import HTMLResponse

from automojo.pychestrate.webservice.webinterface.foundation.templating import (
    render_template_response,
)

from automojo.pychestrate.webservice.webinterface.site_shell.bundle_registry import (
    bundles_for,
)


SHELL_TEMPLATE_NAME: str = "site_shell/shell_document.html"


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

    context: Dict[str, Any] = {
        "page_title": page_title,
        "initial_route": path if len(path) > 0 else "/",
        "bundle_names": bundle_names,
        "content_html": content_html if content_html is not None else "",
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
