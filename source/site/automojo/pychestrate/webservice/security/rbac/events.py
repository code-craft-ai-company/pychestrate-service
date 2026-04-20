"""
.. module:: security.rbac.events
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Event topic names published by 1-rbac.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


class RbacEventTopics:
    """
        String constants for every entity topic owned by 1-rbac.
    """

    ROLE_ASSIGNED: str = "entity.role.assigned"
    ROLE_REVOKED: str = "entity.role.revoked"
    CATALOG_RELOADED: str = "entity.rbac.catalog.reloaded"
