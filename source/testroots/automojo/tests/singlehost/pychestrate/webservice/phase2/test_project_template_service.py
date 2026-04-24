"""
.. module:: test_project_template_service
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for 2-project-templates M1 service surface.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo import testbase

from automojo.pychestrate.webservice.extensions.registry import register_resource_extension
from automojo.pychestrate.webservice.project_templates import service as template_service
from automojo.pychestrate.webservice.project_templates.exceptions import (
    TemplateNotRegisteredError,
)
from automojo.pychestrate.webservice.project_templates.extensions.template import (
    ProjectTemplateExtension,
)

from automojo.tests.singlehost.pychestrate.webservice.phase2.fixtures import (
    reset_phase2_runtime,
)


class _TestMinimalTemplate(ProjectTemplateExtension):
    """
        Minimal in-test template used to exercise the registry.
    """

    resource_extension_name: str = "project_template"
    template_id: str = "test_minimal"
    template_version: str = "0.1.0"
    display_name: str = "Test Minimal"
    description: str = "Test-only minimal template."
    variables = ()
    tags = ()
    notification_rules = ()
    recommended_roles = ("ProjectOwner",)
    PRECEDENCE: int = 500


def test_list_templates_returns_registered():
    """
    **Feature: 2-project-templates (M1)**
    **Property: list_templates returns a summary per registered
    ProjectTemplateExtension subclass.**
    """
    reset_phase2_runtime()
    register_resource_extension(
        base_class=ProjectTemplateExtension,
        extension=_TestMinimalTemplate,
    )

    rows = template_service.list_templates()
    template_ids = [row.template_id for row in rows]
    testbase.assert_equal("test_minimal" in template_ids, True)
    return


def test_read_template_round_trip():
    """
    **Feature: 2-project-templates (M1)**
    **Property: read_template returns the expected summary for a
    registered template.**
    """
    reset_phase2_runtime()
    register_resource_extension(
        base_class=ProjectTemplateExtension,
        extension=_TestMinimalTemplate,
    )

    summary = template_service.read_template(template_id="test_minimal")
    testbase.assert_equal(summary.template_id, "test_minimal")
    testbase.assert_equal(summary.template_version, "0.1.0")
    testbase.assert_equal(summary.recommended_roles, ("ProjectOwner",))
    return


def test_read_template_missing_raises():
    """
    **Feature: 2-project-templates (M1)**
    **Property: read_template with an unregistered id raises
    TemplateNotRegisteredError.**
    """
    reset_phase2_runtime()

    raised = False
    try:
        template_service.read_template(template_id="does-not-exist")
    except TemplateNotRegisteredError:
        raised = True
    testbase.assert_equal(raised, True)
    return
