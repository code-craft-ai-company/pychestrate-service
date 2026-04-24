"""
.. module:: projects.events
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Event topic names published by 2-projects.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


class ProjectEventTopics:
    """
        String constants for every entity topic owned by 2-projects.
    """

    PROJECT_CREATED: str = "entity.project.created"
    PROJECT_ARCHIVED: str = "entity.project.archived"
    PROJECT_UNARCHIVED: str = "entity.project.unarchived"
    PROJECT_DELETED: str = "entity.project.deleted"
    PROJECT_MEMBER_ADDED: str = "entity.project.member_added"
    PROJECT_MEMBER_REMOVED: str = "entity.project.member_removed"
