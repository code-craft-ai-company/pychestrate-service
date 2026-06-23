"""
.. module:: security.rbac.exceptions
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Exception types raised by the RBAC service.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


class RoleNotFoundError(Exception):
    """
        Raised when a binding references an unregistered role.
    """


class BindingNotFoundError(Exception):
    """
        Raised when a revoke references an unknown binding id.
    """


class PermissionKeyCollisionError(Exception):
    """
        Raised when two ``PermissionExtension`` packs declare the same key.
    """


class AuthorizationError(Exception):
    """
        Raised by ``require_permission`` when the decision is deny.
    """


class InvalidBindingScopeError(Exception):
    """
        Raised when ``assign_role`` is called with a scope + scope_id
        combination that is illegal (e.g. ``scope_kind=PROJECT`` with no
        ``scope_id``, or ``inherits_into_project=True`` at a non-organization
        scope).
    """
