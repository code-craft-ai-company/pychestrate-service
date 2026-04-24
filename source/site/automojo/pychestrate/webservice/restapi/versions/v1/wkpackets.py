"""
.. module:: wkpackets
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Aggregates all namespace publishers for v1 API

.. moduleauthor:: Automation Mojo LLC

This module aggregates all namespace publishers for the v1 REST API.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from .feature.examples import publish_namespaces as examples_publish_namespaces
from .config import publish_namespaces as config_publish_namespaces
from .resources import publish_namespaces as resources_publish_namespaces
from .projects import publish_namespaces as projects_publish_namespaces
from .phase1 import publish_namespaces as phase1_publish_namespaces
from .phase2 import publish_namespaces as phase2_publish_namespaces
from .phase3 import publish_namespaces as phase3_publish_namespaces


def publish_namespaces(version_prefix):
    """
    Publish all v1 namespaces.

    :param version_prefix: The version prefix for the API path
    :returns: List of (namespace, path) tuples
    """
    ns_list = []

    # Feature namespaces
    ns_list.extend(examples_publish_namespaces(version_prefix))

    # Config namespaces (users, auth, roles, sessions, variables, secrets, audit)
    ns_list.extend(config_publish_namespaces(version_prefix))

    # Resource namespaces (resources, pools, ip-pools, allocations, reservations, tags, health)
    ns_list.extend(resources_publish_namespaces(version_prefix))

    # Project namespaces (projects, repositories, builds, infrastructure, tests, releases, calendar, watches)
    ns_list.extend(projects_publish_namespaces(version_prefix))

    # Phase-1 spec-shaped namespaces (identity, auth, rbac, secrets, audit, flags)
    ns_list.extend(phase1_publish_namespaces(version_prefix))

    # Phase-2 spec-shaped namespaces (projects, tagging, variables,
    # notifications, project-templates, retention)
    ns_list.extend(phase2_publish_namespaces(version_prefix))

    # Phase-3 spec-shaped namespaces (pod definitions/lifecycle/static/
    # topology/scoped-config/dynamic; agent protocol/capability/inventory/upgrade)
    ns_list.extend(phase3_publish_namespaces(version_prefix))

    return ns_list
