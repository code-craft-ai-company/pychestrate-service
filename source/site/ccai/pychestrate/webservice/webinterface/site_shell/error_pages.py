"""
.. module:: webinterface.site_shell.error_pages
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: One error-page experience for the consumer web UI.

.. moduleauthor:: Code Craft AI LLC

Before the UI remediation the service carried three different
"not found" renderings (a hand-rolled light-only chromeless page in
the catch-all, an unstyled body in the setup blueprint, and six
dead ``errors/*.html`` templates under the projects and resources
blueprints that no route ever rendered). This module replaces all
of them with :func:`render_error_response`:

* an authenticated browser on a shell path gets the
  ``site_shell/error_page.html`` fragment rendered inside the site
  shell, so the header and sidebar stay put;
* everyone else gets ``site_shell/chromeless_error.html``, a
  token-driven standalone page.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Dict, Optional, Tuple

from ccai.webworks.routing.response import HTMLResponse, Response

from ccai.pychestrate.webservice.webinterface.foundation.templating import (
    render_template_response,
    render_template_to_string,
)


ERROR_FRAGMENT_TEMPLATE: str = "site_shell/error_page.html"
CHROMELESS_ERROR_TEMPLATE: str = "site_shell/chromeless_error.html"

DEFAULT_TITLES: Dict[int, str] = {
    403: "You do not have access to this page",
    404: "Page not found",
    500: "Something went wrong",
}

DEFAULT_MESSAGES: Dict[int, str] = {
    403: "Your account does not have permission to view this page. Ask an administrator if you need access.",
    404: "The address may be mistyped, or the page may have moved.",
    500: "The server hit an unexpected problem while handling the request. Try again, and contact an administrator if it keeps happening.",
}


def _request_is_authenticated(*, request: Any) -> bool:
    """
        Reuse the catch-all's cookie + session-row check. Imported
        lazily to avoid an import cycle (the catch-all imports this
        module).
    """
    try:
        from ccai.pychestrate.webservice.webinterface.site_shell.catchall_route import (  # noqa: E402
            _is_request_authenticated,
        )
        rtnval = _is_request_authenticated(request=request)
    except Exception:
        rtnval = False
    return rtnval


def _same_origin_referer(*, request: Any) -> Optional[str]:
    """
        Return the request's ``Referer`` when it is a same-origin
        path, so the error page can offer a "Go back" link.
    """
    try:
        referer = request.headers.get("Referer", None)
    except Exception:
        referer = None
    if referer is None or len(str(referer)) == 0:
        return None
    referer = str(referer)
    if referer.startswith("/") and referer.startswith("//") is False:
        return referer
    try:
        host = request.headers.get("Host", None)
    except Exception:
        host = None
    if host is not None and ("://" + str(host) + "/") in referer:
        rtnval = referer.split(str(host), 1)[1]
        return rtnval
    return None


def render_error_response(
        *,
        request: Any,
        status_code: int,
        title: Optional[str] = None,
        message: Optional[str] = None,
        force_chromeless: bool = False,
        back_link: Optional[Tuple[str, str]] = None
    ) -> Response:
    """
        Render the error page for ``status_code``.

        :param request: Incoming webworks request (drives the
                        authenticated / anonymous decision and the
                        shell's bundle selection).
        :param status_code: HTTP status to emit (403 / 404 / 500).
        :param title: Optional heading override.
        :param message: Optional body text override.
        :param force_chromeless: Render the standalone page even for
                                 an authenticated browser (used when
                                 the shell itself cannot be trusted,
                                 e.g. a templating failure).
        :param back_link: Optional ``(label, url)`` for a link back to the
                          list the missing page belongs to; it replaces
                          the referer-based "Go back" link.

        :returns: :class:`Response` carrying the page with the
                  requested status code.
    """
    resolved_title = title if title is not None else DEFAULT_TITLES.get(status_code, "Error")
    resolved_message = message if message is not None else DEFAULT_MESSAGES.get(
        status_code, "The request could not be completed."
    )
    context: Dict[str, Any] = {
        "status_code": status_code,
        "title": resolved_title,
        "message": resolved_message,
        "back_url": _same_origin_referer(request=request),
        "back_link": back_link,
    }

    if force_chromeless is False and _request_is_authenticated(request=request) is True:
        from ccai.pychestrate.webservice.webinterface.site_shell.shell_document import (  # noqa: E402
            render_shell_document,
        )
        fragment_html = render_template_to_string(
            template_name=ERROR_FRAGMENT_TEMPLATE, context=context
        )
        rtnval = render_shell_document(
            request=request,
            page_title="{} · Pychestrate".format(resolved_title),
            content_html=fragment_html,
        )
        try:
            rtnval._status_code = status_code
        except AttributeError:
            pass
        return rtnval

    rtnval = render_template_response(
        template_name=CHROMELESS_ERROR_TEMPLATE,
        context=context,
        status_code=status_code,
    )
    return rtnval


__all__ = [
    "render_error_response",
    "ERROR_FRAGMENT_TEMPLATE",
    "CHROMELESS_ERROR_TEMPLATE",
]
