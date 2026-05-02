"""
.. module:: test_p10h_rest_endpoint_extension_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the RestEndpointExtension resource base + reference.

.. moduleauthor:: Automation Mojo LLC

The slice promotes ``RestEndpointExtension`` from the published-but-
not-yet-implemented list (per ``8-plugin-api`` Requirement 2) into the
catalog. Tests cover the dataclass, the resource-base contract, the
reference implementation, and the catalog walk that picks the new
entry up.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo import testbase

from automojo.pychestrate.webservice.extensions.rest_endpoint_example import (
    ExampleEchoEndpoints,
)
from automojo.pychestrate.webservice.extensions.rest_endpoint_protocol import (
    HTTP_METHOD_GET,
    HTTP_METHOD_POST,
    RestEndpointDescriptor,
    RestEndpointExtension,
    is_valid_http_method,
)
from automojo.pychestrate.webservice.extensions.resource_extension import ResourceExtension
from automojo.pychestrate.webservice.plugin_api import build_catalog, is_class_published
from automojo.pychestrate.webservice.plugin_api.catalog_validator import (
    validate_catalog_against_code,
)


# ---------------------------------------------------------------------------
# Resource base + descriptor
# ---------------------------------------------------------------------------

def test_rest_endpoint_extension_is_resource_subclass():
    """
    **Feature: 8-rest-api-v1 (T2.5 partial)**
    **Property: RestEndpointExtension is a direct subclass of
    ResourceExtension so the catalog walker enumerates it.**
    """
    testbase.assert_equal(issubclass(RestEndpointExtension, ResourceExtension), True)
    testbase.assert_equal(ResourceExtension in RestEndpointExtension.__bases__, True)
    return


def test_rest_endpoint_extension_default_ext_name_is_empty():
    """
    **Feature: 8-rest-api-v1 (T2.5 partial)**
    **Property: The base class declares ext_name = '' so subclasses
    must override.**
    """
    testbase.assert_equal(RestEndpointExtension.ext_name, "")
    return


def test_rest_endpoint_extension_declare_endpoints_raises_on_base():
    """
    **Feature: 8-rest-api-v1 (T2.5 partial)**
    **Property: Calling declare_endpoints on the base raises
    NotImplementedError.**
    """
    raised = False
    try:
        RestEndpointExtension.declare_endpoints()
    except NotImplementedError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_rest_endpoint_descriptor_is_frozen_with_documented_fields():
    """
    **Feature: 8-rest-api-v1 (T2.5 partial)**
    **Property: RestEndpointDescriptor is a frozen dataclass carrying
    method, path_suffix, required_permissions, required_capabilities,
    description.**
    """
    descriptor = RestEndpointDescriptor(
        method=HTTP_METHOD_GET,
        path_suffix="/example",
        required_permissions=("system:reader",),
        required_capabilities=("net:outbound",),
        description="example",
    )
    testbase.assert_equal(descriptor.method, HTTP_METHOD_GET)
    testbase.assert_equal(descriptor.path_suffix, "/example")
    testbase.assert_equal(descriptor.required_permissions, ("system:reader",))

    raised = False
    try:
        descriptor.method = HTTP_METHOD_POST
    except Exception:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_is_valid_http_method_accepts_documented_verbs():
    """
    **Feature: 8-rest-api-v1 (T2.5 partial)**
    **Property: is_valid_http_method honors the documented verb set.**
    """
    testbase.assert_equal(is_valid_http_method(method=HTTP_METHOD_GET), True)
    testbase.assert_equal(is_valid_http_method(method=HTTP_METHOD_POST), True)
    testbase.assert_equal(is_valid_http_method(method="OPTIONS"), False)
    testbase.assert_equal(is_valid_http_method(method="get"), False)
    return


# ---------------------------------------------------------------------------
# Reference implementation
# ---------------------------------------------------------------------------

def test_example_echo_subclasses_rest_endpoint_extension():
    """
    **Feature: 8-rest-api-v1 (T2.6 partial)**
    **Property: ExampleEchoEndpoints inherits from RestEndpointExtension
    (not directly from ResourceExtension), so the catalog walker treats
    the base class as the published resource entry rather than the
    reference impl.**
    """
    testbase.assert_equal(issubclass(ExampleEchoEndpoints, RestEndpointExtension), True)
    testbase.assert_equal(
        RestEndpointExtension in ExampleEchoEndpoints.__bases__, True
    )
    testbase.assert_equal(
        ResourceExtension in ExampleEchoEndpoints.__bases__, False
    )
    return


def test_example_echo_declares_get_echo_endpoint():
    """
    **Feature: 8-rest-api-v1 (T2.6 partial)**
    **Property: declare_endpoints returns a single descriptor for
    GET /echo with no required permissions or capabilities (M1
    minimum-viable surface).**
    """
    descriptors = ExampleEchoEndpoints.declare_endpoints()
    testbase.assert_equal(len(descriptors), 1)
    testbase.assert_equal(descriptors[0].method, HTTP_METHOD_GET)
    testbase.assert_equal(descriptors[0].path_suffix, "/echo")
    testbase.assert_equal(descriptors[0].required_permissions, tuple())
    testbase.assert_equal(descriptors[0].required_capabilities, tuple())
    return


def test_example_echo_handler_returns_message():
    """
    **Feature: 8-rest-api-v1 (T2.6 partial)**
    **Property: The reference handler returns the supplied message in
    the documented response shape.**
    """
    rtnval = ExampleEchoEndpoints.echo(message="hello")
    testbase.assert_equal(rtnval, {"message": "hello"})
    return


def test_example_echo_ext_name_is_example():
    """
    **Feature: 8-rest-api-v1 (T2.6 partial)**
    **Property: ExampleEchoEndpoints binds the namespace
    /api/v1/ext/example.**
    """
    testbase.assert_equal(ExampleEchoEndpoints.ext_name, "example")
    return


# ---------------------------------------------------------------------------
# Catalog integration
# ---------------------------------------------------------------------------

def test_rest_endpoint_extension_is_published():
    """
    **Feature: 8-plugin-api integration**
    **Property: is_class_published returns True for the new resource
    base.**
    """
    rtnval = is_class_published(target_class=RestEndpointExtension)
    testbase.assert_equal(rtnval, True)
    return


def test_catalog_includes_rest_endpoint_extension_entry():
    """
    **Feature: 8-plugin-api integration**
    **Property: build_catalog now lists a RestEndpointExtension entry
    pointing at ExampleEchoEndpoints as the reference.**
    """
    catalog = build_catalog()
    matched = None
    for entry in catalog.resource_entries:
        if entry.name == "RestEndpointExtension":
            matched = entry
            break
    testbase.assert_equal(matched is not None, True)
    testbase.assert_equal(
        matched.metadata.reference.endswith(".ExampleEchoEndpoints"), True
    )
    return


def test_catalog_validator_resolves_rest_endpoint_reference():
    """
    **Feature: 8-plugin-api integration**
    **Property: validate_catalog_against_code resolves the
    ExampleEchoEndpoints dotted path without raising.**
    """
    catalog = build_catalog()
    validate_catalog_against_code(catalog=catalog)
    return
