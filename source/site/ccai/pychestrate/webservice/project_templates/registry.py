"""
.. module:: project_templates.registry
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Runtime registry over :class:`ProjectTemplateExtension` subclasses.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from typing import Dict, Tuple, Type

from ccai.errors.exceptions import ConfigurationError

from ccai.pychestrate.webservice.extensions.registry import list_resource_extensions
from ccai.pychestrate.webservice.hardening.collisions import check_unique_identifiers
from ccai.pychestrate.webservice.project_templates.exceptions import (
    DuplicateTemplateError,
    TemplateNotRegisteredError,
)
from ccai.pychestrate.webservice.project_templates.extensions.template import (
    ProjectTemplateExtension,
)


def load_registered_templates() -> Dict[str, Type[ProjectTemplateExtension]]:
    """
        Return a ``template_id → class`` mapping across every registered
        :class:`ProjectTemplateExtension`.

        :returns: Dict keyed by template id.
        :raises: DuplicateTemplateError on collision or empty id.
    """
    packs: Tuple[Type[ProjectTemplateExtension], ...] = list_resource_extensions(
        base_class=ProjectTemplateExtension
    )
    try:
        rtnval = check_unique_identifiers(
            packs=packs,
            identifier_attribute="template_id",
            category_label="ProjectTemplateExtension",
        )
    except ConfigurationError as xcpt:
        raise DuplicateTemplateError(str(xcpt)) from None

    return rtnval


def get_template(*, template_id: str) -> Type[ProjectTemplateExtension]:
    """
        Look up a registered template class by id.

        :param template_id: Declared template id.

        :returns: The matching class.
        :raises: TemplateNotRegisteredError
    """
    registry = load_registered_templates()
    pack = registry.get(template_id, None)
    if pack is None:
        err_msg_lines = ["Requested template is not registered."]
        err_msg_lines.append("TEMPLATE_ID: {}".format(template_id))
        err_msg = os.linesep.join(err_msg_lines)
        raise TemplateNotRegisteredError(err_msg)

    rtnval = pack
    return rtnval
