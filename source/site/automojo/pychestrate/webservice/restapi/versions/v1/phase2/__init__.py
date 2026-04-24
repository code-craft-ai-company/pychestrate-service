"""
.. module:: restapi.versions.v1.phase2
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Aggregates the Phase-2 spec-shaped REST namespaces into v1.

.. moduleauthor:: Automation Mojo LLC

The Phase-2 controllers live alongside their feature modules under
``source/site/automojo/pychestrate/webservice/{projects,tagging,variables,notifications,project_templates,retention}/``.
This aggregator pulls their ``publish_namespaces`` exports together and
exposes a single entry point for ``wkpackets.py`` to consume.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.webservice.notifications.restapi.v1.channels_controller import (
    publish_namespaces as notifications_channels_publish_namespaces,
)
from automojo.pychestrate.webservice.project_templates.restapi.v1.templates_controller import (
    publish_namespaces as project_templates_publish_namespaces,
)
from automojo.pychestrate.webservice.projects.restapi.v1.projects_controller import (
    publish_namespaces as projects_publish_namespaces,
)
from automojo.pychestrate.webservice.retention.restapi.v1.retention_controller import (
    publish_namespaces as retention_publish_namespaces,
)
from automojo.pychestrate.webservice.tagging.restapi.v1.tags_controller import (
    publish_namespaces as tags_publish_namespaces,
)
from automojo.pychestrate.webservice.variables.restapi.v1.variables_controller import (
    publish_namespaces as variables_publish_namespaces,
)


def publish_namespaces(version_prefix: str):
    """
        Return the list of (namespace, path) registrations for every
        Phase-2 feature controller.

        :param version_prefix: Version prefix string (``/1``).

        :returns: List of (namespace, path) tuples.
    """
    rtnval = []
    rtnval.extend(projects_publish_namespaces(version_prefix))
    rtnval.extend(tags_publish_namespaces(version_prefix))
    rtnval.extend(variables_publish_namespaces(version_prefix))
    rtnval.extend(notifications_channels_publish_namespaces(version_prefix))
    rtnval.extend(project_templates_publish_namespaces(version_prefix))
    rtnval.extend(retention_publish_namespaces(version_prefix))
    return rtnval
