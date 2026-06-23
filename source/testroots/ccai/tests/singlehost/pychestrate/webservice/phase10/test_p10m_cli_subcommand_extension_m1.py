"""
.. module:: test_p10m_cli_subcommand_extension_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the CLISubcommandExtension resource base + reference.

.. moduleauthor:: Code Craft AI LLC

The slice promotes ``CLISubcommandExtension`` from the published-but-
not-yet-implemented list (per ``8-plugin-api`` Requirement 2) into the
catalog. Tests cover the dataclass, the resource-base contract, the
reference implementation, and the catalog walk that picks the new
entry up.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai import testbase

from ccai.pychestrate.cli.extensions.cli_subcommand import (
    CLISubcommandDescriptor,
    CLISubcommandExtension,
)
from ccai.pychestrate.cli.extensions.example_subcommand import (
    PycExtExampleSubcommand,
)
from ccai.pychestrate.webservice.extensions.resource_extension import ResourceExtension
from ccai.pychestrate.webservice.plugin_api import build_catalog, is_class_published
from ccai.pychestrate.webservice.plugin_api.catalog_validator import (
    validate_catalog_against_code,
)


# ---------------------------------------------------------------------------
# Resource base + descriptor
# ---------------------------------------------------------------------------

def test_cli_subcommand_extension_is_direct_resource_subclass():
    """
    **Feature: 8-plugin-api / 8-cli partial M2**
    **Property: CLISubcommandExtension is a direct subclass of
    ResourceExtension so the catalog walker enumerates it as a
    published base.**
    """
    testbase.assert_equal(issubclass(CLISubcommandExtension, ResourceExtension), True)
    testbase.assert_equal(ResourceExtension in CLISubcommandExtension.__bases__, True)
    return


def test_cli_subcommand_extension_default_ext_name_is_empty():
    """
    **Feature: 8-cli partial M2**
    **Property: The base declares ext_name = '' so subclasses must
    override.**
    """
    testbase.assert_equal(CLISubcommandExtension.ext_name, "")
    return


def test_cli_subcommand_extension_default_required_capabilities_empty():
    """
    **Feature: 8-cli partial M2**
    **Property: The base default for required_capabilities is the
    empty tuple — read-only subcommands need nothing.**
    """
    testbase.assert_equal(CLISubcommandExtension.required_capabilities(), tuple())
    return


def test_cli_subcommand_extension_declare_subcommands_raises_on_base():
    """
    **Feature: 8-cli partial M2**
    **Property: Calling declare_subcommands on the base raises
    NotImplementedError.**
    """
    raised = False
    try:
        CLISubcommandExtension.declare_subcommands()
    except NotImplementedError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_cli_subcommand_descriptor_is_frozen_with_documented_fields():
    """
    **Feature: 8-cli partial M2**
    **Property: CLISubcommandDescriptor is frozen with verb,
    operation_id, positional_arg_names, flag_arg_names, description.**
    """
    descriptor = CLISubcommandDescriptor(
        verb="echo",
        operation_id="ext_example_echo",
        positional_arg_names=("topic",),
        flag_arg_names=("message",),
        description="example",
    )
    testbase.assert_equal(descriptor.verb, "echo")
    testbase.assert_equal(descriptor.operation_id, "ext_example_echo")
    testbase.assert_equal(descriptor.positional_arg_names, ("topic",))
    testbase.assert_equal(descriptor.flag_arg_names, ("message",))

    raised = False
    try:
        descriptor.verb = "different"
    except Exception:
        raised = True
    testbase.assert_equal(raised, True)
    return


# ---------------------------------------------------------------------------
# Reference implementation
# ---------------------------------------------------------------------------

def test_example_subcommand_inherits_from_base_not_resource_extension():
    """
    **Feature: 8-cli partial M2**
    **Property: PycExtExampleSubcommand inherits from
    CLISubcommandExtension (not directly from ResourceExtension), so
    the catalog walker treats only the base as the published entry.**
    """
    testbase.assert_equal(
        issubclass(PycExtExampleSubcommand, CLISubcommandExtension), True
    )
    testbase.assert_equal(
        CLISubcommandExtension in PycExtExampleSubcommand.__bases__, True
    )
    testbase.assert_equal(
        ResourceExtension in PycExtExampleSubcommand.__bases__, False
    )
    return


def test_example_subcommand_declares_echo_descriptor():
    """
    **Feature: 8-cli partial M2**
    **Property: declare_subcommands returns a single descriptor for
    'echo' wrapping ext_example_echo with the documented flag set.**
    """
    descriptors = PycExtExampleSubcommand.declare_subcommands()
    testbase.assert_equal(len(descriptors), 1)
    testbase.assert_equal(descriptors[0].verb, "echo")
    testbase.assert_equal(descriptors[0].operation_id, "ext_example_echo")
    testbase.assert_equal(descriptors[0].positional_arg_names, tuple())
    testbase.assert_equal(descriptors[0].flag_arg_names, ("message",))
    return


def test_example_subcommand_ext_name_is_example():
    """
    **Feature: 8-cli partial M2**
    **Property: PycExtExampleSubcommand binds the namespace
    pyc ext example.**
    """
    testbase.assert_equal(PycExtExampleSubcommand.ext_name, "example")
    return


def test_example_subcommand_required_capabilities_empty():
    """
    **Feature: 8-cli partial M2**
    **Property: The reference subcommand declares no required
    capabilities (matches the empty-cap example REST endpoint).**
    """
    testbase.assert_equal(
        PycExtExampleSubcommand.required_capabilities(), tuple()
    )
    return


# ---------------------------------------------------------------------------
# Catalog integration
# ---------------------------------------------------------------------------

def test_cli_subcommand_extension_is_published():
    """
    **Feature: 8-plugin-api integration**
    **Property: is_class_published returns True for the new resource
    base.**
    """
    rtnval = is_class_published(target_class=CLISubcommandExtension)
    testbase.assert_equal(rtnval, True)
    return


def test_catalog_includes_cli_subcommand_extension_entry():
    """
    **Feature: 8-plugin-api integration**
    **Property: build_catalog now lists a CLISubcommandExtension
    entry pointing at PycExtExampleSubcommand as the reference.**
    """
    catalog = build_catalog()
    matched = None
    for entry in catalog.resource_entries:
        if entry.name == "CLISubcommandExtension":
            matched = entry
            break
    testbase.assert_equal(matched is not None, True)
    testbase.assert_equal(
        matched.metadata.reference.endswith(".PycExtExampleSubcommand"), True
    )
    return


def test_catalog_validator_resolves_cli_subcommand_reference():
    """
    **Feature: 8-plugin-api integration**
    **Property: validate_catalog_against_code resolves the
    PycExtExampleSubcommand dotted path without raising.**
    """
    catalog = build_catalog()
    validate_catalog_against_code(catalog=catalog)
    return
