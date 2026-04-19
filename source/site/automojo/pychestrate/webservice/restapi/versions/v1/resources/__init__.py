"""
.. module:: resources
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: REST API endpoints for resource management

.. moduleauthor:: Automation Mojo LLC

This package contains REST API endpoints for resource management including:
- Resource CRUD operations
- Pool management
- IP pool management
- Allocation management
- Reservation management
- Tag management
- Health monitoring
- History and metrics

Requirements: 10.1, 10.2
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from .base import publish_namespaces as base_publish_namespaces
from .resources import publish_namespaces as resources_publish_namespaces
from .pools import publish_namespaces as pools_publish_namespaces
from .ip_pools import publish_namespaces as ip_pools_publish_namespaces
from .allocations import publish_namespaces as allocations_publish_namespaces
from .reservations import publish_namespaces as reservations_publish_namespaces
from .tags import publish_namespaces as tags_publish_namespaces
from .health import publish_namespaces as health_publish_namespaces


def publish_namespaces(version_prefix):
    """
    Publish all resource-related namespaces.
    
    :param version_prefix: The version prefix for the API path
    :returns: List of (namespace, path) tuples
    """
    ns_list = []
    
    ns_list.extend(resources_publish_namespaces(version_prefix))
    ns_list.extend(pools_publish_namespaces(version_prefix))
    ns_list.extend(ip_pools_publish_namespaces(version_prefix))
    ns_list.extend(allocations_publish_namespaces(version_prefix))
    ns_list.extend(reservations_publish_namespaces(version_prefix))
    ns_list.extend(tags_publish_namespaces(version_prefix))
    ns_list.extend(health_publish_namespaces(version_prefix))
    
    return ns_list
