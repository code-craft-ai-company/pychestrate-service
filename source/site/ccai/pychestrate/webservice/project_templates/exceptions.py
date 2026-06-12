"""
.. module:: project_templates.exceptions
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Exceptions raised by 2-project-templates service APIs.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


class TemplateNotRegisteredError(Exception):
    """
        Raised when a requested template is not in the registry.
    """


class DuplicateTemplateError(Exception):
    """
        Raised at startup when two :class:`ProjectTemplateExtension`
        subclasses declare the same ``template_id``.
    """
