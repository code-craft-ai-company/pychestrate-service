"""
.. module:: api.error_catalogue
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: ``GET /errors`` and ``GET /errors/{slug}`` -- the pages the
               ``type`` member of an error response points to (DOC-14).

.. moduleauthor:: Code Craft AI LLC

Every REST error is an RFC 7807 problem document whose ``type`` names its
kind (``/errors/not-found``). The ``type`` values used to name a site
nothing published, so a caller who followed one found nothing. The service
now serves a page for each documented type: what the problem is, and what
to do about it. The pages are public, because the response that leads to a
page is often a 401.

A browser gets HTML; a client that asks for ``application/json`` (and not
for HTML) gets the same entry as JSON.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import asdict
from typing import Any, Dict

from ccai.webworks.routing.request import Request
from ccai.webworks.routing.response import JSONResponse, Response

from ccai.pychestrate.webservice.api.problem_json import (
    PROBLEM_TYPE_BASE_URL,
    PROBLEM_TYPES,
    ProblemTypeInfo,
    problem_type_info,
)
from ccai.pychestrate.webservice.api.problem_json_webworks import problem_response_for_http_status
from ccai.pychestrate.webservice.webinterface.foundation.templating import render_template_response


#: Catalogue path (the base of every documented ``type``).
CATALOGUE_PATH: str = PROBLEM_TYPE_BASE_URL.rstrip("/")

INDEX_TEMPLATE: str = "site_shell/error_catalogue.html"
TYPE_TEMPLATE: str = "site_shell/error_type.html"


def _wants_json(*, request: Request) -> bool:
    """
        Whether the caller asked for JSON and not for HTML.

        :param request: The request.

        :returns: True for ``Accept: application/json`` without ``text/html``.
    """
    accept = str(request.headers.get("Accept", request.headers.get("accept", "")) or "").lower()
    return "application/json" in accept and "text/html" not in accept


def _entry_dict(*, entry: ProblemTypeInfo) -> Dict[str, Any]:
    """
        One catalogue entry as JSON-friendly data, with its address.
    """
    rtnval = asdict(entry)
    rtnval["type"] = PROBLEM_TYPE_BASE_URL + entry.slug
    return rtnval


def handle_error_index(request: Request) -> Response:
    """
        ``GET /errors``: every documented problem type.
    """
    entries = [_entry_dict(entry=entry) for entry in PROBLEM_TYPES]
    if _wants_json(request=request):
        return JSONResponse({"types": entries})
    return render_template_response(template_name=INDEX_TEMPLATE, context={"problem_types": entries})


def handle_error_type(request: Request) -> Response:
    """
        ``GET /errors/{slug}``: one documented problem type.
    """
    slug = str(request.path_params.get("slug", "") or "")
    entry = problem_type_info(slug=slug)
    if entry is None:
        if _wants_json(request=request):
            return problem_response_for_http_status(
                status=404, detail="There is no problem type '{}'.".format(slug), instance=request.path,
            )
        return render_template_response(
            template_name=INDEX_TEMPLATE,
            context={"problem_types": [_entry_dict(entry=item) for item in PROBLEM_TYPES], "unknown_slug": slug},
            status_code=404,
        )
    if _wants_json(request=request):
        return JSONResponse(_entry_dict(entry=entry))
    return render_template_response(template_name=TYPE_TEMPLATE, context={"problem_type": _entry_dict(entry=entry)})


def register_error_catalogue_routes(*, app: Any) -> None:
    """
        Attach the catalogue routes (no sign-in: an error's ``type`` must be
        readable by the caller that just failed to authenticate).

        :param app: WebWorks application.

        :returns: None.
    """
    app.attach_route(CATALOGUE_PATH, methods=["GET"])(handle_error_index)
    app.attach_route(CATALOGUE_PATH + "/{slug}", methods=["GET"])(handle_error_type)
    return


__all__ = [
    "CATALOGUE_PATH",
    "handle_error_index",
    "handle_error_type",
    "register_error_catalogue_routes",
]
