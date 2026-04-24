"""
.. module:: projects.exceptions
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Exceptions raised by 2-projects service APIs.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


class SlugValidationError(ValueError):
    """
        Raised when a project slug fails canonicalization or pattern check.
    """


class ProjectAlreadyExistsError(Exception):
    """
        Raised when creating a project with a slug that already exists.
    """


class ProjectNotFoundError(Exception):
    """
        Raised when a project lookup has no matching row.
    """


class ProjectStateTransitionError(Exception):
    """
        Raised when a requested state transition is invalid (e.g.
        deleting a project that is not archived).
    """


class LastAdminRemovalError(Exception):
    """
        Raised when removing a member would leave the project with no
        user bearing the ``ProjectOwner`` role.
    """


class MemberBindingNotFoundError(Exception):
    """
        Raised when a member binding lookup has no matching row.
    """


class MetadataFieldValidationError(Exception):
    """
        Raised when an extension_fields payload violates a registered
        :class:`ProjectMetadataFieldExtension` spec.
    """
