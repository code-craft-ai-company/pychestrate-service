"""
.. module:: project_templates.restapi.v1.projecttemplatesblueprint
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: REST API v1 controller for /api/v1/project-templates.

.. moduleauthor:: Automation Mojo LLC

Migrated from Flask + flask-restx to automojo-webworks.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Dict

from automojo.webworks.endpoints.doc import Doc
from automojo.webworks.endpoints.restblueprint import RestBlueprint
from automojo.webworks.routing.exceptions import HTTPException
from automojo.webworks.routing.request import Request
from automojo.webworks.routing.response import JSONResponse

from automojo.pychestrate.webservice.project_templates import (
    service as template_service,
)
from automojo.pychestrate.webservice.project_templates.exceptions import (
    TemplateNotRegisteredError,
)


PROJECT_TEMPLATES_BASE_PATH = "/api/v1/project-templates"


def _summary_to_dict(summary) -> Dict[str, Any]:
    """
        Render a template summary as the REST response dict.
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


class ProjectTemplatesBlueprint(RestBlueprint):
    """
        Blueprint grouping the v1 ``/api/v1/project-templates`` endpoints.
    """

    base_path = PROJECT_TEMPLATES_BASE_PATH
    tags = ["project-templates", "v1"]

    @RestBlueprint.attach_at(
        path="/api/v1/project-templates",
        methods=["GET"],
        doc=Doc(
            summary="List project templates",
            description="Return every registered project template summary.",
        ),
    )
    def list_templates(request: Request) -> JSONResponse:
        """
            List every registered template.
        """
        rows = template_service.list_templates()
        body = [_summary_to_dict(summary=row) for row in rows]
        rtnval = JSONResponse(content=body, status_code=200)
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/project-templates/{template_id}",
        methods=["GET"],
        doc=Doc(
            summary="Read project template",
            description="Return one template's summary by id.",
        ),
    )
    def read_template(request: Request) -> JSONResponse:
        """
            Read a single template summary.
        """
        template_id = request.path_params.get("template_id", "")
        try:
            summary = template_service.read_template(
                template_id=template_id,
            )
        except TemplateNotRegisteredError as exc:
            raise HTTPException(
                status_code=404, detail=str(exc),
            ) from exc

        body = _summary_to_dict(summary=summary)
        rtnval = JSONResponse(content=body, status_code=200)
        return rtnval
