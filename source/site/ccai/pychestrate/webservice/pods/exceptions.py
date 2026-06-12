"""
.. module:: pods.exceptions
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Exceptions raised by Layer-3 pod services.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


class PodSpecValidationError(Exception):
    """
        Raised when a :class:`PodSpec` fails validator checks.
    """


class PodDefinitionNotFoundError(Exception):
    """
        Raised when a pod definition lookup has no match.
    """


class PodDefinitionAlreadyExistsError(Exception):
    """
        Raised when creating a pod definition that collides on
        (project_id, pod_name).
    """


class PodStateTransitionError(Exception):
    """
        Raised when an invalid pod-lifecycle transition is attempted.
    """


class PodRegistrationRejectedError(Exception):
    """
        Raised when a static-pod registration report mismatches the
        pinned definition version.
    """


class PodTemplateNotFoundError(Exception):
    """
        Raised when a dynamic-pod template lookup has no match.
    """


class MaterializationError(Exception):
    """
        Raised when dynamic-pod materialization hits a terminal failure.
    """


class MemberKindNotRegisteredError(Exception):
    """
        Raised when a pod spec references a member kind that has no
        registered :class:`PodMemberKindExtension`.
    """
