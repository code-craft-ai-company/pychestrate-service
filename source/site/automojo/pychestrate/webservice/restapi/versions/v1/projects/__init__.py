"""
.. module:: projects
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: REST API endpoints for project management

.. moduleauthor:: Automation Mojo LLC

This package contains REST API endpoints for project management including:
- Project CRUD operations
- Project membership management
- Project resource assignment
- Project variables
- Repository management
- Build specification and execution
- Infrastructure specification and jobs
- Test specification and jobs
- Release management
- Calendar events
- Watch management

Requirements: 12.1
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from .projects import publish_namespaces as projects_publish_namespaces
from .repositories import publish_namespaces as repositories_publish_namespaces
from .builds import publish_namespaces as builds_publish_namespaces
from .infrastructure import publish_namespaces as infrastructure_publish_namespaces
from .tests import publish_namespaces as tests_publish_namespaces
from .releases import publish_namespaces as releases_publish_namespaces
from .calendar import publish_namespaces as calendar_publish_namespaces
from .watches import publish_namespaces as watches_publish_namespaces


def publish_namespaces(version_prefix):
    """
    Publish all project-related namespaces.
    
    :param version_prefix: The version prefix for the API path
    :returns: List of (namespace, path) tuples
    """
    ns_list = []
    
    ns_list.extend(projects_publish_namespaces(version_prefix))
    ns_list.extend(repositories_publish_namespaces(version_prefix))
    ns_list.extend(builds_publish_namespaces(version_prefix))
    ns_list.extend(infrastructure_publish_namespaces(version_prefix))
    ns_list.extend(tests_publish_namespaces(version_prefix))
    ns_list.extend(releases_publish_namespaces(version_prefix))
    ns_list.extend(calendar_publish_namespaces(version_prefix))
    ns_list.extend(watches_publish_namespaces(version_prefix))
    
    return ns_list
