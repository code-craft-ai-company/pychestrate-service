"""
.. module:: project_templates.restapi.v1.templates_controller
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: REST API v1 controller for /api/v1/project-templates.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from flask_restx import Namespace, Resource, fields

from automojo.pychestrate.webservice.project_templates import service as template_service
from automojo.pychestrate.webservice.project_templates.exceptions import (
    TemplateNotRegisteredError,
)


PROJECT_TEMPLATES_NAMESPACE_PATH = "/project-templates"


templates_ns = Namespace(
    "Project Templates v1",
    description="Registered project templates (2-project-templates).",
)


template_summary_model = templates_ns.model(
    "ProjectTemplateSummary",
    {
        "template_id": fields.String(description="Template id"),
        "template_version": fields.String(description="Template version (SemVer)"),
        "display_name": fields.String(description="Human-facing name"),
        "description": fields.String(description="Description"),
        "variable_count": fields.Integer(description="Variable spec count"),
        "tag_count": fields.Integer(description="Tag spec count"),
        "notification_rule_count": fields.Integer(description="Notification rule count"),
        "recommended_roles": fields.List(fields.String, description="Recommended role names"),
    },
)


def _summary_to_dict(summary) -> dict:
    """
        Render a :class:`TemplateSummary` as the REST response dict.
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


@templates_ns.route("")
class TemplatesList(Resource):
    """
        Resource that exposes GET ``/api/v1/project-templates``.
    """

    @templates_ns.marshal_list_with(template_summary_model)
    def get(self):
        """
            List every registered template.
        """
        rows = template_service.list_templates()
        rtnval = [_summary_to_dict(row) for row in rows]
        return rtnval


@templates_ns.route("/<string:template_id>")
@templates_ns.param("template_id", "The template id")
class TemplateDetail(Resource):
    """
        Resource that exposes GET ``/api/v1/project-templates/{template_id}``.
    """

    @templates_ns.marshal_with(template_summary_model)
    def get(self, template_id: str):
        """
            Return a single template's summary.
        """
        try:
            summary = template_service.read_template(template_id=template_id)
        except TemplateNotRegisteredError as xcpt:
            templates_ns.abort(404, str(xcpt))

        rtnval = _summary_to_dict(summary)
        return rtnval


def publish_namespaces(version_prefix: str):
    """
        Return namespace registrations for v1 wiring.

        :param version_prefix: Version prefix.

        :returns: List of (namespace, path) tuples.
    """
    rtnval = [(templates_ns, version_prefix + PROJECT_TEMPLATES_NAMESPACE_PATH)]
    return rtnval
