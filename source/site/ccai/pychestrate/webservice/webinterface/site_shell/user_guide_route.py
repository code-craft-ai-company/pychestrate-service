"""
.. module:: webinterface.site_shell.user_guide_route
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Serve the built user guide from the service itself (DOC-20).

.. moduleauthor:: Code Craft AI LLC

The product is self-hosted, often behind a firewall, so a link to a site on
the internet is a link that may not open, and a guide published elsewhere can
describe a different release from the one that is running. The service
therefore serves the user guide it shipped with:

* ``make docs-into-service`` builds the Sphinx site (``make docs``) and copies
  it into ``static/docs`` beside the other static assets; the deploy script
  runs it before it syncs the tree.
* This module mounts that directory at ``/docs`` and answers ``/docs`` and
  ``/docs/`` with a redirect to the guide's first page.
* The shell shows a "User guide" link in the account menu only when the guide
  is installed (:func:`user_guide_url`), so the link never leads nowhere. A
  deployment without the built site simply has no ``/docs`` and no link.

The guide is public, like the API reference and the error pages: it describes
the product, not the deployment.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from typing import Any, Optional

from ccai.webworks.routing.request import Request
from ccai.webworks.routing.response import RedirectResponse, Response

from ccai.pychestrate.webservice.metadata import SITE_DIRECTORIES
from ccai.pychestrate.webservice.webinterface.foundation.static_files import register_static_routes


USER_GUIDE_URL_PREFIX: str = "/docs"
USER_GUIDE_INDEX_FILE: str = "index.html"


def user_guide_root() -> str:
    """
        Where the built user guide is installed: ``static/docs`` under the
        web interface.

        :returns: Absolute directory path (it may not exist).
    """
    rtnval = os.path.join(SITE_DIRECTORIES.DIR_STATIC, "docs")
    return rtnval


def user_guide_is_installed(*, docs_root: Optional[str] = None) -> bool:
    """
        Whether a built user guide is present.

        :param docs_root: Directory to look in (default: :func:`user_guide_root`).

        :returns: ``True`` when the guide's first page exists.
    """
    root = docs_root if docs_root is not None else user_guide_root()
    rtnval = os.path.isfile(os.path.join(root, USER_GUIDE_INDEX_FILE))
    return rtnval


def user_guide_url(*, docs_root: Optional[str] = None) -> str:
    """
        The address of the user guide for the shell's account menu.

        :param docs_root: Directory to look in (default: :func:`user_guide_root`).

        :returns: ``"/docs/"`` when the guide is installed, else ``""``.
    """
    if user_guide_is_installed(docs_root=docs_root) is False:
        return ""
    rtnval = USER_GUIDE_URL_PREFIX + "/"
    return rtnval


def register_user_guide_routes(*, app: Any, docs_root: Optional[str] = None) -> None:
    """
        Mount the user guide at ``/docs`` and send ``/docs`` and ``/docs/`` to
        its first page. Registered even when the guide is not installed, so
        an address someone bookmarked answers the site's own 404 instead of
        the shell.

        :param app: WebWorks application.
        :param docs_root: Directory holding the built site (default:
                          :func:`user_guide_root`).
    """
    root = docs_root if docs_root is not None else user_guide_root()

    def _redirect_to_first_page(request: Request) -> Response:
        if user_guide_is_installed(docs_root=root) is False:
            from ccai.pychestrate.webservice.webinterface.site_shell.error_pages import (  # noqa: E402
                render_error_response,
            )
            rtnval = render_error_response(
                request=request,
                status_code=404,
                title="The user guide is not installed",
                message=(
                    "This deployment was set up without the built user guide. "
                    "An administrator can install it with `make docs-into-service` "
                    "and a deploy."
                ),
            )
            return rtnval
        rtnval = RedirectResponse(
            url="{}/{}".format(USER_GUIDE_URL_PREFIX, USER_GUIDE_INDEX_FILE), status_code=302
        )
        return rtnval

    app.attach_route(USER_GUIDE_URL_PREFIX, methods=["GET"])(_redirect_to_first_page)
    app.attach_route(USER_GUIDE_URL_PREFIX + "/", methods=["GET"])(_redirect_to_first_page)
    register_static_routes(app=app, url_prefix=USER_GUIDE_URL_PREFIX, static_root=root)
    return


__all__ = [
    "USER_GUIDE_URL_PREFIX",
    "register_user_guide_routes",
    "user_guide_is_installed",
    "user_guide_root",
    "user_guide_url",
]
