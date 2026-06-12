"""
.. module:: test_extensions_registry
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the Phase-1 extension-host registry.

.. moduleauthor:: Code Craft AI LLC

Validates the behavior of
:mod:`ccai.pychestrate.webservice.extensions.registry`: PRECEDENCE
ordering, predicate resolution, resource-extension enumeration, and the
ConfigurationError surface raised when no implementation matches.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai import testbase

from ccai.errors.exceptions import ConfigurationError

from ccai.pychestrate.webservice.extensions.factory_protocol import FactoryProtocolBase
from ccai.pychestrate.webservice.extensions.registry import (
    list_factory_implementations,
    list_resource_extensions,
    register_factory_implementation,
    register_resource_extension,
    reset_registry_for_testing,
    resolve_factory_implementation,
    unregister_factory_implementation,
)
from ccai.pychestrate.webservice.extensions.resource_extension import ResourceExtension


class _FakeProtocol(FactoryProtocolBase):
    factory_protocol_name: str = "test.fake_protocol"
    protocol_schema_version: int = 1


class _LowPrecedenceImpl(_FakeProtocol):
    PRECEDENCE: int = 500


class _HighPrecedenceImpl(_FakeProtocol):
    PRECEDENCE: int = 1000


class _FakeResourceBase(ResourceExtension):
    resource_extension_name: str = "test.fake_resource"


class _FakeResourceA(_FakeResourceBase):
    pass


class _FakeResourceB(_FakeResourceBase):
    pass


def test_register_sorts_by_precedence():
    """
    **Feature: 1-extension-host**
    **Property: Registrations are returned in ascending PRECEDENCE order.**
    """
    reset_registry_for_testing()
    register_factory_implementation(implementation=_HighPrecedenceImpl)
    register_factory_implementation(implementation=_LowPrecedenceImpl)

    impls = list_factory_implementations(factory_protocol_name="test.fake_protocol")

    testbase.assert_equal(len(impls), 2)
    testbase.assert_equal(impls[0], _LowPrecedenceImpl)
    testbase.assert_equal(impls[1], _HighPrecedenceImpl)
    return


def test_register_is_idempotent():
    """
    **Feature: 1-extension-host**
    **Property: Registering the same class twice yields a single entry.**
    """
    reset_registry_for_testing()
    register_factory_implementation(implementation=_LowPrecedenceImpl)
    register_factory_implementation(implementation=_LowPrecedenceImpl)

    impls = list_factory_implementations(factory_protocol_name="test.fake_protocol")
    testbase.assert_equal(len(impls), 1)
    return


def test_unregister_removes_entry():
    """
    **Feature: 1-extension-host**
    **Property: unregister_factory_implementation removes the given class.**
    """
    reset_registry_for_testing()
    register_factory_implementation(implementation=_LowPrecedenceImpl)
    register_factory_implementation(implementation=_HighPrecedenceImpl)
    unregister_factory_implementation(implementation=_LowPrecedenceImpl)

    impls = list_factory_implementations(factory_protocol_name="test.fake_protocol")
    testbase.assert_equal(len(impls), 1)
    testbase.assert_equal(impls[0], _HighPrecedenceImpl)
    return


def test_resolve_predicate_matches_first_candidate():
    """
    **Feature: 1-extension-host**
    **Property: resolve_factory_implementation honors the predicate.**
    """
    reset_registry_for_testing()
    register_factory_implementation(implementation=_LowPrecedenceImpl)
    register_factory_implementation(implementation=_HighPrecedenceImpl)

    matched = resolve_factory_implementation(
        factory_protocol_name="test.fake_protocol",
        predicate=lambda impl: impl is _HighPrecedenceImpl,
    )
    testbase.assert_equal(matched, _HighPrecedenceImpl)
    return


def test_resolve_without_match_raises_configuration_error():
    """
    **Feature: 1-extension-host**
    **Property: resolve with no candidate raises ConfigurationError.**
    """
    reset_registry_for_testing()
    raised = False
    try:
        resolve_factory_implementation(
            factory_protocol_name="test.does_not_exist",
            predicate=None,
        )
    except ConfigurationError:
        raised = True

    testbase.assert_equal(raised, True)
    return


def test_register_empty_protocol_name_raises():
    """
    **Feature: 1-extension-host**
    **Property: A class with empty factory_protocol_name fails registration.**
    """
    class _BogusImpl(FactoryProtocolBase):
        factory_protocol_name: str = ""
        PRECEDENCE: int = 1000

    reset_registry_for_testing()
    raised = False
    try:
        register_factory_implementation(implementation=_BogusImpl)
    except ConfigurationError:
        raised = True

    testbase.assert_equal(raised, True)
    return


def test_resource_extensions_register_and_list():
    """
    **Feature: 1-extension-host**
    **Property: Resource extensions enumerate in registration order.**
    """
    reset_registry_for_testing()
    register_resource_extension(base_class=_FakeResourceBase, extension=_FakeResourceA)
    register_resource_extension(base_class=_FakeResourceBase, extension=_FakeResourceB)
    register_resource_extension(base_class=_FakeResourceBase, extension=_FakeResourceA)

    exts = list_resource_extensions(base_class=_FakeResourceBase)
    testbase.assert_equal(len(exts), 2)
    testbase.assert_equal(exts[0], _FakeResourceA)
    testbase.assert_equal(exts[1], _FakeResourceB)
    return
