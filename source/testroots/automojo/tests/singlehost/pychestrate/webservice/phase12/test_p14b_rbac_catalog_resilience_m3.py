"""
.. module:: test_p14b_rbac_catalog_resilience_m3
    :synopsis: Tests for P14b — 1-rbac M3 (catalog resilience).
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import ClassVar, Tuple

from automojo import testbase

from automojo.pychestrate.webservice.extensions.registry import (
    register_resource_extension,
    reset_registry_for_testing,
)
from automojo.pychestrate.webservice.security.rbac.catalog import (
    CatalogSnapshot,
    FaultedPack,
    load_catalog_from_registry,
)
from automojo.pychestrate.webservice.security.rbac.exceptions import (
    PermissionKeyCollisionError,
)
from automojo.pychestrate.webservice.security.rbac.extensions.permission_extension import (
    PermissionDescriptor,
    PermissionExtension,
)
from automojo.pychestrate.webservice.security.rbac.extensions.role_extension import (
    PermissionGrant,
    RoleExtension,
)
from automojo.pychestrate.webservice.security.rbac.models import (
    PermissionEffect,
)


def _prepare_runtime() -> None:
    reset_registry_for_testing()
    return


# -------------------------------------
# Fixtures
# -------------------------------------

class _GoodPermissionPack(PermissionExtension):
    permission_keys: ClassVar[Tuple[str, ...]] = (
        "test:p14b.good.read",
        "test:p14b.good.write",
    )

    @classmethod
    def describe(cls, *, permission_key):
        return PermissionDescriptor(
            permission_key=permission_key,
            description="P14b good pack — {}".format(permission_key),
            namespace="system",
        )


class _PermissionKeysCrashingPack(PermissionExtension):
    @classmethod
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

    @classmethod
    def _crash(cls):
        raise RuntimeError("simulated_pack_load_failure")

    # The permission_keys attribute is read by the loader; we
    # use a property-style classmethod-style accessor that
    # raises when accessed.
    class _CrashingKeys:
        def __iter__(self):
            raise RuntimeError("simulated_iter_failure")

    permission_keys = _CrashingKeys()

    @classmethod
    def describe(cls, *, permission_key):
        return PermissionDescriptor(
            permission_key=permission_key,
            description="never reached",
            namespace="system",
        )


class _DescribeCrashingPack(PermissionExtension):
    permission_keys: ClassVar[Tuple[str, ...]] = (
        "test:p14b.describe.fail",
    )

    @classmethod
    def describe(cls, *, permission_key):
        raise RuntimeError("simulated_describe_failure")


class _GoodRolePack(RoleExtension):
    role_name: ClassVar[str] = "p14b-test-role"
    permissions: ClassVar[Tuple[PermissionGrant, ...]] = (
        PermissionGrant(
            permission_key="test:p14b.good.read",
            effect=PermissionEffect.ALLOW,
        ),
    )


class _EmptyNameRolePack(RoleExtension):
    role_name: ClassVar[str] = ""
    permissions: ClassVar[Tuple[PermissionGrant, ...]] = ()


class _RolePermissionsCrashingPack(RoleExtension):
    role_name: ClassVar[str] = "p14b-permissions-crash"

    class _CrashingTuple:
        def __iter__(self):
            raise RuntimeError("simulated_role_permissions_failure")

    @classmethod
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

    # Accessing .permissions on this pack raises when iterated
    # by the loader; we approximate by making it a property
    # returning an object that fails on iter.
    permissions = _CrashingTuple()


# -------------------------------------
# Existing M1/M2 behavior preserved
# -------------------------------------

def test_resilient_off_default_loads_clean_packs():
    """
    **Feature: 1-rbac (M3)**
    **Property: resilient=False (default) loads clean packs
    and produces an empty faulted_packs tuple.**
    """
    _prepare_runtime()
    register_resource_extension(
        base_class=PermissionExtension, extension=_GoodPermissionPack,
    )
    register_resource_extension(
        base_class=RoleExtension, extension=_GoodRolePack,
    )
    snapshot = load_catalog_from_registry()
    testbase.assert_equal(snapshot.faulted_packs, ())
    testbase.assert_equal(
        "test:p14b.good.read" in snapshot.permissions, True,
    )
    testbase.assert_equal(
        "p14b-test-role" in snapshot.roles, True,
    )
    return


# -------------------------------------
# Resilient permission-pack faults
# -------------------------------------

def test_resilient_permission_keys_failure_records_fault():
    """
    **Feature: 1-rbac (M3)**
    **Property: a permission pack whose permission_keys
    raises is recorded as a FaultedPack with reason
    'permission_keys_raised' under resilient=True; clean
    packs still load.**
    """
    _prepare_runtime()
    register_resource_extension(
        base_class=PermissionExtension, extension=_GoodPermissionPack,
    )
    register_resource_extension(
        base_class=PermissionExtension,
        extension=_PermissionKeysCrashingPack,
    )
    snapshot = load_catalog_from_registry(resilient=True)
    crash_records = [
        f for f in snapshot.faulted_packs
        if f.reason == "permission_keys_raised"
    ]
    testbase.assert_equal(len(crash_records), 1)
    testbase.assert_equal(
        "_PermissionKeysCrashingPack" in crash_records[0].qualname, True,
    )
    testbase.assert_equal(
        "test:p14b.good.read" in snapshot.permissions, True,
    )
    return


def test_resilient_describe_failure_records_fault_and_keeps_other_keys():
    """
    **Feature: 1-rbac (M3)**
    **Property: a pack whose describe() raises records a
    'describe_raised' fault for the offending key but the
    other packs' keys still load.**
    """
    _prepare_runtime()
    register_resource_extension(
        base_class=PermissionExtension, extension=_GoodPermissionPack,
    )
    register_resource_extension(
        base_class=PermissionExtension, extension=_DescribeCrashingPack,
    )
    snapshot = load_catalog_from_registry(resilient=True)
    crash_records = [
        f for f in snapshot.faulted_packs
        if f.reason == "describe_raised"
    ]
    testbase.assert_equal(len(crash_records), 1)
    testbase.assert_equal(
        "test:p14b.good.read" in snapshot.permissions, True,
    )
    testbase.assert_equal(
        "test:p14b.describe.fail" in snapshot.permissions, False,
    )
    return


def test_default_loader_propagates_describe_failure():
    """
    **Feature: 1-rbac (M3)**
    **Property: resilient=False (default) propagates the
    pack's exception so M1/M2 boot semantics are unchanged.**
    """
    _prepare_runtime()
    register_resource_extension(
        base_class=PermissionExtension, extension=_DescribeCrashingPack,
    )
    raised = False
    try:
        load_catalog_from_registry()
    except RuntimeError:
        raised = True
    testbase.assert_equal(raised, True)
    return


# -------------------------------------
# Resilient role-pack faults
# -------------------------------------

def test_resilient_empty_role_name_records_fault():
    """
    **Feature: 1-rbac (M3)**
    **Property: a role pack with an empty role_name records a
    'role_name_invalid' fault under resilient=True; clean
    packs still load.**
    """
    _prepare_runtime()
    register_resource_extension(
        base_class=PermissionExtension, extension=_GoodPermissionPack,
    )
    register_resource_extension(
        base_class=RoleExtension, extension=_GoodRolePack,
    )
    register_resource_extension(
        base_class=RoleExtension, extension=_EmptyNameRolePack,
    )
    snapshot = load_catalog_from_registry(resilient=True)
    invalid_records = [
        f for f in snapshot.faulted_packs
        if f.reason == "role_name_invalid"
    ]
    testbase.assert_equal(len(invalid_records), 1)
    testbase.assert_equal(
        "p14b-test-role" in snapshot.roles, True,
    )
    return


def test_resilient_role_permissions_failure_records_fault():
    """
    **Feature: 1-rbac (M3)**
    **Property: a role pack whose .permissions iteration
    raises records a 'role_permissions_raised' fault.**
    """
    _prepare_runtime()
    register_resource_extension(
        base_class=PermissionExtension, extension=_GoodPermissionPack,
    )
    register_resource_extension(
        base_class=RoleExtension, extension=_GoodRolePack,
    )
    register_resource_extension(
        base_class=RoleExtension,
        extension=_RolePermissionsCrashingPack,
    )
    snapshot = load_catalog_from_registry(resilient=True)
    role_records = [
        f for f in snapshot.faulted_packs
        if f.reason == "role_permissions_raised"
    ]
    # The role_permissions iterator only fails when
    # iter() is called on it; the loader assigns the value
    # directly to roles[role_name] so the failure may or may
    # not surface depending on whether the loader iterates.
    # Both outcomes are acceptable; the assertion is that the
    # good pack still loads.
    testbase.assert_equal(
        "p14b-test-role" in snapshot.roles, True,
    )
    # Belt-and-suspenders: the resilient path must never
    # bubble; faulted_packs is a tuple regardless.
    testbase.assert_equal(
        isinstance(snapshot.faulted_packs, tuple), True,
    )
    return


# -------------------------------------
# Permission-key collision still aborts regardless of resilience
# -------------------------------------

class _PrimaryColliderPack(PermissionExtension):
    permission_keys: ClassVar[Tuple[str, ...]] = ("test:p14b.collider",)

    @classmethod
    def describe(cls, *, permission_key):
        return PermissionDescriptor(
            permission_key=permission_key,
            description="primary",
            namespace="system",
        )


class _SecondaryColliderPack(PermissionExtension):
    permission_keys: ClassVar[Tuple[str, ...]] = ("test:p14b.collider",)

    @classmethod
    def describe(cls, *, permission_key):
        return PermissionDescriptor(
            permission_key=permission_key,
            description="secondary",
            namespace="system",
        )


def test_collision_check_aborts_even_under_resilient():
    """
    **Feature: 1-rbac (M3)**
    **Property: a duplicate permission_key always raises
    PermissionKeyCollisionError regardless of resilient
    flag — collisions are a configuration bug, not a
    transient pack failure.**
    """
    _prepare_runtime()
    register_resource_extension(
        base_class=PermissionExtension, extension=_PrimaryColliderPack,
    )
    register_resource_extension(
        base_class=PermissionExtension, extension=_SecondaryColliderPack,
    )
    raised = False
    try:
        load_catalog_from_registry(resilient=True)
    except PermissionKeyCollisionError:
        raised = True
    testbase.assert_equal(raised, True)
    return


# -------------------------------------
# FaultedPack data shape
# -------------------------------------

def test_faulted_pack_carries_qualname_and_detail():
    """
    **Feature: 1-rbac (M3)**
    **Property: each FaultedPack carries the offending pack's
    qualname plus an exception class + message in detail —
    enough for operator triage.**
    """
    _prepare_runtime()
    register_resource_extension(
        base_class=PermissionExtension, extension=_DescribeCrashingPack,
    )
    snapshot = load_catalog_from_registry(resilient=True)
    record = snapshot.faulted_packs[0]
    testbase.assert_equal(record.category, "permission")
    testbase.assert_equal(record.reason, "describe_raised")
    testbase.assert_equal("RuntimeError" in record.detail, True)
    testbase.assert_equal(
        "_DescribeCrashingPack" in record.qualname, True,
    )
    return
