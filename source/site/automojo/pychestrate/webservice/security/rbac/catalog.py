"""
.. module:: security.rbac.catalog
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Catalog loader for PermissionExtension and RoleExtension packs.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from automojo.pychestrate.webservice.extensions.registry import list_resource_extensions
from automojo.pychestrate.webservice.security.rbac.exceptions import PermissionKeyCollisionError
from automojo.pychestrate.webservice.security.rbac.extensions.permission_extension import (
    PermissionDescriptor,
    PermissionExtension,
)
from automojo.pychestrate.webservice.security.rbac.extensions.role_extension import (
    PermissionGrant,
    RoleExtension,
)


@dataclass(frozen=True)
class FaultedPack:
    """
        Per-pack failure record produced by the M3 resilient
        loader.

        :param category: ``"permission"`` or ``"role"``.
        :param qualname: Fully-qualified class name of the pack
                         that faulted.
        :param reason: Stable token —
                       ``permission_keys_raised`` /
                       ``describe_raised`` /
                       ``role_permissions_raised`` /
                       ``role_name_invalid``.
        :param detail: Exception class + message for operator
                       triage.
    """
    category: str
    qualname: str
    reason: str
    detail: str


@dataclass(frozen=True)
class CatalogSnapshot:
    """
        Immutable snapshot of registered permissions and roles.

        :param permissions: Mapping of permission_key to descriptor.
        :param roles: Mapping of role_name to tuple of grants.
        :param faulted_packs: Tuple of per-pack failure records
                              the M3 resilient loader collected
                              without halting the catalog build.
                              Empty when ``resilient=False`` or
                              when every pack loaded cleanly.
    """
    permissions: Dict[str, PermissionDescriptor] = field(default_factory=dict)
    roles: Dict[str, Tuple[PermissionGrant, ...]] = field(default_factory=dict)
    faulted_packs: Tuple[FaultedPack, ...] = ()


def load_catalog_from_registry(
        *,
        resilient: bool = False
    ) -> CatalogSnapshot:
    """
        Walk registered ``PermissionExtension`` and ``RoleExtension``
        subclasses and produce the canonical in-memory catalog.

        :param resilient: When ``True`` (M3), a pack that
                          raises during catalog load is
                          recorded as a :class:`FaultedPack`
                          and the loader keeps walking the
                          remaining packs. When ``False``
                          (default — M1/M2 behavior), pack
                          exceptions bubble. Permission-key
                          collisions still abort regardless of
                          ``resilient``.

        :returns: The :class:`CatalogSnapshot`.
        :raises: PermissionKeyCollisionError on duplicate
                 keys; pack-level exceptions when
                 ``resilient=False``.
    """
    permission_packs = list_resource_extensions(base_class=PermissionExtension)
    role_packs = list_resource_extensions(base_class=RoleExtension)

    permissions: Dict[str, PermissionDescriptor] = {}
    collisions: List[str] = []
    faulted: List[FaultedPack] = []

    for pack in permission_packs:
        try:
            keys = list(pack.permission_keys)
        except Exception as keys_err:
            if resilient is False:
                raise
            faulted.append(_record_fault(
                category="permission",
                pack=pack,
                reason="permission_keys_raised",
                err=keys_err,
            ))
            continue
        for key in keys:
            if key in permissions:
                collisions.append(key)
                continue
            try:
                descriptor = pack.describe(permission_key=key)
            except Exception as describe_err:
                if resilient is False:
                    raise
                faulted.append(_record_fault(
                    category="permission",
                    pack=pack,
                    reason="describe_raised",
                    err=describe_err,
                ))
                # Skip the offending key but keep processing
                # the rest of the pack.
                continue
            permissions[key] = descriptor

    if len(collisions) > 0:
        err_msg_lines = ["Permission catalog load aborted — duplicate keys."]
        err_msg_lines.append("DUPLICATES: ({})".format(len(collisions)))
        for key in collisions:
            err_msg_lines.append("    {}".format(key))
        err_msg = os.linesep.join(err_msg_lines)
        raise PermissionKeyCollisionError(err_msg) from None

    roles: Dict[str, Tuple[PermissionGrant, ...]] = {}
    for role_pack in role_packs:
        try:
            role_name = role_pack.role_name
        except Exception as name_err:
            if resilient is False:
                raise
            faulted.append(_record_fault(
                category="role",
                pack=role_pack,
                reason="role_name_invalid",
                err=name_err,
            ))
            continue
        if role_name is None or len(role_name) == 0:
            if resilient is False:
                err_msg_lines = ["RoleExtension is missing role_name."]
                err_msg_lines.append(
                    "PACK: {}".format(
                        getattr(role_pack, "__qualname__", str(role_pack)),
                    ),
                )
                err_msg = os.linesep.join(err_msg_lines)
                raise ValueError(err_msg) from None
            faulted.append(FaultedPack(
                category="role",
                qualname=getattr(
                    role_pack, "__qualname__", str(role_pack),
                ),
                reason="role_name_invalid",
                detail="role_name is empty",
            ))
            continue
        try:
            grants = role_pack.permissions
        except Exception as grants_err:
            if resilient is False:
                raise
            faulted.append(_record_fault(
                category="role",
                pack=role_pack,
                reason="role_permissions_raised",
                err=grants_err,
            ))
            continue
        roles[role_name] = grants

    rtnval = CatalogSnapshot(
        permissions=permissions,
        roles=roles,
        faulted_packs=tuple(faulted),
    )
    return rtnval


def _record_fault(
        *,
        category: str,
        pack,
        reason: str,
        err: Exception
    ) -> FaultedPack:
    """
        Build a :class:`FaultedPack` for the resilient-load
        path. Centralizes the qualname + detail formatting so
        every call site produces a consistent record.
    """
    rtnval = FaultedPack(
        category=category,
        qualname=getattr(pack, "__qualname__", str(pack)),
        reason=reason,
        detail="{}: {}".format(type(err).__name__, err),
    )
    return rtnval
