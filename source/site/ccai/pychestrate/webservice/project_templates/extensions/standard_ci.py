"""
.. module:: project_templates.extensions.standard_ci
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Reference StandardCi + Compliance project templates.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import ClassVar, Tuple

from ccai.pychestrate.webservice.project_templates.extensions.template import (
    ProjectTemplateExtension,
    TemplateNotificationRuleSpec,
    TemplateTagSpec,
    TemplateVariableSpec,
)


class StandardCiTemplate(ProjectTemplateExtension):
    """
        Reference template that seeds a project for standard CI usage.
    """

    resource_extension_name: ClassVar[str] = "project_template"
    template_id: ClassVar[str] = "standard_ci"
    template_version: ClassVar[str] = "1.0.0"
    display_name: ClassVar[str] = "Standard CI Project"
    description: ClassVar[str] = "Typical continuous-integration project defaults."

    variables: ClassVar[Tuple[TemplateVariableSpec, ...]] = (
        TemplateVariableSpec(
            name="default_branch",
            value_type="STRING",
            default_value="main",
            description="Git branch treated as the release baseline.",
        ),
        TemplateVariableSpec(
            name="build_concurrency",
            value_type="INTEGER",
            default_value=4,
            description="Default parallelism for build pipelines.",
        ),
    )

    tags: ClassVar[Tuple[TemplateTagSpec, ...]] = (
        TemplateTagSpec(taxonomy_name="env", canonical_value="dev"),
    )

    notification_rules: ClassVar[Tuple[TemplateNotificationRuleSpec, ...]] = (
        TemplateNotificationRuleSpec(
            event_pattern="entity.run.failed",
            template_name="run_failed",
            channel_names=(),
            recipients=(),
        ),
    )

    recommended_roles: ClassVar[Tuple[str, ...]] = ("ProjectOwner", "Editor", "Viewer")


class ComplianceProjectTemplate(ProjectTemplateExtension):
    """
        Reference template that seeds a project for compliance-sensitive work.
    """

    resource_extension_name: ClassVar[str] = "project_template"
    template_id: ClassVar[str] = "compliance"
    template_version: ClassVar[str] = "1.0.0"
    display_name: ClassVar[str] = "Compliance Project"
    description: ClassVar[str] = "Compliance-sensitive project with stricter defaults."

    variables: ClassVar[Tuple[TemplateVariableSpec, ...]] = (
        TemplateVariableSpec(
            name="retention_days",
            value_type="INTEGER",
            default_value=730,
            description="Artifact retention (2 years).",
        ),
    )

    tags: ClassVar[Tuple[TemplateTagSpec, ...]] = (
        TemplateTagSpec(taxonomy_name="compliance", canonical_value="restricted"),
    )

    notification_rules: ClassVar[Tuple[TemplateNotificationRuleSpec, ...]] = ()

    recommended_roles: ClassVar[Tuple[str, ...]] = ("ProjectOwner", "Auditor")
