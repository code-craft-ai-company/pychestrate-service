"""
.. module:: project_templates.restapi.v1.templates_routes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-native REST routes for /api/v1/project-templates.

.. moduleauthor:: Code Craft AI LLC

The production webservice runs on ``ccai.webworks`` (see
:mod:`app_pychestrate_main`). This module provides the
webworks-native ``templates`` controller.

Two routes:

* ``GET /api/v1/project-templates`` — list registered templates.
* ``GET /api/v1/project-templates/{template_id}`` — read one
  template's summary, 404 problem+json if not registered.

These endpoints are read-only views over the in-process template
registry — no SQLAlchemy session required. The session middleware
still attaches one because every ``/api/v1/`` path is in scope, but
the handlers do not consume it.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any

from ccai.webworks.routing.request import Request
from ccai.webworks.routing.response import JSONResponse, Response

from ccai.pychestrate.webservice.api.problem_json_webworks import (
    problem_response_for_http_status,
)
from ccai.pychestrate.webservice.project_templates import (
    service as template_service,
)
from ccai.pychestrate.webservice.project_templates.exceptions import (
    TemplateNotRegisteredError,
)


TEMPLATES_PATH = "/project-templates"


def _summary_to_dict(summary: Any) -> dict:
    """
        Render a :class:`TemplateSummary` as the REST response dict.

        :param summary: Template summary object from the service
                        layer.

        :returns: JSON-friendly dict.
    """
    rtnval = {
        "template_id": summary.template_id,
        "template_version": summary.template_version,
        "display_name": summary.display_name,
        "description": summary.description,
        "variable_count": summary.variable_count,
        "tag_count": summary.tag_count,
        "notification_rule_count": summary.notification_rule_count,
        "recommended_roles": list(summary.recommended_roles),
    }
    return rtnval


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def handle_list_templates(request: Request) -> Response:
    """
        ``GET /api/v1/project-templates`` — list registered template
        summaries.

        :param request: Incoming webworks request (unused).

        :returns: JSON response (200) carrying a list of template
                  summary dicts.
    """
    rows = template_service.list_templates()
    body = [_summary_to_dict(row) for row in rows]
    rtnval = JSONResponse(content=body, status_code=200)
    return rtnval


def handle_read_template(request: Request) -> Response:
    """
        ``GET /api/v1/project-templates/{template_id}`` — read one
        template's summary. Returns 404 problem+json with the
        template id as an extension member when the template is not
        registered.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with the summary dict, or
                  problem response (404).
    """
    template_id = request.path_params.get("template_id", "")

    try:
        summary = template_service.read_template(template_id=template_id)
    except TemplateNotRegisteredError as xcpt:
        rtnval: Response = problem_response_for_http_status(
            status=404,
            detail=str(xcpt),
            instance=request.path,
            extensions={"template_id": template_id},
        )
        return rtnval

    body = _summary_to_dict(summary)
    rtnval = JSONResponse(content=body, status_code=200)
    return rtnval


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_templates_routes(*, app: Any, version_prefix: str) -> None:
    """
        Attach the project-templates routes to a webworks
        application.

        :param app: WebWorks application built by
                    ``establish_webapp_persona``.
        :param version_prefix: Versioned API prefix (e.g.
                               ``"/api/v1"``).

        :returns: None.
    """
    base = version_prefix + TEMPLATES_PATH
    app.attach_route(base, methods=["GET"])(handle_list_templates)
    app.attach_route(
        base + "/{template_id}", methods=["GET"]
    )(handle_read_template)
    return


__all__ = [
    "TEMPLATES_PATH",
    "register_templates_routes",
    "handle_list_templates",
    "handle_read_template",
]
