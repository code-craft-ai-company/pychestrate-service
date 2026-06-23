"""
.. module:: project_templates.extensions.template
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: ProjectTemplateExtension — base class for project templates.

.. moduleauthor:: Code Craft AI LLC

A :class:`ProjectTemplateExtension` subclass bundles the opinionated
defaults (variables, tags, notification rules, recommended roles)
applied at project creation or reapplication. M1 only registers /
reads templates; the apply-at-create transaction and diff API land
in M2.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass, field
from typing import Any, ClassVar, List, Mapping, Tuple

from ccai.pychestrate.webservice.extensions.resource_extension import ResourceExtension


@dataclass(frozen=True)
class TemplateVariableSpec:
    """
        One variable to apply at project creation.

        :param name: Variable name.
        :param value_type: Declared value type (``STRING | INTEGER | ...``).
        :param default_value: Default payload.
        :param description: Human-readable description.
    """
    name: str
    value_type: str
    default_value: Any
    description: str = ""


@dataclass(frozen=True)
class TemplateTagSpec:
    """
        One tag to assign at project creation.

        :param taxonomy_name: Registered taxonomy name.
        :param canonical_value: Canonical tag value.
    """
    taxonomy_name: str
    canonical_value: str


@dataclass(frozen=True)
class TemplateNotificationRuleSpec:
    """
        One notification routing rule to seed at project creation.

        :param event_pattern: Event pattern glob.
        :param template_name: Registered template name.
        :param channel_names: Channel names referenced by the rule.
        :param recipients: Recipient list.
    """
    event_pattern: str
    template_name: str
    channel_names: Tuple[str, ...] = field(default_factory=tuple)
    recipients: Tuple[str, ...] = field(default_factory=tuple)


class ProjectTemplateExtension(ResourceExtension):
    """
        Base class for project templates registered via E-resource-extensions.
    """

    resource_extension_name: ClassVar[str] = "project_template"
    template_id: ClassVar[str] = ""
    template_version: ClassVar[str] = "0.0.0"
    display_name: ClassVar[str] = ""
    description: ClassVar[str] = ""
    variables: ClassVar[Tuple[TemplateVariableSpec, ...]] = ()
    tags: ClassVar[Tuple[TemplateTagSpec, ...]] = ()
    notification_rules: ClassVar[Tuple[TemplateNotificationRuleSpec, ...]] = ()
    recommended_roles: ClassVar[Tuple[str, ...]] = ()
    PRECEDENCE: ClassVar[int] = 1000
