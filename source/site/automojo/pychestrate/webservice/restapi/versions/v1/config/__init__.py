"""
.. module:: config
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: REST API endpoints for system configuration

.. moduleauthor:: Automation Mojo LLC

This package contains REST API endpoints for system configuration including:
- User management
- Authentication
- Role management
- Session management
- Global variables
- Secret management
- Audit logs
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from .users import publish_namespaces as users_publish_namespaces
from .auth import publish_namespaces as auth_publish_namespaces
from .roles import publish_namespaces as roles_publish_namespaces
from .sessions import publish_namespaces as sessions_publish_namespaces
from .variables import publish_namespaces as variables_publish_namespaces
from .secrets import publish_namespaces as secrets_publish_namespaces
from .audit import publish_namespaces as audit_publish_namespaces


def publish_namespaces(version_prefix):
    """
    Publish all config-related namespaces.
    
    :param version_prefix: The version prefix for the API path
    :returns: List of (namespace, path) tuples
    """
    ns_list = []
    
    ns_list.extend(users_publish_namespaces(version_prefix))
    ns_list.extend(auth_publish_namespaces(version_prefix))
    ns_list.extend(roles_publish_namespaces(version_prefix))
    ns_list.extend(sessions_publish_namespaces(version_prefix))
    ns_list.extend(variables_publish_namespaces(version_prefix))
    ns_list.extend(secrets_publish_namespaces(version_prefix))
    ns_list.extend(audit_publish_namespaces(version_prefix))
    
    return ns_list
