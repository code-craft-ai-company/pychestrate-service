"""
.. module:: webinterface.blueprints.config.permission_denied
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The text of the 403 page an admin page answers when the
               viewer lacks its permission: which permission, what it
               covers, and which built-in roles grant it.

.. moduleauthor:: Code Craft AI LLC

A refused admin request used to say only "Your account does not have
permission to view this page" (or, on three pages, redirect to the
dashboard with a flash). The viewer could not tell an administrator
what to grant (audit ADM-21).
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import logging

from typing import List, Tuple


_module_logger = logging.getLogger(__name__)


def _describe_from_catalog(*, permission: str) -> Tuple[str, List[str]]:
    """
        The permission's catalog description and the built-in roles
        that allow it.

        :param permission: Canonical permission key.

        :returns: ``(description, role_names)``; empty when the catalog
                  cannot be read.
    """
    description = ""
    role_names: List[str] = []
    try:
        from ccai.pychestrate.webservice.security.rbac import catalog as _catalog  # noqa: E402
        from ccai.pychestrate.webservice.security.rbac.models import (  # noqa: E402
            PermissionEffect,
        )
        snapshot = _catalog.load_catalog_from_registry()
        descriptor = snapshot.permissions.get(permission, None)
        if descriptor is not None:
            description = str(descriptor.description or "").strip()
        for role_name, grants in snapshot.roles.items():
            for grant in grants:
                if grant.permission_key == permission and grant.effect == PermissionEffect.ALLOW:
                    role_names.append(role_name)
                    break
    except Exception:
        _module_logger.debug(
            "pychestrate.ui.admin.authz.catalog_unavailable permission=%s", permission,
            exc_info=True,
        )
    rtnval = (description, sorted(role_names))
    return rtnval


def describe_missing_permission(*, permission: str) -> str:
    """
        The 403 page's message for a viewer without ``permission``.

        :param permission: Canonical permission key the page requires,
                           e.g. ``"system:resources.manage"``.

        :returns: Plain text naming the permission, what it covers and
                  the built-in roles that grant it.
    """
    description, role_names = _describe_from_catalog(permission=permission)
    sentences = [
        'This page needs the "{}" permission, which your account does not have.'.format(permission)
    ]
    if len(description) > 0:
        sentences.append("It covers: {}.".format(description.rstrip(".")))
    if len(role_names) > 0:
        sentences.append(
            "Built-in roles that grant it: {}. Ask an administrator to assign one to you.".format(
                ", ".join(role_names)
            )
        )
    else:
        sentences.append("Ask an administrator for access.")
    rtnval = " ".join(sentences)
    return rtnval


__all__ = [
    "describe_missing_permission",
]
